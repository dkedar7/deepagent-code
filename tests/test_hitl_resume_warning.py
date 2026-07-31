"""Answering a plain-string ``interrupt()`` must NOT leak ag_ui_langgraph's benign
"failed to parse resume_input as JSON" WARNING to the console (gh #103).

On the interactive HITL path, every free-text response to a plain-string
``interrupt(...)`` made the bundled ``ag_ui_langgraph`` dep log an error-looking
WARNING right above the (correct) answer. The value was always right; the line was
pure confusing noise. The CLI drops ONLY that one record, surgically, so no other
warning is ever hidden — and it stays cli-local (the CLI owns its console UX).
"""

import io
import logging
import textwrap
from contextlib import redirect_stdout

import pytest

pytest.importorskip("ag_ui_langgraph")
pytest.importorskip("fastapi")

from langstage_cli import cli  # noqa: E402
from langstage_cli.agui_stream import build_session_agent  # noqa: E402
from langstage_cli.cli import _DropResumeJSONWarning, run_single_turn_agui  # noqa: E402

# The issue's canonical plain-string interrupt agent: a node does
# `answer = interrupt("What is your favorite color?")` and echoes it back.
_HITL_AGENT = textwrap.dedent(
    """
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import MessagesState
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import interrupt
    from langchain_core.messages import AIMessage

    def ask(state):
        answer = interrupt("What is your favorite color?")
        return {"messages": [AIMessage(content=f"You chose: {answer}")]}

    g = StateGraph(MessagesState)
    g.add_node("ask", ask)
    g.add_edge(START, "ask")
    g.add_edge("ask", END)
    graph = g.compile(checkpointer=MemorySaver())
    """
)


class _Capture(logging.Handler):
    """Records the messages of every log record that reaches it."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


async def test_free_text_resume_does_not_leak_the_json_parse_warning(monkeypatch):
    ns: dict = {}
    exec(_HITL_AGENT, ns)
    agent = build_session_agent(ns["graph"])

    # Simulate the interactive HITL menu: a real terminal, user picks "Provide a
    # response", and types free text `blue` (not valid JSON — the noisy case).
    monkeypatch.setattr(cli, "_is_a_tty", lambda *a, **k: True)
    monkeypatch.setattr(cli, "select_option", lambda *a, **k: 0)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "blue")

    # Capture anything the emitting logger would send to the console.
    logger = logging.getLogger("ag_ui_langgraph.agent")
    cap = _Capture()
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(cap)

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            _elapsed, had_error = await run_single_turn_agui(
                agent, "start", "t-color", interactive=True
            )
    finally:
        logger.removeHandler(cap)
        logger.setLevel(old_level)

    out = buf.getvalue()
    assert had_error is False, out
    # The resumed value is still correct...
    assert "You chose: blue" in out, out
    # ...and the benign warning was dropped at the logger, never reaching a handler.
    assert not any("failed to parse resume_input as JSON" in m for m in cap.messages), cap.messages


def test_filter_drops_only_the_resume_warning():
    # Unit-level guard that the filter is surgical: it drops the one benign record and
    # lets every other warning through.
    filt = _DropResumeJSONWarning()

    def record(msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            "ag_ui_langgraph.agent", logging.WARNING, __file__, 1, msg, None, None
        )

    assert (
        filt.filter(record("failed to parse resume_input as JSON, treating as string (x)")) is False
    )
    assert filt.filter(record("some other important warning")) is True
