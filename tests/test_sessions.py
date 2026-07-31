"""First-class cross-invocation session persistence: --continue / --resume (gh #102).

Every invocation used to start amnesiac (an in-memory checkpointer thrown away at
process exit). The CLI now attaches a durable per-workspace SQLite checkpointer itself
so a fresh run is persisted and a later `--continue` (most recent) or `--resume <id>`
(a specific thread) picks the conversation back up — no user-supplied checkpointer, no
graph edits. Tests are hermetic: the autouse `_hermetic_sessions` fixture points the
session store at a temp dir, and each test isolates the global config home.
"""

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

pytest.importorskip("ag_ui_langgraph")
pytest.importorskip("fastapi")
pytest.importorskip("langgraph.checkpoint.sqlite.aio")

from langstage_cli import sessions  # noqa: E402
from langstage_cli.cli import main  # noqa: E402

# A keyless, deterministic agent that ECHOES prior state: it reports the FIRST human
# message it can see. A second invocation that still reports the first turn's fact proves
# memory persisted across processes (separate SqliteSaver opens over the same file).
_ECHO_AGENT = textwrap.dedent(
    """
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import MessagesState
    from langchain_core.messages import AIMessage

    def respond(state):
        first = ""
        for m in state["messages"]:
            if getattr(m, "type", "") == "human":
                first = m.content
                break
        return {"messages": [AIMessage(content=f"first fact: {first}")]}

    g = StateGraph(MessagesState)
    g.add_node("respond", respond)
    g.add_edge(START, "respond")
    g.add_edge("respond", END)
    graph = g.compile()
    """
)


def _setup(runner_fs: str, monkeypatch, tmp_path) -> None:
    """Write the echo agent + langstage.toml into the isolated fs and isolate config."""
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path / "empty_home"))
    (Path(runner_fs) / "echo_agent.py").write_text(_ECHO_AGENT)
    (Path(runner_fs) / "langstage.toml").write_text('[agent]\nspec = "echo_agent.py:graph"\n')


def test_continue_recalls_the_earlier_turn(monkeypatch, tmp_path):
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        _setup(fs, monkeypatch, tmp_path)
        # Turn 1 (fresh, persisted): establish a fact.
        one = r.invoke(main, ["--no-interactive", "my name is Kedar"])
        assert one.exit_code == 0, one.output
        assert "first fact: my name is Kedar" in one.output

        # Turn 2 (--continue): a SEPARATE invocation still sees the earlier turn's
        # content — memory persisted across processes via the durable store.
        two = r.invoke(main, ["-c", "--no-interactive", "what did I say?"])
        assert two.exit_code == 0, two.output
        assert "first fact: my name is Kedar" in two.output


def test_fresh_run_starts_empty(monkeypatch, tmp_path):
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        _setup(fs, monkeypatch, tmp_path)
        r.invoke(main, ["--no-interactive", "my name is Kedar"])
        # A run WITHOUT --continue is a brand-new session: it can only see its own turn.
        fresh = r.invoke(main, ["--no-interactive", "a totally new topic"])
        assert fresh.exit_code == 0, fresh.output
        assert "first fact: a totally new topic" in fresh.output


def test_resume_targets_a_specific_thread(monkeypatch, tmp_path):
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        _setup(fs, monkeypatch, tmp_path)
        r.invoke(main, ["--no-interactive", "session A fact"])  # session A
        r.invoke(main, ["--no-interactive", "session B fact"])  # session B (most recent)

        workspace = Path(fs).resolve()
        rows = sessions.list_sessions(workspace)
        a_tid = next(t for t, e in rows if e["first_message"] == "session A fact")

        # --resume <id> continues THAT thread, even though B is the most recent.
        res = r.invoke(main, ["--resume", a_tid, "--no-interactive", "back to A"])
        assert res.exit_code == 0, res.output
        assert "first fact: session A fact" in res.output


def test_continue_with_no_prior_starts_fresh_without_error(monkeypatch, tmp_path):
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        _setup(fs, monkeypatch, tmp_path)
        # --continue with nothing to continue must NOT error — it starts fresh + notes it.
        res = r.invoke(main, ["-c", "--no-interactive", "hello"])
        assert res.exit_code == 0, res.output
        assert "first fact: hello" in res.output
        assert "No prior session" in res.output


def test_continue_and_resume_are_mutually_exclusive(monkeypatch, tmp_path):
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        _setup(fs, monkeypatch, tmp_path)
        res = r.invoke(main, ["-c", "--resume", "abc", "--no-interactive", "hi"])
        assert res.exit_code != 0
        assert "mutually exclusive" in res.output


def test_no_persist_disables_persistence(monkeypatch, tmp_path):
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        _setup(fs, monkeypatch, tmp_path)
        r.invoke(main, ["--no-persist", "--no-interactive", "remember me"])
        # Nothing was recorded, so --continue finds no prior session.
        res = r.invoke(main, ["-c", "--no-interactive", "still here?"])
        assert "No prior session" in res.output


# ---- sessions module unit tests ----


def test_sessions_index_records_and_resolves(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSTAGE_CLI_SESSIONS_DIR", str(tmp_path / "store"))
    ws = tmp_path / "ws"
    ws.mkdir()

    sessions.record_session(ws, "thread-aaaa1111", first_message="hello world")
    sessions.record_session(ws, "thread-bbbb2222", first_message="second one")

    # most_recent is the last-updated; touch bumps it.
    sessions.touch_session(ws, "thread-aaaa1111")
    assert sessions.most_recent_thread(ws) == "thread-aaaa1111"

    # exact + unambiguous-prefix resolution; ambiguous/unknown -> None.
    assert sessions.resolve_thread(ws, "thread-bbbb2222") == "thread-bbbb2222"
    assert sessions.resolve_thread(ws, "thread-aaaa") == "thread-aaaa1111"
    assert sessions.resolve_thread(ws, "thread-") is None  # ambiguous
    assert sessions.resolve_thread(ws, "nope") is None

    # snippet of the first message is retained.
    rows = dict(sessions.list_sessions(ws))
    assert rows["thread-aaaa1111"]["first_message"] == "hello world"


def test_sessions_are_keyed_per_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSTAGE_CLI_SESSIONS_DIR", str(tmp_path / "store"))
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    sessions.record_session(ws1, "t-1", first_message="in ws1")
    # A different workspace has its own, independent index.
    assert sessions.most_recent_thread(ws2) is None
    assert sessions.db_path(ws1) != sessions.db_path(ws2)
