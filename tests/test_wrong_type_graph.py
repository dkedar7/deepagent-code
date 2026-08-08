"""gh #117: a wrong-type agent object gets build_agent's clean TypeError on the
DEFAULT (persist-on) run path, not a cryptic leaked internal AttributeError.

The default path attaches a durable AsyncSqliteSaver (gh #102) by setting
`graph.checkpointer` BEFORE `build_agent` validates the graph. For `graph = None`
(a placeholder, a construction that fell through, or `-a` pointed at the wrong
attribute) that attribute-set raised first, leaking
`AttributeError: 'NoneType' object has no attribute 'checkpointer'`. `--verify` and
`--no-persist` already reached build_agent's clean, actionable message — the default
config, which every user hits, must too.
"""

from click.testing import CliRunner

from langstage_cli.cli import main


def test_none_graph_default_path_shows_clean_typeerror(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path / "empty_home"))
    (tmp_path / "nonegraph.py").write_text("graph = None\n")
    monkeypatch.chdir(tmp_path)

    # DEFAULT config: persistence ON (no --no-persist / --verify).
    r = CliRunner().invoke(main, ["-a", "nonegraph.py:graph", "--no-interactive", "hi"])

    assert r.exit_code != 0, r.output
    # build_agent's clean, actionable validator message — the same one --verify shows.
    assert "build_agent expected a compiled LangGraph graph" in r.output, r.output
    assert "but got NoneType" in r.output, r.output
    # The cryptic internal leak must be gone.
    assert "has no attribute 'checkpointer'" not in r.output, r.output
