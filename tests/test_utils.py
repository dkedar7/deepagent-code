"""Tests for utility functions."""
import pytest
import json
from langgraph_utils_cli.utils import (
    parse_interrupt_value,
    serialize_action_request,
    serialize_review_config,
    process_interrupt,
    extract_todos_from_content,
    extract_reflection_from_content,
    serialize_tool_calls,
    clean_content_from_tool_dicts,
    process_message_content,
    process_tool_message,
    process_ai_message,
    prepare_agent_input,
    stream_graph_updates,
    resume_graph_from_interrupt,
)


class TestParseInterruptValue:
    """Tests for parse_interrupt_value function."""

    def test_tuple_format_two_elements(self):
        """Test parsing two-element tuple format."""
        action_requests = [{"tool": "test_tool", "args": {}}]
        review_configs = [{"allowed_decisions": ["approve", "reject"]}]
        interrupt_value = (action_requests, review_configs)

        actions, configs = parse_interrupt_value(interrupt_value)

        assert actions == action_requests
        assert configs == review_configs

    def test_tuple_format_single_element_with_dict(self):
        """Test parsing single-element tuple with dict value."""

        class MockInterrupt:
            def __init__(self):
                self.value = {
                    "action_requests": [{"tool": "test"}],
                    "review_configs": [{"allowed_decisions": ["approve"]}],
                }

        interrupt_value = (MockInterrupt(),)
        actions, configs = parse_interrupt_value(interrupt_value)

        assert len(actions) == 1
        assert actions[0]["tool"] == "test"
        assert len(configs) == 1


class TestSerializeActionRequest:
    """Tests for serialize_action_request function."""

    def test_dict_format(self):
        """Test serializing dict format action."""
        action = {
            "tool": "test_tool",
            "tool_call_id": "call_123",
            "args": {"param": "value"},
            "description": "Test action",
        }

        result = serialize_action_request(action, index=0)

        assert result["tool"] == "test_tool"
        assert result["tool_call_id"] == "call_123"
        assert result["args"] == {"param": "value"}
        assert result["description"] == "Test action"

    def test_object_format(self):
        """Test serializing object format action."""

        class MockAction:
            tool = "test_tool"
            tool_call_id = "call_123"
            args = {"param": "value"}
            description = "Test action"

        result = serialize_action_request(MockAction(), index=0)

        assert result["tool"] == "test_tool"
        assert result["tool_call_id"] == "call_123"

    def test_fallback_tool_call_id(self):
        """Test fallback tool_call_id generation."""
        action = {"tool": "test_tool", "args": {}}

        result = serialize_action_request(action, index=5)

        assert result["tool_call_id"] == "call_5"


class TestExtractTodosFromContent:
    """Tests for extract_todos_from_content function."""

    def test_string_with_array(self):
        """Test extracting from string with array."""
        content = "Updated todo list to [{'content': 'Task 1', 'status': 'pending'}]"

        result = extract_todos_from_content(content)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["content"] == "Task 1"

    def test_dict_format(self):
        """Test extracting from dict format."""
        content = {"todos": [{"content": "Task 1", "status": "pending"}]}

        result = extract_todos_from_content(content)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_list_format(self):
        """Test extracting from direct list."""
        content = [{"content": "Task 1", "status": "pending"}]

        result = extract_todos_from_content(content)

        assert result == content


class TestSerializeToolCalls:
    """Tests for serialize_tool_calls function."""

    def test_basic_serialization(self):
        """Test basic tool call serialization."""

        class MockToolCall:
            id = "call_123"
            name = "test_tool"
            args = {"param": "value"}

        tool_calls = [MockToolCall()]
        result = serialize_tool_calls(tool_calls)

        assert len(result) == 1
        assert result[0]["id"] == "call_123"
        assert result[0]["name"] == "test_tool"

    def test_skip_tools(self):
        """Test skipping specified tools."""

        class MockToolCall:
            def __init__(self, name):
                self.id = f"call_{name}"
                self.name = name
                self.args = {}

        tool_calls = [
            MockToolCall("think_tool"),
            MockToolCall("execute_tool"),
            MockToolCall("write_todos"),
        ]

        result = serialize_tool_calls(tool_calls, skip_tools=["think_tool", "write_todos"])

        assert len(result) == 1
        assert result[0]["name"] == "execute_tool"


class TestPrepareAgentInput:
    """Tests for prepare_agent_input function."""

    def test_message_input(self):
        """Test preparing message input."""
        result = prepare_agent_input(message="Hello, agent!")

        assert "messages" in result
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == "Hello, agent!"

    def test_decisions_input(self):
        """Test preparing decisions input."""
        decisions = [{"type": "approve"}]

        result = prepare_agent_input(decisions=decisions)

        # Should return a Command object
        assert hasattr(result, "resume")

    def test_raw_input(self):
        """Test preparing raw input."""
        raw = {"custom": "data"}

        result = prepare_agent_input(raw_input=raw)

        assert result == raw

    def test_no_input_raises_error(self):
        """Test that no input raises ValueError."""
        with pytest.raises(ValueError, match="Must provide one of"):
            prepare_agent_input()

    def test_multiple_inputs_raises_error(self):
        """Test that multiple inputs raise ValueError."""
        with pytest.raises(ValueError, match="Can only provide one of"):
            prepare_agent_input(message="Hello", decisions=[])


class TestProcessInterrupt:
    """Tests for process_interrupt function."""

    def test_full_interrupt_processing(self):
        """Test complete interrupt processing."""
        action_requests = [
            {"tool": "test_tool", "tool_call_id": "call_1", "args": {"param": "value"}}
        ]
        review_configs = [{"allowed_decisions": ["approve", "reject"]}]
        interrupt_value = (action_requests, review_configs)

        result = process_interrupt(interrupt_value)

        assert "action_requests" in result
        assert "review_configs" in result
        assert len(result["action_requests"]) == 1
        assert result["action_requests"][0]["tool"] == "test_tool"
        assert len(result["review_configs"]) == 1


class TestSerializeReviewConfig:
    """Tests for serialize_review_config function."""

    def test_dict_format(self):
        """Test serializing dict format config."""
        config = {"allowed_decisions": ["approve", "reject"]}

        result = serialize_review_config(config)

        assert "allowed_decisions" in result
        assert result["allowed_decisions"] == ["approve", "reject"]

    def test_object_format(self):
        """Test serializing object format config."""

        class MockConfig:
            allowed_decisions = ["approve", "reject", "modify"]

        result = serialize_review_config(MockConfig())

        assert result["allowed_decisions"] == ["approve", "reject", "modify"]

    def test_empty_config(self):
        """Test empty config."""
        config = {}

        result = serialize_review_config(config)

        assert result["allowed_decisions"] == []


class TestExtractReflectionFromContent:
    """Tests for extract_reflection_from_content function."""

    def test_string_format(self):
        """Test extracting from plain string."""
        content = "This is a reflection"

        result = extract_reflection_from_content(content)

        assert result == "This is a reflection"

    def test_json_string_format(self):
        """Test extracting from JSON string."""
        content = '{"reflection": "This is my reflection"}'

        result = extract_reflection_from_content(content)

        assert result == "This is my reflection"

    def test_dict_format(self):
        """Test extracting from dict format."""
        content = {"reflection": "This is my reflection"}

        result = extract_reflection_from_content(content)

        assert result == "This is my reflection"

    def test_invalid_json(self):
        """Test with invalid JSON falls back to plain string."""
        content = "{invalid json"

        result = extract_reflection_from_content(content)

        assert result == "{invalid json"


class TestCleanContentFromToolDicts:
    """Tests for clean_content_from_tool_dicts function."""

    def test_removes_tool_dict(self):
        """Test removing tool call dictionary from content."""
        content = "Some text {'id': 'call_123', 'input': {'param': 'value'}, 'name': 'tool_name', 'type': 'tool_use'} more text"

        result = clean_content_from_tool_dicts(content)

        assert "{'id':" not in result
        assert "Some text" in result
        assert "more text" in result

    def test_no_tool_dict(self):
        """Test content without tool dict remains unchanged."""
        content = "Just regular content"

        result = clean_content_from_tool_dicts(content)

        assert result == "Just regular content"

    def test_empty_string(self):
        """Test empty string."""
        result = clean_content_from_tool_dicts("")

        assert result == ""


class TestProcessMessageContent:
    """Tests for process_message_content function."""

    def test_string_content(self):
        """Test processing string content."""

        class MockMessage:
            content = "Hello, world!"

        result = process_message_content(MockMessage())

        assert result == "Hello, world!"

    def test_list_content(self):
        """Test processing list of content blocks."""

        class MockMessage:
            content = [
                {"text": "Hello", "type": "text"},
                {"text": "World", "type": "text"},
            ]

        result = process_message_content(MockMessage())

        assert "Hello" in result
        assert "World" in result

    def test_no_content_attribute(self):
        """Test message without content attribute."""

        class MockMessage:
            pass

        result = process_message_content(MockMessage())

        assert result == ""

    def test_other_type_content(self):
        """Test content of other types."""

        class MockMessage:
            content = 123

        result = process_message_content(MockMessage())

        assert result == "123"


class TestProcessToolMessage:
    """Tests for process_tool_message function."""

    def test_think_tool_message(self):
        """Test processing think_tool message."""

        class MockMessage:
            name = "think_tool"
            content = '{"reflection": "My thoughts"}'

        result = process_tool_message(MockMessage())

        assert result is not None
        assert result["chunk"] == "My thoughts"
        assert result["status"] == "streaming"

    def test_write_todos_message(self):
        """Test processing write_todos message."""

        class MockMessage:
            name = "write_todos"
            content = [{"content": "Task 1", "status": "pending"}]

        result = process_tool_message(MockMessage())

        assert result is not None
        assert "todo_list" in result
        assert len(result["todo_list"]) == 1
        assert result["status"] == "streaming"

    def test_other_tool_message(self):
        """Test processing other tool messages."""

        class MockMessage:
            name = "execute_tool"
            content = "Tool output"

        result = process_tool_message(MockMessage())

        assert result is None

    def test_no_name_attribute(self):
        """Test message without name attribute."""

        class MockMessage:
            content = "Some content"

        result = process_tool_message(MockMessage())

        assert result is None


class TestProcessAIMessage:
    """Tests for process_ai_message function."""

    def test_message_with_content(self):
        """Test processing AI message with content."""

        class MockMessage:
            content = "Hello from AI"
            tool_calls = []

        chunks = list(process_ai_message(MockMessage(), "test_node"))

        assert len(chunks) == 1
        assert chunks[0]["chunk"] == "Hello from AI"
        assert chunks[0]["node"] == "test_node"
        assert chunks[0]["status"] == "streaming"

    def test_message_with_tool_calls(self):
        """Test processing AI message with tool calls."""

        class MockToolCall:
            id = "call_123"
            name = "test_tool"
            args = {"param": "value"}

        class MockMessage:
            content = ""
            tool_calls = [MockToolCall()]

        chunks = list(process_ai_message(MockMessage(), "test_node"))

        assert len(chunks) == 1
        assert "tool_calls" in chunks[0]
        assert len(chunks[0]["tool_calls"]) == 1
        assert chunks[0]["tool_calls"][0]["name"] == "test_tool"

    def test_message_with_content_and_tool_calls(self):
        """Test processing AI message with both content and tool calls."""

        class MockToolCall:
            id = "call_123"
            name = "execute_tool"
            args = {}

        class MockMessage:
            content = "Executing tool"
            tool_calls = [MockToolCall()]

        chunks = list(process_ai_message(MockMessage(), "test_node"))

        # Should have 2 chunks: one for tool calls, one for content
        assert len(chunks) == 2

    def test_skip_tools_filter(self):
        """Test skipping specified tools."""

        class MockToolCall:
            def __init__(self, name):
                self.id = f"call_{name}"
                self.name = name
                self.args = {}

        class MockMessage:
            content = ""
            tool_calls = [
                MockToolCall("think_tool"),
                MockToolCall("execute_tool"),
            ]

        chunks = list(process_ai_message(MockMessage(), "test_node", skip_tools=["think_tool"]))

        # Should only have 1 tool call (execute_tool)
        assert len(chunks) == 1
        assert len(chunks[0]["tool_calls"]) == 1
        assert chunks[0]["tool_calls"][0]["name"] == "execute_tool"

    def test_empty_content_not_yielded(self):
        """Test that empty content is not yielded."""

        class MockMessage:
            content = "   "  # Only whitespace
            tool_calls = []

        chunks = list(process_ai_message(MockMessage(), "test_node"))

        assert len(chunks) == 0


class TestStreamGraphUpdates:
    """Integration tests for stream_graph_updates function."""

    def test_simple_graph_execution(self):
        """Test streaming from a simple graph."""

        class MockMessage:
            content = "Response from agent"
            tool_calls = []

            def __init__(self):
                pass

        class MockGraph:
            def stream(self, input_data, config=None, stream_mode="updates"):
                # Simulate a simple update
                yield {
                    "agent_node": {
                        "messages": [MockMessage()]
                    }
                }

        graph = MockGraph()
        input_data = {"messages": [{"role": "user", "content": "Hello"}]}

        chunks = list(stream_graph_updates(graph, input_data))

        # Should have 2 chunks: content + complete
        assert len(chunks) >= 2
        assert any(c.get("status") == "complete" for c in chunks)
        assert any(c.get("chunk") == "Response from agent" for c in chunks)

    def test_graph_with_interrupt(self):
        """Test handling interrupts from graph."""

        class MockGraph:
            def stream(self, input_data, config=None, stream_mode="updates"):
                # Simulate an interrupt
                yield {
                    "__interrupt__": (
                        [{"tool": "test_tool", "tool_call_id": "call_1", "args": {}}],
                        [{"allowed_decisions": ["approve", "reject"]}],
                    )
                }

        graph = MockGraph()
        input_data = {"messages": [{"role": "user", "content": "Hello"}]}

        chunks = list(stream_graph_updates(graph, input_data))

        # Should have interrupt chunk and complete chunk
        interrupt_chunks = [c for c in chunks if c.get("status") == "interrupt"]
        assert len(interrupt_chunks) == 1
        assert "interrupt" in interrupt_chunks[0]
        assert "action_requests" in interrupt_chunks[0]["interrupt"]

    def test_graph_error_handling(self):
        """Test error handling in stream."""

        class MockGraph:
            def stream(self, input_data, config=None, stream_mode="updates"):
                raise Exception("Test error")

        graph = MockGraph()
        input_data = {"messages": [{"role": "user", "content": "Hello"}]}

        chunks = list(stream_graph_updates(graph, input_data))

        # Should yield error chunk
        error_chunks = [c for c in chunks if c.get("status") == "error"]
        assert len(error_chunks) == 1
        assert "error" in error_chunks[0]
        assert "Test error" in error_chunks[0]["error"]


class TestResumeGraphFromInterrupt:
    """Tests for resume_graph_from_interrupt function."""

    def test_resume_with_decisions(self):
        """Test resuming graph with decisions."""

        class MockMessage:
            content = "Resumed successfully"
            tool_calls = []

        class MockGraph:
            def stream(self, input_data, config=None, stream_mode="updates"):
                # Check that we received a Command object
                if hasattr(input_data, 'resume'):
                    yield {
                        "agent_node": {
                            "messages": [MockMessage()]
                        }
                    }

        graph = MockGraph()
        decisions = [{"type": "approve"}]

        chunks = list(resume_graph_from_interrupt(graph, decisions))

        # Should have content chunk and complete chunk
        assert len(chunks) >= 2
        assert any(c.get("chunk") == "Resumed successfully" for c in chunks)
        assert any(c.get("status") == "complete" for c in chunks)


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_parse_interrupt_value_with_object_attributes(self):
        """Test parsing interrupt value with object attributes."""

        class MockInterrupt:
            action_requests = [{"tool": "test"}]
            review_configs = [{"allowed_decisions": ["approve"]}]

        actions, configs = parse_interrupt_value(MockInterrupt())

        assert len(actions) == 1
        assert len(configs) == 1

    def test_serialize_action_request_with_name_field(self):
        """Test serializing action with 'name' field instead of 'tool'."""
        action = {
            "name": "test_tool",  # Using 'name' instead of 'tool'
            "args": {}
        }

        result = serialize_action_request(action, 0)

        assert result["tool"] == "test_tool"

    def test_extract_todos_json_string_format(self):
        """Test extracting todos from JSON string format."""
        content = '[{"content": "Task 1", "status": "pending"}]'

        result = extract_todos_from_content(content)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_extract_todos_nested_json(self):
        """Test extracting todos with nested JSON string."""
        content = {"todos": '[{"content": "Task 1", "status": "pending"}]'}

        result = extract_todos_from_content(content)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_serialize_tool_calls_dict_format(self):
        """Test serializing tool calls in dict format."""
        tool_calls = [
            {"id": "call_123", "name": "test_tool", "args": {"param": "value"}}
        ]

        result = serialize_tool_calls(tool_calls)

        assert len(result) == 1
        assert result[0]["name"] == "test_tool"

    def test_process_message_content_empty_list(self):
        """Test processing message with empty content list."""

        class MockMessage:
            content = []

        result = process_message_content(MockMessage())

        assert result == ""

    def test_tool_calls_with_no_skip_tools(self):
        """Test tool call serialization with no skip_tools."""

        class MockToolCall:
            id = "call_123"
            name = "think_tool"
            args = {}

        result = serialize_tool_calls([MockToolCall()], skip_tools=None)

        assert len(result) == 1  # Should include think_tool when skip_tools is None

    def test_prepare_agent_input_with_none_values(self):
        """Test error handling when passing None explicitly."""
        with pytest.raises(ValueError):
            prepare_agent_input(message=None, decisions=None, raw_input=None)
