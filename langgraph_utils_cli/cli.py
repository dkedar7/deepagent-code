"""
CLI for running arbitrary LangGraph agents from the terminal.
"""
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown
from rich import print as rprint

from langgraph_utils_cli.utils import (
    prepare_agent_input,
    stream_graph_updates,
    astream_graph_updates,
)


console = Console()


def parse_agent_spec(agent_spec: str) -> Tuple[str, str]:
    """
    Parse DEEPAGENT_AGENT_SPEC format: path/to/file.py:variable_name.

    Args:
        agent_spec: Agent specification string

    Returns:
        Tuple of (file_path, variable_name)

    Raises:
        ValueError: If format is invalid
    """
    if ':' not in agent_spec:
        raise ValueError(
            f"Invalid agent spec format: '{agent_spec}'. "
            f"Expected format: 'path/to/file.py:variable_name'"
        )

    parts = agent_spec.rsplit(':', 1)
    file_path = parts[0]
    variable_name = parts[1]

    if not file_path.endswith('.py'):
        raise ValueError(f"Agent spec file must be a .py file: {file_path}")

    return file_path, variable_name


def load_graph_from_file(file_path: str, graph_name: str = "graph"):
    """
    Dynamically load a LangGraph graph from a Python file.

    Args:
        file_path: Path to the Python file containing the graph
        graph_name: Name of the graph variable (default: "graph")

    Returns:
        The loaded graph object

    Raises:
        FileNotFoundError: If the file doesn't exist
        AttributeError: If the graph variable doesn't exist in the module
        Exception: For other loading errors
    """
    file_path = Path(file_path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Load the module
    spec = importlib.util.spec_from_file_location("graph_module", file_path)
    if spec is None or spec.loader is None:
        raise Exception(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["graph_module"] = module
    spec.loader.exec_module(module)

    # Get the graph object
    if not hasattr(module, graph_name):
        raise AttributeError(
            f"Module does not have a '{graph_name}' variable. "
            f"Available: {', '.join(dir(module))}"
        )

    graph = getattr(module, graph_name)
    return graph


def print_chunk(chunk: Dict[str, Any], verbose: bool = False):
    """
    Pretty print a chunk from the stream.

    Args:
        chunk: The chunk dictionary
        verbose: Whether to show verbose output
    """
    status = chunk.get("status")

    if status == "streaming":
        # Handle text chunks
        if "chunk" in chunk:
            text = chunk["chunk"]
            node = chunk.get("node", "unknown")
            if verbose:
                console.print(f"[dim][{node}][/dim] {text}")
            else:
                console.print(text, end="")

        # Handle tool calls
        elif "tool_calls" in chunk:
            node = chunk.get("node", "unknown")
            for tool_call in chunk["tool_calls"]:
                table = Table(title=f"Tool Call: {tool_call['name']}", show_header=False)
                table.add_row("ID", tool_call.get("id", "N/A"))
                table.add_row("Name", tool_call["name"])
                table.add_row(
                    "Args",
                    Syntax(
                        json.dumps(tool_call.get("args", {}), indent=2),
                        "json",
                        theme="monokai",
                    ),
                )
                if verbose:
                    table.add_row("Node", node)
                console.print(table)

        # Handle todo lists
        elif "todo_list" in chunk:
            todos = chunk["todo_list"]
            table = Table(title="Todo List")
            table.add_column("Status", style="cyan")
            table.add_column("Task", style="white")

            for todo in todos:
                status_icon = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "completed": "✅",
                }.get(todo.get("status", "pending"), "❓")

                table.add_row(
                    f"{status_icon} {todo.get('status', 'pending')}",
                    todo.get("content", "N/A"),
                )

            console.print(table)

    elif status == "interrupt":
        interrupt_data = chunk.get("interrupt", {})
        action_requests = interrupt_data.get("action_requests", [])
        review_configs = interrupt_data.get("review_configs", [])

        panel_content = []

        if action_requests:
            panel_content.append("[bold yellow]Action Requests:[/bold yellow]")
            for i, action in enumerate(action_requests):
                panel_content.append(f"\n{i + 1}. Tool: {action['tool']}")
                panel_content.append(f"   ID: {action['tool_call_id']}")
                if action.get('description'):
                    panel_content.append(f"   Description: {action['description']}")
                panel_content.append(
                    f"   Args: {json.dumps(action.get('args', {}), indent=6)}"
                )

        if review_configs:
            panel_content.append("\n[bold cyan]Review Configs:[/bold cyan]")
            for i, config in enumerate(review_configs):
                allowed = config.get('allowed_decisions', [])
                panel_content.append(f"\n{i + 1}. Allowed decisions: {', '.join(allowed)}")

        console.print(
            Panel(
                "\n".join(panel_content),
                title="⚠️  Interrupt",
                border_style="yellow",
            )
        )

    elif status == "complete":
        console.print("\n[bold green]✓ Complete[/bold green]")

    elif status == "error":
        error_msg = chunk.get("error", "Unknown error")
        console.print(
            Panel(
                f"[bold red]{error_msg}[/bold red]",
                title="Error",
                border_style="red",
            )
        )


def handle_interrupt_input(interrupt_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle user input for interrupt decisions.

    Args:
        interrupt_data: The interrupt data from the stream

    Returns:
        Decision object to resume with
    """
    action_requests = interrupt_data.get("action_requests", [])
    review_configs = interrupt_data.get("review_configs", [])

    console.print("\n[bold]How would you like to proceed?[/bold]")
    console.print("1. Approve all actions")
    console.print("2. Reject all actions")
    console.print("3. Provide custom decision (JSON)")
    console.print("4. Exit")

    choice = click.prompt("Enter your choice", type=int, default=1)

    if choice == 1:
        return {"type": "approve"}
    elif choice == 2:
        return {"type": "reject"}
    elif choice == 3:
        console.print("Enter your decision as JSON (e.g., {'type': 'approve'}):")
        json_str = click.prompt("Decision JSON", type=str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON: {e}[/red]")
            return {"type": "reject"}
    else:
        sys.exit(0)


async def run_async_graph(
    graph,
    message: str,
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = True,
    verbose: bool = False,
    stream_mode: str = "updates",
):
    """
    Run an async LangGraph graph.

    Args:
        graph: The graph instance
        message: The input message
        config: Optional config dict
        interactive: Whether to handle interrupts interactively
        verbose: Whether to show verbose output
        stream_mode: Stream mode for LangGraph (default: "updates")
    """
    input_data = prepare_agent_input(message=message)

    while True:
        has_interrupt = False
        interrupt_data = None

        async for chunk in astream_graph_updates(graph, input_data, config=config, stream_mode=stream_mode):
            print_chunk(chunk, verbose=verbose)

            if chunk.get("status") == "interrupt":
                has_interrupt = True
                interrupt_data = chunk.get("interrupt", {})

        if has_interrupt and interactive:
            decision = handle_interrupt_input(interrupt_data)
            # Prepare resume input
            from langgraph_utils_cli.utils import prepare_agent_input
            input_data = prepare_agent_input(decisions=[decision])
        else:
            break


def run_sync_graph(
    graph,
    message: str,
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = True,
    verbose: bool = False,
    stream_mode: str = "updates",
):
    """
    Run a sync LangGraph graph.

    Args:
        graph: The graph instance
        message: The input message
        config: Optional config dict
        interactive: Whether to handle interrupts interactively
        verbose: Whether to show verbose output
        stream_mode: Stream mode for LangGraph (default: "updates")
    """
    input_data = prepare_agent_input(message=message)

    while True:
        has_interrupt = False
        interrupt_data = None

        for chunk in stream_graph_updates(graph, input_data, config=config, stream_mode=stream_mode):
            print_chunk(chunk, verbose=verbose)

            if chunk.get("status") == "interrupt":
                has_interrupt = True
                interrupt_data = chunk.get("interrupt", {})

        if has_interrupt and interactive:
            decision = handle_interrupt_input(interrupt_data)
            # Prepare resume input
            from langgraph_utils_cli.utils import prepare_agent_input
            input_data = prepare_agent_input(decisions=[decision])
        else:
            break


@click.command()
@click.argument("graph_file", type=click.Path(exists=True), required=False)
@click.option(
    "--graph-name",
    "-g",
    help="Name of the graph variable in the file (default: 'graph')",
)
@click.option(
    "--message",
    "-m",
    help="Input message to send to the agent",
)
@click.option(
    "--config",
    "-c",
    help="Configuration JSON string or path to JSON file",
)
@click.option(
    "--interactive/--no-interactive",
    default=True,
    help="Handle interrupts interactively (default: True)",
)
@click.option(
    "--async-mode/--sync-mode",
    "use_async",
    default=False,
    help="Use async streaming (default: sync)",
)
@click.option(
    "--stream-mode",
    help="Stream mode for LangGraph (default: 'updates')",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show verbose output including node names",
)
def main(
    graph_file: Optional[str],
    graph_name: Optional[str],
    message: Optional[str],
    config: Optional[str],
    interactive: bool,
    use_async: bool,
    stream_mode: Optional[str],
    verbose: bool,
):
    """
    Run a LangGraph agent from the command line.

    Supports environment variables for configuration (compatible with deepagent-lab):

    - DEEPAGENT_AGENT_SPEC: Agent location (format: path/to/file.py:variable_name)
    - DEEPAGENT_WORKSPACE_ROOT: Working directory for the agent
    - DEEPAGENT_CONFIG: Configuration JSON string or path to JSON file
    - DEEPAGENT_STREAM_MODE: Stream mode for LangGraph (updates or values)

    Command-line arguments override environment variables.

    Examples:

        # Run with a message
        langgraph-cli my_agent.py -m "Hello, agent!"

        # Use DEEPAGENT_AGENT_SPEC environment variable
        export DEEPAGENT_AGENT_SPEC="my_agent.py:graph"
        langgraph-cli -m "Hello!"

        # Use a different graph variable name
        langgraph-cli my_agent.py -g my_custom_graph -m "Hello!"

        # Run in async mode
        langgraph-cli my_agent.py --async-mode -m "Hello!"

        # Provide config
        langgraph-cli my_agent.py -m "Hello!" -c '{"configurable": {"thread_id": "1"}}'

        # Non-interactive mode (auto-approve interrupts)
        langgraph-cli my_agent.py --no-interactive -m "Hello!"
    """
    try:
        # Get environment variables
        env_agent_spec = os.getenv('DEEPAGENT_AGENT_SPEC')
        env_workspace_root = os.getenv('DEEPAGENT_WORKSPACE_ROOT')
        env_config = os.getenv('DEEPAGENT_CONFIG')
        env_stream_mode = os.getenv('DEEPAGENT_STREAM_MODE', 'updates')

        # Resolve graph file and name
        final_graph_file = graph_file
        final_graph_name = graph_name or "graph"

        # If no graph file provided, try DEEPAGENT_AGENT_SPEC
        if not final_graph_file and env_agent_spec:
            try:
                final_graph_file, final_graph_name = parse_agent_spec(env_agent_spec)
                if verbose:
                    console.print(f"[dim]Using DEEPAGENT_AGENT_SPEC: {env_agent_spec}[/dim]")
            except ValueError as e:
                console.print(f"[red]Error parsing DEEPAGENT_AGENT_SPEC: {e}[/red]")
                sys.exit(1)

        # Validate we have a graph file
        if not final_graph_file:
            console.print("[red]Error: No graph file specified.[/red]")
            console.print("\nProvide either:")
            console.print("  1. GRAPH_FILE argument: langgraph-cli my_agent.py")
            console.print("  2. DEEPAGENT_AGENT_SPEC env var: export DEEPAGENT_AGENT_SPEC='my_agent.py:graph'")
            sys.exit(1)

        # Change to workspace root if specified
        if env_workspace_root:
            workspace_path = Path(env_workspace_root).resolve()
            if workspace_path.exists():
                os.chdir(workspace_path)
                if verbose:
                    console.print(f"[dim]Changed to workspace: {workspace_path}[/dim]")
            else:
                console.print(f"[yellow]Warning: DEEPAGENT_WORKSPACE_ROOT not found: {workspace_path}[/yellow]")

        # Load the graph
        console.print(f"[cyan]Loading graph from {final_graph_file}...[/cyan]")
        graph = load_graph_from_file(final_graph_file, final_graph_name)
        console.print(f"[green]✓ Graph '{final_graph_name}' loaded successfully[/green]\n")

        # Parse config (CLI option overrides environment variable)
        config_dict = None
        config_source = config or env_config

        if config_source:
            config_path = Path(config_source)
            if config_path.exists():
                with open(config_path) as f:
                    config_dict = json.load(f)
                if verbose:
                    console.print(f"[dim]Loaded config from file: {config_path}[/dim]")
            else:
                try:
                    config_dict = json.loads(config_source)
                    if verbose:
                        console.print(f"[dim]Loaded config from JSON string[/dim]")
                except json.JSONDecodeError as e:
                    console.print(f"[red]Invalid config JSON: {e}[/red]")
                    sys.exit(1)

        # Get stream mode (CLI option overrides environment variable)
        final_stream_mode = stream_mode or env_stream_mode

        # Get message if not provided
        if not message:
            message = click.prompt("Enter your message", type=str)

        # Run the graph
        console.print(Panel(
            f"[bold]Message:[/bold] {message}",
            title="Running Agent",
            border_style="blue",
        ))
        console.print()

        if use_async:
            asyncio.run(
                run_async_graph(graph, message, config_dict, interactive, verbose, final_stream_mode)
            )
        else:
            run_sync_graph(graph, message, config_dict, interactive, verbose, final_stream_mode)

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except AttributeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
