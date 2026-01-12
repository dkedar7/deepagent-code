# Quick Start Guide

Get up and running with `langgraph-utils-cli` in 5 minutes!

## Installation

Install from source:

```bash
git clone https://github.com/yourusername/langgraph-utils-cli.git
cd langgraph-utils-cli
pip install -e .
```

## Your First Agent

### 1. Create a Simple Agent

Create a file `my_agent.py`:

```python
from langgraph.graph import StateGraph, MessagesState, START, END

def chatbot(state: MessagesState):
    messages = state["messages"]
    last_message = messages[-1]

    return {
        "messages": [
            {"role": "assistant", "content": f"Echo: {last_message.content}"}
        ]
    }

# Build graph
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge(END, "chatbot")

# Compile (required!)
graph = graph_builder.compile()
```

### 2. Run from CLI

```bash
langgraph-cli my_agent.py -m "Hello, world!"
```

Output:
```
Loading graph from my_agent.py...
✓ Graph 'graph' loaded successfully

╭─ Running Agent ─╮
│ Message: Hello, world! │
╰─────────────────╯

Echo: Hello, world!

✓ Complete
```

## Try the Examples

The package includes several examples:

```bash
# Simple chatbot
langgraph-cli examples/simple_chatbot.py -m "Hi there!"

# Agent with tool calls
langgraph-cli examples/tool_calling_agent.py -m "What's the weather?"

# Agent with interrupts (interactive)
langgraph-cli examples/interrupt_agent.py -m "Execute dangerous action"

# Async agent
langgraph-cli examples/async_agent.py --async-mode -m "Hello!"
```

## Common Use Cases

### Interactive Mode (Handle Interrupts)

```bash
langgraph-cli my_agent.py -m "Delete the database"
```

When an interrupt occurs, you'll be prompted:
```
⚠️  Interrupt

How would you like to proceed?
1. Approve all actions
2. Reject all actions
3. Provide custom decision (JSON)
4. Exit

Enter your choice [1]:
```

### Non-Interactive Mode (Auto-Approve)

```bash
langgraph-cli my_agent.py --no-interactive -m "Delete the database"
```

Interrupts are automatically approved.

### With Configuration

```bash
# Inline JSON
langgraph-cli my_agent.py -m "Hello" -c '{"configurable": {"thread_id": "1"}}'

# From file
langgraph-cli my_agent.py -m "Hello" -c config.json
```

### Async Mode

```bash
langgraph-cli my_agent.py --async-mode -m "Hello"
```

Use this when your agent has async nodes.

### Verbose Mode

```bash
langgraph-cli my_agent.py -v -m "Hello"
```

Shows node names and detailed execution info.

## Programmatic Usage

You can also use the library in your Python code:

### Basic Streaming

```python
from langgraph_utils_cli import stream_graph_updates, prepare_agent_input
from my_agent import graph

input_data = prepare_agent_input(message="Hello!")

for chunk in stream_graph_updates(graph, input_data):
    if chunk.get("chunk"):
        print(chunk["chunk"], end="")
    elif chunk.get("status") == "complete":
        print("\nDone!")
```

### Async Streaming

```python
from langgraph_utils_cli import astream_graph_updates
import asyncio

async def run():
    input_data = prepare_agent_input(message="Hello!")

    async for chunk in astream_graph_updates(graph, input_data):
        if chunk.get("chunk"):
            print(chunk["chunk"], end="")

asyncio.run(run())
```

### Handling Interrupts

```python
from langgraph_utils_cli import stream_graph_updates, prepare_agent_input

# Initial run
input_data = prepare_agent_input(message="Do something")
config = {"configurable": {"thread_id": "1"}}

interrupt_data = None
for chunk in stream_graph_updates(graph, input_data, config=config):
    if chunk.get("status") == "interrupt":
        interrupt_data = chunk["interrupt"]
        break

# Resume with approval
if interrupt_data:
    resume_input = prepare_agent_input(decisions=[{"type": "approve"}])

    for chunk in stream_graph_updates(graph, resume_input, config=config):
        if chunk.get("chunk"):
            print(chunk["chunk"], end="")
```

## Next Steps

- Read the [full README](README.md) for complete documentation
- Check out [examples/](examples/) for more complex use cases
- See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute
- Open an issue if you have questions!

## Troubleshooting

### "Module does not have a 'graph' variable"

Make sure you compile your graph and assign it:

```python
# ✓ Correct
graph = graph_builder.compile()

# ✗ Wrong
compiled_graph = graph_builder.compile()  # Different variable name
```

Or specify the variable name:

```bash
langgraph-cli my_agent.py -g compiled_graph
```

### "Error streaming from agent"

Check that your graph is compatible with LangGraph's streaming API. Make sure:

- Nodes return proper state updates
- Messages follow the MessagesState format
- Tools are properly configured

### Async errors in sync mode

If you get errors about coroutines, try async mode:

```bash
langgraph-cli my_agent.py --async-mode -m "Hello"
```

## Getting Help

- **Issues**: https://github.com/yourusername/langgraph-utils-cli/issues
- **Discussions**: https://github.com/yourusername/langgraph-utils-cli/discussions
- **Examples**: Check the `examples/` directory

Happy agent building! 🚀
