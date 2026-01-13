# deepagent-code

A Claude Code-style CLI for running LangGraph agents from the terminal.

![deepagent-code](examples/image.png)

## Installation

```bash
pip install deepagent-code
```

Or install directly from GitHub:
```bash
pip install git+https://github.com/dkedar7/deepagent-code.git
```

## Quick Start

Run with the default agent (requires `ANTHROPIC_API_KEY`):
```bash
export ANTHROPIC_API_KEY="your_api_key"
deepagent-code
```

Or specify your own agent:
```bash
deepagent-code path/to/your_agent.py:graph
```

This launches an interactive conversation loop with your agent.

## Usage

```bash
# Use the default agent
deepagent-code

# Specify a custom agent file
deepagent-code my_agent.py:graph

# Use a module path
deepagent-code mypackage.agents:chatbot

# With an initial message
deepagent-code -m "Hello, agent!"

# Non-interactive mode (auto-approve tool calls)
deepagent-code --no-interactive

# Verbose output
deepagent-code -v
```

## Commands

In the interactive loop:
- `/q` or `/quit` - Exit
- `/c` - Clear conversation history
- `/h` or `/help` - Show help

## Environment Variables

```bash
# Agent location (path/to/file.py:variable_name or module:variable)
export DEEPAGENT_AGENT_SPEC="my_agent.py:graph"
deepagent-code

# Working directory
export DEEPAGENT_WORKSPACE_ROOT="/path/to/workspace"

# Configuration
export DEEPAGENT_CONFIG='{"configurable": {"thread_id": "1"}}'
```

## CLI Options

```
Usage: deepagent-code [OPTIONS] [AGENT_SPEC]

Arguments:
  AGENT_SPEC  Agent location (path/to/file.py:graph or module:graph)

Options:
  -g, --graph-name TEXT           Graph variable name (default: "graph")
  -m, --message TEXT              Initial message
  -c, --config TEXT               Config JSON or file path
  --interactive/--no-interactive  Handle interrupts (default: interactive)
  --async-mode/--sync-mode        Async streaming (default: sync)
  -v, --verbose                   Verbose output
```

## Creating Your Own Agent

Your agent file should export a compiled LangGraph graph:

```python
# my_agent.py
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    name="My Agent",
    model="anthropic:claude-sonnet-4-20250514",
    checkpointer=MemorySaver(),
)
```

Then run it:
```bash
deepagent-code my_agent.py:agent
```

## Programmatic Use

```python
from deepagent_code import stream_graph_updates, prepare_agent_input

input_data = prepare_agent_input(message="Hello!")

for chunk in stream_graph_updates(graph, input_data):
    if chunk.get("chunk"):
        print(chunk["chunk"], end="")
```

## License

MIT License - see LICENSE file for details.
