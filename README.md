# langgraph-utils-cli

A universal CLI for running **any** LangGraph agent from the terminal. Framework-agnostic, robust interrupt handling, and clean JSON-serializable output.

## Why Use This?

`langgraph-utils-cli` provides a **universal CLI for running any LangGraph agent** without requiring any specific framework or middleware. Key benefits:

- **Framework-agnostic**: Works with any LangGraph graph implementation
- **Flexible interrupt handling**: Automatically handles multiple interrupt formats (tuples, objects, dicts)
- **Clean streaming output**: JSON-serializable responses with explicit status tracking
- **Production-ready**: Battle-tested utilities for robust agent execution
- **Both CLI and Library**: Use from terminal or integrate into your Python code

## Features

- ✅ **Universal**: Works with any LangGraph graph, no framework lock-in
- ✅ **Robust interrupt handling**: Supports multiple interrupt formats (tuples, objects, dicts)
- ✅ **Clean output**: JSON-serializable streaming with explicit status tracking
- ✅ **Async/Sync support**: Works with both sync and async graphs
- ✅ **Interactive mode**: Handle interrupts interactively from the terminal
- ✅ **Rich formatting**: Beautiful terminal output with syntax highlighting
- ✅ **Programmatic API**: Use as a library in your Python code

## Installation

Install from source:

```bash
git clone https://github.com/yourusername/langgraph-utils-cli.git
cd langgraph-utils-cli
pip install -e .
```

## Quick Start

### 1. Create a LangGraph Agent

Create a file `my_agent.py`:

```python
from langgraph.graph import StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

def chatbot(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

# Define your graph
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("chatbot", chatbot)
graph_builder.set_entry_point("chatbot")
graph_builder.set_finish_point("chatbot")

# Compile it
graph = graph_builder.compile()
```

### 2. Run from CLI

```bash
# Basic usage
langgraph-cli my_agent.py -m "Hello, how are you?"

# With custom graph variable name
langgraph-cli my_agent.py -g my_custom_graph -m "Hello!"

# Async mode
langgraph-cli my_agent.py --async-mode -m "Hello!"

# With configuration
langgraph-cli my_agent.py -m "Hello!" -c '{"configurable": {"thread_id": "1"}}'

# Non-interactive mode (auto-approve interrupts)
langgraph-cli my_agent.py --no-interactive -m "Hello!"

# Verbose mode (show node names)
langgraph-cli my_agent.py -v -m "Hello!"
```

## Programmatic Usage

### Streaming from a Graph

```python
from langgraph_utils_cli import stream_graph_updates, prepare_agent_input

# Load your graph
from my_agent import graph

# Prepare input
input_data = prepare_agent_input(message="Hello, agent!")

# Stream updates
for chunk in stream_graph_updates(graph, input_data):
    if chunk.get("status") == "streaming":
        if "chunk" in chunk:
            print(chunk["chunk"], end="")
        elif "tool_calls" in chunk:
            print(f"Tool calls: {chunk['tool_calls']}")
    elif chunk.get("status") == "interrupt":
        print(f"Interrupt: {chunk['interrupt']}")
    elif chunk.get("status") == "complete":
        print("Done!")
```

### Async Streaming

```python
from langgraph_utils_cli import astream_graph_updates
import asyncio

async def run_agent():
    input_data = prepare_agent_input(message="Hello!")

    async for chunk in astream_graph_updates(graph, input_data):
        if chunk.get("status") == "streaming":
            if "chunk" in chunk:
                print(chunk["chunk"], end="")

asyncio.run(run_agent())
```

### Handling Interrupts

```python
from langgraph_utils_cli import (
    stream_graph_updates,
    resume_graph_from_interrupt,
    prepare_agent_input
)

# Initial run
input_data = prepare_agent_input(message="Please do X, Y, and Z")
interrupt_data = None

for chunk in stream_graph_updates(graph, input_data, config={"configurable": {"thread_id": "1"}}):
    if chunk.get("status") == "interrupt":
        interrupt_data = chunk["interrupt"]
        break

# Resume with decision
if interrupt_data:
    decision = {"type": "approve"}  # or "reject", or custom

    for chunk in resume_graph_from_interrupt(
        graph,
        decisions=[decision],
        config={"configurable": {"thread_id": "1"}}
    ):
        if chunk.get("status") == "streaming":
            print(chunk.get("chunk", ""))
```

## API Reference

### Core Functions

#### `stream_graph_updates(agent, input_data, config=None, stream_mode="updates")`

Stream updates from a LangGraph agent (sync).

**Yields:**
- `{"chunk": str, "status": "streaming"}` - Text content
- `{"tool_calls": list, "status": "streaming"}` - Tool calls
- `{"todo_list": list, "status": "streaming"}` - Todo updates (if using write_todos)
- `{"interrupt": dict, "status": "interrupt"}` - Interrupts
- `{"status": "complete"}` - Completion
- `{"error": str, "status": "error"}` - Errors

#### `astream_graph_updates(agent, input_data, config=None, stream_mode="updates")`

Async version of `stream_graph_updates`.

#### `prepare_agent_input(message=None, decisions=None, raw_input=None)`

Prepare input for a LangGraph agent.

**Args:**
- `message`: User message string
- `decisions`: List of interrupt decisions
- `raw_input`: Raw input (bypasses message/decisions)

#### `resume_graph_from_interrupt(agent, decisions, config=None, stream_mode="updates")`

Resume from an interrupt (sync).

#### `aresume_graph_from_interrupt(agent, decisions, config=None, stream_mode="updates")`

Resume from an interrupt (async).

### Utility Functions

All utility functions are also exported for advanced use cases:

- `parse_interrupt_value(interrupt_value)` - Parse interrupt formats
- `serialize_action_request(action, index)` - Serialize action requests
- `process_interrupt(interrupt_value)` - Process interrupts
- `extract_todos_from_content(tool_content)` - Extract todo lists
- `serialize_tool_calls(tool_calls, skip_tools=None)` - Serialize tool calls
- `process_message_content(message)` - Extract message content
- `process_ai_message(message, node_name, skip_tools=None)` - Process AI messages

## CLI Options

```
Usage: langgraph-cli [OPTIONS] [GRAPH_FILE]

Options:
  -g, --graph-name TEXT      Name of graph variable (default: "graph")
  -m, --message TEXT         Input message
  -c, --config TEXT          Config JSON string or file path
  --interactive / --no-interactive
                             Handle interrupts interactively (default: True)
  --async-mode / --sync-mode
                             Use async streaming (default: sync)
  --stream-mode TEXT        Stream mode for LangGraph (default: "updates")
  -v, --verbose             Show verbose output
  --help                    Show this message and exit
```

## Environment Variables

Compatible with `deepagent-lab` for consistent configuration:

### `DEEPAGENT_AGENT_SPEC`

Specifies agent location using format: `path/to/file.py:variable_name`

```bash
# Set agent spec
export DEEPAGENT_AGENT_SPEC="my_agent.py:graph"

# Run without specifying file
langgraph-cli -m "Hello!"
```

### `DEEPAGENT_WORKSPACE_ROOT`

Sets the working directory for the agent.

```bash
# Set workspace
export DEEPAGENT_WORKSPACE_ROOT="/path/to/workspace"

# Agent will run in this directory
langgraph-cli my_agent.py -m "Hello!"
```

### `DEEPAGENT_CONFIG`

Configuration JSON string or path to JSON file.

```bash
# JSON string
export DEEPAGENT_CONFIG='{"configurable": {"thread_id": "123"}}'

# Or file path
export DEEPAGENT_CONFIG="config.json"

langgraph-cli my_agent.py -m "Hello!"
```

### `DEEPAGENT_STREAM_MODE`

Default stream mode for LangGraph (`updates` or `values`).

```bash
export DEEPAGENT_STREAM_MODE="values"
langgraph-cli my_agent.py -m "Hello!"
```

### Priority

Command-line arguments always override environment variables:

```bash
export DEEPAGENT_AGENT_SPEC="agent1.py:graph"

# Uses agent2.py instead of agent1.py
langgraph-cli agent2.py -m "Hello!"
```

## Examples

See the `examples/` directory for complete examples:

- `examples/simple_chatbot.py` - Basic chatbot
- `examples/tool_calling_agent.py` - Agent with tool calls
- `examples/interrupt_agent.py` - Agent with interrupts
- `examples/async_agent.py` - Async agent

## Architecture

### Why This Approach is Superior

1. **Framework-agnostic**: Works with any LangGraph graph, no middleware required
2. **Robust interrupt handling**: Handles tuples, objects, and dict formats
3. **Clean output**: JSON-serializable dicts with explicit status tracking
4. **Separation of concerns**: Core utilities separate from CLI

### Interrupt Format Handling

The library handles multiple interrupt formats:

```python
# Format 1: Single-element tuple with object
("(Interrupt(value={'action_requests': [...]}),)")

# Format 2: Two-element tuple
"(action_requests, review_configs)"

# Format 3: Direct object
"Interrupt(action_requests=[...], review_configs=[...])"
```

All are normalized to:

```json
{
  "action_requests": [
    {
      "tool": "tool_name",
      "tool_call_id": "call_0",
      "args": {},
      "description": "..."
    }
  ],
  "review_configs": [
    {
      "allowed_decisions": ["approve", "reject"]
    }
  ]
}
```

## Development

### Setup

```bash
git clone https://github.com/yourusername/langgraph-utils-cli.git
cd langgraph-utils-cli
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
ruff check .
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- Issues: https://github.com/yourusername/langgraph-utils-cli/issues
- Discussions: https://github.com/yourusername/langgraph-utils-cli/discussions

## Changelog

### 0.1.0 (2026-01-12)

- Initial release
- Sync and async streaming support
- Robust interrupt handling
- CLI with rich formatting
- Comprehensive utilities for LangGraph agents
