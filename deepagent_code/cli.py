"""
CLI for running arbitrary LangGraph agents from the terminal.
Styled after Claude Code / nanocode.
"""
import asyncio
import importlib.util
import json
import os
import re
import sys
import termios
import threading
import time
import tty
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

from deepagent_code.utils import (
    prepare_agent_input,
    stream_graph_updates,
    astream_graph_updates,
)


# ANSI color codes (matching nanocode style)
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
BLUE, CYAN, GREEN, YELLOW, RED = "\033[34m", "\033[36m", "\033[32m", "\033[33m", "\033[31m"

# Spinner frames for thinking animation
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """A simple terminal spinner for showing activity."""

    def __init__(self, message: str = "Thinking"):
        self.message = message
        self.running = False
        self.thread = None
        self.frame_idx = 0

    def _spin(self):
        """Run the spinner animation."""
        while self.running:
            frame = SPINNER_FRAMES[self.frame_idx % len(SPINNER_FRAMES)]
            print(f"\r{CYAN}{frame}{RESET} {DIM}{self.message}...{RESET}", end="", flush=True)
            self.frame_idx += 1
            time.sleep(0.08)

    def start(self):
        """Start the spinner."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the spinner and clear the line."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        # Clear the spinner line
        print("\r\033[2K", end="", flush=True)


def separator() -> str:
    """Return a dim separator line."""
    try:
        width = min(os.get_terminal_size().columns, 80)
    except OSError:
        width = 80
    return f"{DIM}{'─' * width}{RESET}"


def get_agent_name(graph) -> str:
    """Extract agent name from graph object, defaulting to 'AgentCode'."""
    # Try common attribute names for agent/graph name
    for attr in ('name', 'agent_name', '_name', '__name__'):
        if hasattr(graph, attr):
            name = getattr(graph, attr)
            if name and isinstance(name, str):
                return name
    # Check if it's a compiled graph with a name in builder
    if hasattr(graph, 'builder') and hasattr(graph.builder, 'name'):
        name = graph.builder.name
        if name and isinstance(name, str):
            return name
    return "AgentCode"


def print_header_box(agent_name: str, cwd: str):
    """Print a box-drawn header with the agent name."""
    try:
        term_width = min(os.get_terminal_size().columns, 80)
    except OSError:
        term_width = 80

    # Box drawing characters
    TL, TR, BL, BR = "╭", "╮", "╰", "╯"  # corners
    H, V = "─", "│"  # horizontal and vertical

    # Calculate inner width (accounting for borders and padding)
    inner_width = term_width - 4  # 2 for borders, 2 for padding

    # Build the header content
    title_line = agent_name.center(inner_width)
    cwd_display = cwd if len(cwd) <= inner_width else "..." + cwd[-(inner_width - 3):]
    cwd_line = cwd_display.center(inner_width)

    # Print the box
    print(f"{CYAN}{TL}{H * (term_width - 2)}{TR}{RESET}")
    print(f"{CYAN}{V}{RESET} {BOLD}{title_line}{RESET} {CYAN}{V}{RESET}")
    print(f"{CYAN}{V}{RESET} {DIM}{cwd_line}{RESET} {CYAN}{V}{RESET}")
    print(f"{CYAN}{BL}{H * (term_width - 2)}{BR}{RESET}")
    print()


def render_markdown(text: str) -> str:
    """Simple markdown rendering for **bold** text."""
    return re.sub(r"\*\*(.+?)\*\*", f"{BOLD}\\1{RESET}", text)


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


def load_graph_from_module(module_path: str, graph_name: str = "graph"):
    """
    Dynamically load a LangGraph graph from a Python module path.

    Args:
        module_path: Dotted module path (e.g., "mypackage.agents.chatbot")
        graph_name: Name of the graph variable (default: "graph")

    Returns:
        The loaded graph object

    Raises:
        ModuleNotFoundError: If the module doesn't exist
        AttributeError: If the graph variable doesn't exist in the module
    """
    import importlib
    module = importlib.import_module(module_path)

    if not hasattr(module, graph_name):
        raise AttributeError(
            f"Module '{module_path}' does not have a '{graph_name}' variable. "
            f"Available: {', '.join(dir(module))}"
        )

    graph = getattr(module, graph_name)
    return graph


def load_graph(spec: str, default_graph_name: str = "graph"):
    """
    Load a graph from either a file path or module path.

    Supports formats:
        - path/to/file.py (uses default_graph_name)
        - path/to/file.py:graph_name
        - package.module (uses default_graph_name)
        - package.module:graph_name

    Args:
        spec: File path or module path, optionally with :graph_name suffix
        default_graph_name: Graph name to use if not specified in spec

    Returns:
        The loaded graph object
    """
    # Parse the spec to extract graph name if present
    if ':' in spec:
        path_or_module, graph_name = spec.rsplit(':', 1)
        if not graph_name:
            graph_name = default_graph_name
    else:
        path_or_module = spec
        graph_name = default_graph_name

    # Determine if it's a file path or module path
    # File paths end with .py or contain path separators
    is_file_path = (
        path_or_module.endswith('.py') or
        '/' in path_or_module or
        '\\' in path_or_module or
        Path(path_or_module).exists()
    )

    if is_file_path:
        return load_graph_from_file(path_or_module, graph_name), graph_name
    else:
        return load_graph_from_module(path_or_module, graph_name), graph_name


def get_tool_arg_preview(args: Dict[str, Any]) -> str:
    """Get a preview of the first argument value (nanocode style)."""
    if not args:
        return ""
    # Get first value
    first_val = str(list(args.values())[0])
    # Truncate if needed
    if len(first_val) > 50:
        return first_val[:50] + "..."
    return first_val


def format_result_preview(result: str) -> str:
    """Format a result preview with line count indicator."""
    if not result:
        return "(empty)"
    lines = result.split("\n")
    preview = lines[0][:60]
    if len(lines) > 1:
        preview += f" ... +{len(lines) - 1} lines"
    elif len(lines[0]) > 60:
        preview += "..."
    return preview


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


def print_timing(duration: float, verbose: bool = False):
    """Print response timing information."""
    formatted = format_duration(duration)
    if verbose:
        print(f"\n{DIM}Response time: {formatted}{RESET}")
    else:
        print(f"\n{DIM}{formatted}{RESET}")


def print_chunk(chunk: Dict[str, Any], verbose: bool = False):
    """
    Pretty print a chunk from the stream using Claude Code styling.

    Args:
        chunk: The chunk dictionary
        verbose: Whether to show verbose output
    """
    status = chunk.get("status")

    if status == "streaming":
        # Handle text chunks - cyan bullet with text
        if "chunk" in chunk:
            text = chunk["chunk"]
            node = chunk.get("node", "unknown")
            if verbose:
                print(f"{DIM}[{node}]{RESET} {text}", end="")
            else:
                # Print text output with cyan bullet (only on first chunk or after newline)
                print(f"{CYAN}⏺{RESET} {render_markdown(text)}", end="")

        # Handle tool calls - green bullet with tool name
        elif "tool_calls" in chunk:
            for tool_call in chunk["tool_calls"]:
                tool_name = tool_call["name"]
                args = tool_call.get("args", {})
                arg_preview = get_tool_arg_preview(args)

                print(f"\n{GREEN}⏺ {tool_name.capitalize()}{RESET}({DIM}{arg_preview}{RESET})")

        # Handle tool results - indented with result preview
        elif "tool_result" in chunk:
            result = chunk.get("tool_result", "")
            preview = format_result_preview(str(result))
            print(f"  {DIM}⎿  {preview}{RESET}")

    elif status == "interrupt":
        interrupt_data = chunk.get("interrupt", {})
        action_requests = interrupt_data.get("action_requests", [])

        print(f"\n{YELLOW}⏺ Interrupt{RESET}")
        if action_requests:
            for i, action in enumerate(action_requests):
                tool = action.get('tool', 'unknown')
                args_preview = get_tool_arg_preview(action.get('args', {}))
                print(f"  {DIM}{i + 1}. {tool}({args_preview}){RESET}")

    elif status == "complete":
        pass  # No output on complete (nanocode style)

    elif status == "error":
        error_msg = chunk.get("error", "Unknown error")
        print(f"\n{RED}⏺ Error: {error_msg}{RESET}")


def get_key() -> str:
    """Read a single keypress from stdin."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Handle escape sequences (arrow keys)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return 'up'
                elif ch3 == 'B':
                    return 'down'
        elif ch == '\r' or ch == '\n':
            return 'enter'
        elif ch == '\x03':  # Ctrl+C
            return 'ctrl-c'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_option(options: List[str], prompt: str = "Select an option:") -> int:
    """
    Interactive option selector using arrow keys.

    Args:
        options: List of option strings to display
        prompt: Prompt to show above options

    Returns:
        Index of selected option (0-based)
    """
    selected = 0
    num_options = len(options)

    # Hide cursor
    print("\033[?25l", end="")

    try:
        print(f"\n{BOLD}{prompt}{RESET}")

        # Print initial options
        for i, opt in enumerate(options):
            if i == selected:
                print(f"  {CYAN}❯ {opt}{RESET}")
            else:
                print(f"    {DIM}{opt}{RESET}")

        while True:
            key = get_key()

            if key == 'up' and selected > 0:
                selected -= 1
            elif key == 'down' and selected < num_options - 1:
                selected += 1
            elif key == 'enter':
                break
            elif key == 'ctrl-c':
                print("\033[?25h", end="")  # Show cursor
                sys.exit(0)

            # Move cursor up to redraw options
            print(f"\033[{num_options}A", end="")

            # Redraw options
            for i, opt in enumerate(options):
                # Clear line and print option
                print("\033[2K", end="")  # Clear line
                if i == selected:
                    print(f"  {CYAN}❯ {opt}{RESET}")
                else:
                    print(f"    {DIM}{opt}{RESET}")

        return selected
    finally:
        # Show cursor
        print("\033[?25h", end="")


def handle_interrupt_input(num_actions: int = 1) -> List[Dict[str, Any]]:
    """
    Handle user input for interrupt decisions using arrow key navigation.

    Args:
        num_actions: Number of pending tool calls that need decisions

    Returns:
        List of decision objects (one for each pending action)
    """
    options = [
        "Approve all actions",
        "Reject all actions",
        "Provide custom decision (JSON)",
        "Exit",
    ]

    choice = select_option(options, "How would you like to proceed?")

    if choice == 0:
        # Return approve decision for each pending action
        return [{"type": "approve"} for _ in range(num_actions)]
    elif choice == 1:
        # Return reject decision for each pending action
        return [{"type": "reject"} for _ in range(num_actions)]
    elif choice == 2:
        print("Enter your decision as JSON (will be applied to all actions):")
        json_str = input(f"{BOLD}{BLUE}❯{RESET} ").strip()
        try:
            decision = json.loads(json_str)
            return [decision for _ in range(num_actions)]
        except json.JSONDecodeError as e:
            print(f"{RED}⏺ Invalid JSON: {e}{RESET}")
            return [{"type": "reject"} for _ in range(num_actions)]
    else:
        sys.exit(0)


async def run_single_turn_async(
    graph,
    message: str,
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = True,
    verbose: bool = False,
    stream_mode: str = "updates",
) -> float:
    """Run a single turn of an async LangGraph graph. Returns total duration in seconds."""
    input_data = prepare_agent_input(message=message)
    start_time = time.time()

    while True:
        has_interrupt = False
        num_pending_actions = 0
        first_chunk = True
        spinner = Spinner("Thinking")
        spinner.start()

        async for chunk in astream_graph_updates(graph, input_data, config=config, stream_mode=stream_mode):
            # Stop spinner on first chunk
            if first_chunk:
                spinner.stop()
                first_chunk = False

            print_chunk(chunk, verbose=verbose)

            if chunk.get("status") == "interrupt":
                has_interrupt = True
                # Count pending action requests
                interrupt_data = chunk.get("interrupt", {})
                action_requests = interrupt_data.get("action_requests", [])
                num_pending_actions = len(action_requests) if action_requests else 1

        # Ensure spinner is stopped even if no chunks received
        if first_chunk:
            spinner.stop()

        if has_interrupt and interactive:
            decisions = handle_interrupt_input(num_pending_actions)
            input_data = prepare_agent_input(decisions=decisions)
        else:
            break

    return time.time() - start_time


def run_single_turn_sync(
    graph,
    message: str,
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = True,
    verbose: bool = False,
    stream_mode: str = "updates",
) -> float:
    """Run a single turn of a sync LangGraph graph. Returns total duration in seconds."""
    input_data = prepare_agent_input(message=message)
    start_time = time.time()

    while True:
        has_interrupt = False
        num_pending_actions = 0
        first_chunk = True
        spinner = Spinner("Thinking")
        spinner.start()

        for chunk in stream_graph_updates(graph, input_data, config=config, stream_mode=stream_mode):
            # Stop spinner on first chunk
            if first_chunk:
                spinner.stop()
                first_chunk = False

            print_chunk(chunk, verbose=verbose)

            if chunk.get("status") == "interrupt":
                has_interrupt = True
                # Count pending action requests
                interrupt_data = chunk.get("interrupt", {})
                action_requests = interrupt_data.get("action_requests", [])
                num_pending_actions = len(action_requests) if action_requests else 1

        # Ensure spinner is stopped even if no chunks received
        if first_chunk:
            spinner.stop()

        if has_interrupt and interactive:
            decisions = handle_interrupt_input(num_pending_actions)
            input_data = prepare_agent_input(decisions=decisions)
        else:
            break

    return time.time() - start_time


def run_conversation_loop(
    graph,
    config: Dict[str, Any],
    agent_name: str = "AgentCode",
    use_async: bool = False,
    interactive: bool = True,
    verbose: bool = False,
    stream_mode: str = "updates",
    initial_message: Optional[str] = None,
):
    """
    Run a continuous conversation loop with the LangGraph agent.
    Styled after Claude Code / nanocode.
    """
    # Print box-drawn header with agent name
    print_header_box(agent_name, os.getcwd())

    # Process initial message if provided
    if initial_message:
        print(separator())
        print(f"{BOLD}{BLUE}❯{RESET} {initial_message}")
        print(separator())

        if use_async:
            duration = asyncio.run(
                run_single_turn_async(graph, initial_message, config, interactive, verbose, stream_mode)
            )
        else:
            duration = run_single_turn_sync(graph, initial_message, config, interactive, verbose, stream_mode)
        print_timing(duration, verbose)
        print()

    # Main conversation loop
    while True:
        try:
            print(separator())
            user_input = input(f"{BOLD}{BLUE}❯{RESET} ").strip()
            print(separator())

            if not user_input:
                continue

            # Handle special commands
            if user_input in ("/q", "/quit", "/exit", "exit"):
                break

            if user_input == "/c":
                # Generate new thread_id to start fresh conversation
                config["configurable"]["thread_id"] = str(uuid.uuid4())
                print(f"{GREEN}⏺ Cleared conversation{RESET}")
                continue

            if user_input in ("/h", "/help"):
                print(f"\n{BOLD}Commands:{RESET}")
                print(f"  /q, /quit, exit  - Exit")
                print(f"  /c               - Clear conversation")
                print(f"  /h, /help        - Show this help\n")
                continue

            # Run the agent
            if use_async:
                duration = asyncio.run(
                    run_single_turn_async(graph, user_input, config, interactive, verbose, stream_mode)
                )
            else:
                duration = run_single_turn_sync(graph, user_input, config, interactive, verbose, stream_mode)
            print_timing(duration, verbose)
            print()

        except (EOFError, KeyboardInterrupt):
            break
        except Exception as err:
            print(f"{RED}⏺ Error: {err}{RESET}")


@click.command()
@click.argument("agent_spec", required=False)
@click.option(
    "--graph-name",
    "-g",
    help="Name of the graph variable (default: 'graph', overridden if spec includes :name)",
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
    agent_spec: Optional[str],
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

    AGENT_SPEC can be:
    \b
    - path/to/file.py           (uses default graph name 'graph')
    - path/to/file.py:agent     (specifies graph variable name)
    - package.module            (Python module path)
    - package.module:agent      (module with graph variable name)

    Supports environment variables for configuration:

    \b
    - DEEPAGENT_AGENT_SPEC: Agent location (same formats as above)
    - DEEPAGENT_WORKSPACE_ROOT: Working directory for the agent
    - DEEPAGENT_CONFIG: Configuration JSON string or path to JSON file
    - DEEPAGENT_STREAM_MODE: Stream mode for LangGraph (updates or values)

    Command-line arguments override environment variables.

    \b
    Examples:
        deepagent-code my_agent.py
        deepagent-code my_agent.py:graph
        deepagent-code mypackage.agents:chatbot
        deepagent-code -m "Hello, agent!"
    """
    try:
        # Get environment variables
        env_agent_spec = os.getenv('DEEPAGENT_AGENT_SPEC')
        env_workspace_root = os.getenv('DEEPAGENT_WORKSPACE_ROOT')
        env_config = os.getenv('DEEPAGENT_CONFIG')
        env_stream_mode = os.getenv('DEEPAGENT_STREAM_MODE', 'updates')

        # Determine which spec to use (CLI arg > env var > default)
        final_spec = agent_spec or env_agent_spec
        default_graph_name = graph_name or "graph"

        # If no spec provided, try the default agent
        if not final_spec:
            default_agent_path = Path(__file__).parent.parent / "examples" / "agent.py"
            if default_agent_path.exists():
                final_spec = f"{default_agent_path}:agent"
            else:
                print(f"{RED}⏺ Error: No agent specified.{RESET}")
                print(f"\n{DIM}Usage:{RESET}")
                print(f"  deepagent-code path/to/agent.py:graph")
                print(f"  deepagent-code mypackage.module:agent")
                print(f"\n{DIM}Or set DEEPAGENT_AGENT_SPEC environment variable{RESET}")
                sys.exit(1)

        # Change to workspace root if specified
        if env_workspace_root:
            workspace_path = Path(env_workspace_root).resolve()
            if workspace_path.exists():
                os.chdir(workspace_path)

        # Load the graph
        print(f"{DIM}Loading {final_spec}...{RESET}")
        graph, final_graph_name = load_graph(final_spec, default_graph_name)

        # Parse config
        config_dict = None
        config_source = config or env_config

        if config_source:
            config_path = Path(config_source)
            if config_path.exists():
                with open(config_path) as f:
                    config_dict = json.load(f)
            else:
                try:
                    config_dict = json.loads(config_source)
                except json.JSONDecodeError as e:
                    print(f"{RED}⏺ Invalid config JSON: {e}{RESET}")
                    sys.exit(1)

        # Get stream mode
        final_stream_mode = stream_mode or env_stream_mode

        # Ensure config has a thread_id for checkpointer support
        if config_dict is None:
            config_dict = {}
        if "configurable" not in config_dict:
            config_dict["configurable"] = {}
        if "thread_id" not in config_dict["configurable"]:
            config_dict["configurable"]["thread_id"] = str(uuid.uuid4())

        # Extract agent name from graph object
        agent_name = get_agent_name(graph)

        # Run the conversation loop
        run_conversation_loop(
            graph=graph,
            config=config_dict,
            agent_name=agent_name,
            use_async=use_async,
            interactive=interactive,
            verbose=verbose,
            stream_mode=final_stream_mode,
            initial_message=message,
        )

    except FileNotFoundError as e:
        print(f"{RED}⏺ Error: {e}{RESET}")
        sys.exit(1)
    except AttributeError as e:
        print(f"{RED}⏺ Error: {e}{RESET}")
        sys.exit(1)
    except ModuleNotFoundError as e:
        print(f"{RED}⏺ Error: {e}{RESET}")
        print(f"\n{DIM}Make sure your agent's dependencies are installed.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}⏺ Error: {e}{RESET}")
        if verbose:
            import traceback
            print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
