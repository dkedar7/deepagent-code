"""
Reusable utilities for LangGraph agents.

This module provides generic functions for streaming from LangGraph agents,
handling interrupts, and processing various message types. It can be used
across different applications that use LangGraph.
"""
from typing import Any, Dict, Iterator, Optional, List, AsyncIterator
import json
import re
import ast


def parse_interrupt_value(interrupt_value: Any) -> tuple[List[Any], List[Any]]:
    """
    Parse interrupt value into action_requests and review_configs.

    Handles different interrupt value formats from LangGraph:
    - Tuple formats (single element, two elements)
    - Object formats with attributes

    Args:
        interrupt_value: The interrupt value from LangGraph

    Returns:
        Tuple of (action_requests, review_configs)
    """
    action_requests = []
    review_configs = []

    if isinstance(interrupt_value, tuple):
        if len(interrupt_value) == 1:
            # Single-element tuple containing Interrupt object
            interrupt_obj = interrupt_value[0]
            if hasattr(interrupt_obj, 'value') and isinstance(interrupt_obj.value, dict):
                action_requests = interrupt_obj.value.get('action_requests', [])
                review_configs = interrupt_obj.value.get('review_configs', [])
            else:
                action_requests = getattr(interrupt_obj, 'action_requests', [])
                review_configs = getattr(interrupt_obj, 'review_configs', [])
        elif len(interrupt_value) == 2:
            # Two-element tuple: (action_requests, review_configs)
            action_requests, review_configs = interrupt_value
    else:
        # Handle object format
        action_requests = getattr(interrupt_value, 'action_requests', [])
        review_configs = getattr(interrupt_value, 'review_configs', [])

    return action_requests, review_configs


def serialize_action_request(action: Any, index: int) -> Dict[str, Any]:
    """
    Serialize an action request to a dictionary.

    Handles both dict and object formats, and both 'name' and 'tool' field names.

    Args:
        action: The action request object or dict
        index: The index of this action (used for fallback tool_call_id)

    Returns:
        Dictionary with tool, tool_call_id, args, and description
    """
    if isinstance(action, dict):
        tool_name = action.get('tool') or action.get('name')
        tool_call_id = action.get('tool_call_id', f"call_{index}")
        args = action.get('args', {})
        description = action.get('description')
    else:
        tool_name = getattr(action, 'tool', None) or getattr(action, 'name', None)
        tool_call_id = getattr(action, 'tool_call_id', f"call_{index}")
        args = getattr(action, 'args', {})
        description = getattr(action, 'description', None)

    return {
        "tool": tool_name,
        "tool_call_id": tool_call_id,
        "args": args,
        "description": description
    }


def serialize_review_config(config: Any) -> Dict[str, Any]:
    """
    Serialize a review config to a dictionary.

    Args:
        config: The review config object or dict

    Returns:
        Dictionary with allowed_decisions
    """
    if isinstance(config, dict):
        allowed_decisions = config.get('allowed_decisions', [])
    else:
        allowed_decisions = getattr(config, 'allowed_decisions', [])

    return {
        "allowed_decisions": allowed_decisions
    }


def process_interrupt(interrupt_value: Any) -> Dict[str, Any]:
    """
    Process a LangGraph interrupt value and convert to serializable format.

    Args:
        interrupt_value: The interrupt value from the update

    Returns:
        Dictionary containing action_requests and review_configs
    """
    action_requests, review_configs = parse_interrupt_value(interrupt_value)

    interrupt_data = {
        "action_requests": [],
        "review_configs": []
    }

    # Extract action requests
    for i, action in enumerate(action_requests):
        interrupt_data["action_requests"].append(
            serialize_action_request(action, i)
        )

    # Extract review configs
    for config in review_configs:
        interrupt_data["review_configs"].append(
            serialize_review_config(config)
        )

    return interrupt_data


def extract_todos_from_content(tool_content: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Extract todos list from write_todos tool content.

    Handles multiple formats:
    - String with embedded JSON/list
    - Dict with 'todos' key
    - Direct list

    Args:
        tool_content: The content from the write_todos tool message

    Returns:
        List of todo items or None if parsing fails
    """
    todos = None

    if isinstance(tool_content, str):
        # Look for array pattern first (handles "Updated todo list to [...]" format)
        match = re.search(r'\[.*\]', tool_content, re.DOTALL)
        if match:
            array_str = match.group(0)

            # Try parsing as Python literal first (handles single quotes)
            try:
                todos = ast.literal_eval(array_str)
            except:
                # Fall back to JSON parsing (requires double quotes)
                try:
                    todos = json.loads(array_str)
                except:
                    pass
        else:
            # No array found, try parsing entire string as JSON
            try:
                parsed = json.loads(tool_content)
                if isinstance(parsed, dict):
                    todos = parsed.get('todos')
                    # If todos is a string, parse it again
                    if isinstance(todos, str):
                        todos = json.loads(todos)
                elif isinstance(parsed, list):
                    # Content is directly a list
                    todos = parsed
            except:
                pass
    elif isinstance(tool_content, dict):
        todos = tool_content.get('todos')
        if isinstance(todos, str):
            try:
                todos = json.loads(todos)
            except:
                pass
    elif isinstance(tool_content, list):
        # Content is directly a list
        todos = tool_content

    return todos if isinstance(todos, list) else None


def extract_reflection_from_content(tool_content: Any) -> Optional[str]:
    """
    Extract reflection from think_tool content.

    Args:
        tool_content: The content from the think_tool message

    Returns:
        Reflection string or None
    """
    reflection = None

    if isinstance(tool_content, str):
        # Try to parse as JSON
        try:
            parsed = json.loads(tool_content)
            reflection = parsed.get('reflection')
        except:
            reflection = tool_content
    elif isinstance(tool_content, dict):
        reflection = tool_content.get('reflection')

    return reflection


def serialize_tool_calls(tool_calls: List[Any], skip_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Serialize tool calls to dictionaries, optionally skipping certain tools.

    Args:
        tool_calls: List of tool call objects or dicts
        skip_tools: Optional list of tool names to skip (e.g., ['think_tool', 'write_todos'])

    Returns:
        List of serialized tool calls
    """
    skip_tools = skip_tools or []
    serialized = []

    for tc in tool_calls:
        tool_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, 'name', None)

        # Skip specified tools
        if tool_name in skip_tools:
            continue

        serialized.append({
            "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, 'id', None),
            "name": tool_name,
            "args": tc.get("args") if isinstance(tc, dict) else getattr(tc, 'args', {})
        })

    return serialized


def clean_content_from_tool_dicts(content: str) -> str:
    """
    Remove tool call dictionary representations from content strings.

    Tool calls often appear as strings like:
    "{'id': '...', 'input': {...}, 'name': '...', 'type': 'tool_use'}"

    Args:
        content: The content string to clean

    Returns:
        Cleaned content string
    """
    # Pattern to match tool call dictionary representations
    tool_dict_pattern = r"\{'id':\s*'[^']+',\s*'input':\s*\{.*?\},\s*'name':\s*'[^']+',\s*'type':\s*'tool_use'\}"
    content = re.sub(tool_dict_pattern, '', content, flags=re.DOTALL)
    return content.strip()


def process_message_content(message: Any) -> str:
    """
    Extract and convert message content to string.

    Handles different content formats:
    - String content
    - List of content blocks
    - Other types (converted to string)

    Args:
        message: The message object

    Returns:
        Content as string
    """
    if not hasattr(message, 'content'):
        return ""

    content = message.content

    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # Handle list of content blocks (e.g., [{"text": "...", "type": "text"}])
        return " ".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in content
        )
    else:
        return str(content)


def process_tool_message(message: Any) -> Optional[Dict[str, Any]]:
    """
    Process a ToolMessage and extract special content if applicable.

    Handles special tools:
    - think_tool: Extracts and returns reflection
    - write_todos: Extracts and returns todo list

    Args:
        message: The ToolMessage to process

    Returns:
        Dictionary with chunk/todo_list and status, or None if no special handling
    """
    if not hasattr(message, 'name'):
        return None

    tool_name = message.name
    tool_content = message.content

    if tool_name == 'think_tool':
        reflection = extract_reflection_from_content(tool_content)
        if reflection:
            return {
                "chunk": reflection,
                "status": "streaming"
            }
    elif tool_name == 'write_todos':
        todos = extract_todos_from_content(tool_content)
        if todos:
            return {
                "todo_list": todos,
                "status": "streaming"
            }

    return None


def process_ai_message(message: Any, node_name: str, skip_tools: Optional[List[str]] = None) -> Iterator[Dict[str, Any]]:
    """
    Process an AI message and yield content and tool calls.

    Args:
        message: The AI message to process
        node_name: Name of the graph node
        skip_tools: Optional list of tool names to skip when serializing tool calls

    Yields:
        Dictionaries with tool_calls or chunk content
    """
    skip_tools = skip_tools or ['think_tool', 'write_todos']

    # Extract content
    content_str = process_message_content(message)

    # Check for tool calls
    tool_calls = None
    if hasattr(message, 'tool_calls') and message.tool_calls:
        tool_calls = serialize_tool_calls(message.tool_calls, skip_tools=skip_tools)

    # Clean content: strip whitespace and remove tool call dicts
    content_str = content_str.strip() if content_str else ""

    # Filter out tool call dictionaries from content
    if content_str and hasattr(message, 'tool_calls') and message.tool_calls:
        content_str = clean_content_from_tool_dicts(content_str)

    # Yield tool calls (if any)
    if tool_calls and len(tool_calls) > 0:
        yield {
            "tool_calls": tool_calls,
            "node": node_name,
            "status": "streaming"
        }

    # Yield content separately, only if non-empty
    if content_str:
        yield {
            "chunk": content_str,
            "node": node_name,
            "status": "streaming"
        }


def prepare_agent_input(
    message: Optional[str] = None,
    decisions: Optional[List[Dict[str, Any]]] = None,
    raw_input: Optional[Any] = None
) -> Any:
    """
    Prepare input for a LangGraph agent.

    This function handles different input types:
    - message: Regular user message (converted to message dict)
    - decisions: Resume decisions (converted to Command)
    - raw_input: Raw input passed directly (for custom formats)

    Args:
        message: Optional user message string
        decisions: Optional list of interrupt decisions
        raw_input: Optional raw input (bypasses message/decisions processing)

    Returns:
        Prepared input for the agent

    Raises:
        ValueError: If no input is provided or multiple inputs are provided
    """
    # Count how many inputs are provided
    inputs_provided = sum([
        message is not None,
        decisions is not None,
        raw_input is not None
    ])

    if inputs_provided == 0:
        raise ValueError("Must provide one of: message, decisions, or raw_input")
    if inputs_provided > 1:
        raise ValueError("Can only provide one of: message, decisions, or raw_input")

    # Handle raw input (pass through)
    if raw_input is not None:
        return raw_input

    # Handle regular message
    if message is not None:
        return {"messages": [{"role": "user", "content": message}]}

    # Handle resume from interrupt
    if decisions is not None:
        from langgraph.types import Command
        return Command(resume={"decisions": decisions})


def stream_graph_updates(
    agent,
    input_data: Any,
    config: Optional[Dict[str, Any]] = None,
    stream_mode: str = "updates"
) -> Iterator[Dict[str, Any]]:
    """
    Stream updates from a LangGraph agent.

    This is a generic function that handles:
    - Regular message streaming
    - Interrupt detection and processing
    - Special tool handling (think_tool, write_todos)
    - Tool call serialization

    Args:
        agent: The LangGraph agent/graph instance
        input_data: Input data for the agent (can be dict, Command, or any agent input)
        config: Optional configuration for the agent
        stream_mode: Stream mode for LangGraph (default: "updates")

    Yields:
        Dictionaries containing:
        - {"chunk": str, "status": "streaming"} for text content
        - {"tool_calls": list, "status": "streaming"} for tool calls
        - {"todo_list": list, "status": "streaming"} for todos
        - {"interrupt": dict, "status": "interrupt"} for interrupts
        - {"status": "complete"} when finished
        - {"error": str, "status": "error"} on errors
    """
    try:
        for update in agent.stream(input_data, config=config, stream_mode=stream_mode):
            # Check for interrupts
            if isinstance(update, dict) and "__interrupt__" in update:
                interrupt_data = process_interrupt(update["__interrupt__"])
                yield {
                    "interrupt": interrupt_data,
                    "status": "interrupt"
                }
                continue

            # Process regular updates
            if isinstance(update, dict):
                for node_name, state_data in update.items():
                    # Extract message content from the state update
                    if isinstance(state_data, dict) and "messages" in state_data:
                        messages = state_data["messages"]
                        if not messages:
                            continue

                        # Get the last message in this update
                        last_message = messages[-1] if isinstance(messages, list) else messages
                        message_type = last_message.__class__.__name__ if hasattr(last_message, '__class__') else None

                        # Handle ToolMessage (tool outputs)
                        if message_type == 'ToolMessage':
                            result = process_tool_message(last_message)
                            if result:
                                yield result

                        # Handle regular messages (including AIMessage with tool calls)
                        elif hasattr(last_message, 'content'):
                            for chunk in process_ai_message(last_message, node_name):
                                yield chunk

        yield {"status": "complete"}

    except Exception as e:
        yield {
            "error": f"Error streaming from agent: {str(e)}",
            "status": "error"
        }


def resume_graph_from_interrupt(
    agent,
    decisions: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    stream_mode: str = "updates"
) -> Iterator[Dict[str, Any]]:
    """
    Resume a LangGraph agent from an interrupt.

    This is a convenience wrapper around stream_graph_updates that prepares
    the resume input automatically.

    Args:
        agent: The LangGraph agent/graph instance
        decisions: List of decision objects with 'type' and optional fields
        config: Optional configuration for the agent
        stream_mode: Stream mode for LangGraph (default: "updates")

    Yields:
        Same format as stream_graph_updates
    """
    try:
        # Prepare resume input using the generic function
        resume_input = prepare_agent_input(decisions=decisions)

        # Use the same streaming logic as regular streaming
        for chunk in stream_graph_updates(agent, resume_input, config=config, stream_mode=stream_mode):
            yield chunk

    except Exception as e:
        yield {
            "error": f"Error resuming from interrupt: {str(e)}",
            "status": "error"
        }


# ============================================================================
# ASYNC VARIANTS
# ============================================================================


async def astream_graph_updates(
    agent,
    input_data: Any,
    config: Optional[Dict[str, Any]] = None,
    stream_mode: str = "updates"
) -> AsyncIterator[Dict[str, Any]]:
    """
    Async version of stream_graph_updates.

    Supports both stream_mode="updates" (granular) and "values" (simpler).

    Args:
        agent: The LangGraph agent/graph instance
        input_data: Input data for the agent (can be dict, Command, or any agent input)
        config: Optional configuration for the agent
        stream_mode: Stream mode for LangGraph (default: "updates")

    Yields:
        Dictionaries containing:
        - {"chunk": str, "status": "streaming"} for text content
        - {"tool_calls": list, "status": "streaming"} for tool calls
        - {"todo_list": list, "status": "streaming"} for todos
        - {"interrupt": dict, "status": "interrupt"} for interrupts
        - {"status": "complete"} when finished
        - {"error": str, "status": "error"} on errors
    """
    try:
        async for update in agent.astream(input_data, config=config, stream_mode=stream_mode):
            # Check for interrupts
            if isinstance(update, dict) and "__interrupt__" in update:
                interrupt_data = process_interrupt(update["__interrupt__"])
                yield {
                    "interrupt": interrupt_data,
                    "status": "interrupt"
                }
                continue

            # Process regular updates
            if isinstance(update, dict):
                for node_name, state_data in update.items():
                    # Extract message content from the state update
                    if isinstance(state_data, dict) and "messages" in state_data:
                        messages = state_data["messages"]
                        if not messages:
                            continue

                        # Get the last message in this update
                        last_message = messages[-1] if isinstance(messages, list) else messages
                        message_type = last_message.__class__.__name__ if hasattr(last_message, '__class__') else None

                        # Handle ToolMessage (tool outputs)
                        if message_type == 'ToolMessage':
                            result = process_tool_message(last_message)
                            if result:
                                yield result

                        # Handle regular messages (including AIMessage with tool calls)
                        elif hasattr(last_message, 'content'):
                            for chunk in process_ai_message(last_message, node_name):
                                yield chunk

        yield {"status": "complete"}

    except Exception as e:
        yield {
            "error": f"Error streaming from agent: {str(e)}",
            "status": "error"
        }


async def aresume_graph_from_interrupt(
    agent,
    decisions: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    stream_mode: str = "updates"
) -> AsyncIterator[Dict[str, Any]]:
    """
    Async version of resume_graph_from_interrupt.

    Resume a LangGraph agent from an interrupt asynchronously.

    Args:
        agent: The LangGraph agent/graph instance
        decisions: List of decision objects with 'type' and optional fields
        config: Optional configuration for the agent
        stream_mode: Stream mode for LangGraph (default: "updates")

    Yields:
        Same format as astream_graph_updates
    """
    try:
        # Prepare resume input using the generic function
        resume_input = prepare_agent_input(decisions=decisions)

        # Use the same streaming logic as regular async streaming
        async for chunk in astream_graph_updates(agent, resume_input, config=config, stream_mode=stream_mode):
            yield chunk

    except Exception as e:
        yield {
            "error": f"Error resuming from interrupt: {str(e)}",
            "status": "error"
        }
