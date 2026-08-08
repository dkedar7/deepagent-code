"""Relative agent-spec resolution vs the workspace-root chdir (gh #30).

The CLI chdirs into LANGSTAGE_WORKSPACE_ROOT before loading the agent, so a
relative `-a my_agent.py:graph` must be anchored to the invocation cwd up front
— otherwise it's looked up under the workspace root and fails "file not found"
for a file sitting in the user's current directory.
"""

from click.testing import CliRunner

from langstage_cli.cli import _absolutize_file_spec, main

_AGENT_SRC = (
    "from langgraph.graph import StateGraph, START, END, MessagesState\n"
    "from langchain_core.messages import AIMessage\n"
    "def respond(state):\n"
    "    return {'messages': [AIMessage(content='hi from my_agent')]}\n"
    "g = StateGraph(MessagesState); g.add_node('respond', respond)\n"
    "g.add_edge(START, 'respond'); g.add_edge('respond', END)\n"
    "graph = g.compile()\n"
)


def test_absolutize_resolves_relative_py(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = _absolutize_file_spec("my_agent.py:graph")
    assert out == f"{(tmp_path / 'my_agent.py').resolve()}:graph"


def test_absolutize_bare_py_keeps_no_suffix(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = _absolutize_file_spec("my_agent.py")
    assert out == str((tmp_path / "my_agent.py").resolve())
    assert not out.endswith(":")


def test_absolutize_leaves_module_specs_untouched():
    assert _absolutize_file_spec("pkg.mod:graph") == "pkg.mod:graph"
    assert _absolutize_file_spec("langstage_hermes.agent:graph") == "langstage_hermes.agent:graph"


def test_absolutize_idempotent_on_absolute(tmp_path):
    abs_spec = f"{(tmp_path / 'a.py').resolve()}:graph"
    assert _absolutize_file_spec(abs_spec) == abs_spec


def test_relative_spec_with_workspace_root_resolves_against_cwd(tmp_path, monkeypatch):
    # The exact issue scenario: relative spec in cwd, workspace root elsewhere.
    proj = tmp_path / "proj"
    proj.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (proj / "my_agent.py").write_text(_AGENT_SRC)
    monkeypatch.chdir(proj)

    r = CliRunner().invoke(
        main,
        ["-a", "my_agent.py:graph", "--no-interactive", "hi"],
        env={"LANGSTAGE_WORKSPACE_ROOT": str(elsewhere)},
    )
    assert r.exit_code == 0, r.output
    assert "hi from my_agent" in r.output
    assert "not found" not in r.output.lower()


# ── gh #116: a RELATIVE spec from a walked-up langstage.toml resolves against the
# toml's own directory (the project root), so an init-scaffolded project runs from
# any subdirectory — not just its root. Distinct from #30 (a -a/env spec stays
# cwd-relative), which the tests above and below pin. ──────────────────────────


def test_toml_relative_spec_resolves_against_toml_dir_from_subdir(tmp_path, monkeypatch):
    """gh #116: the documented `init` scaffold runs from a subdir, not just its root.

    `init` writes a RELATIVE `agent.spec` ("my_agent.py:graph") at the project root.
    Config discovery walks UP to find that langstage.toml from a subdir, so the spec
    must resolve against the toml's OWN directory (the project root) — not the process
    cwd — else the run crashes `Agent file not found` from any subdirectory.
    """
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path / "empty_home"))
    proj = tmp_path / "proj"
    proj.mkdir()

    # Scaffold the documented init project at the root (my_agent.py + langstage.toml).
    monkeypatch.chdir(proj)
    assert CliRunner().invoke(main, ["init"]).exit_code == 0

    # From the project ROOT the run already works today...
    monkeypatch.chdir(proj)
    r_root = CliRunner().invoke(main, ["--no-interactive", "hello from root"])
    assert r_root.exit_code == 0, r_root.output
    assert "You said: hello from root" in r_root.output

    # ...and from a normal SUBDIR of the same project it must work too (the bug).
    sub = proj / "src"
    sub.mkdir()
    monkeypatch.chdir(sub)
    r_sub = CliRunner().invoke(main, ["--no-interactive", "hello from src"])
    assert r_sub.exit_code == 0, r_sub.output
    assert "You said: hello from src" in r_sub.output
    assert "not found" not in r_sub.output.lower()


def test_dash_a_relative_spec_stays_cwd_relative_from_subdir(tmp_path, monkeypatch):
    """gh #116 control: `-a` keeps #30's cwd-relative base even beside a langstage.toml.

    Only TOML-sourced specs rebase onto the toml dir; a spec the user types on the
    command line resolves against where they typed it. Here the toml points at a
    DIFFERENT file at the root, but `-a my_agent.py:graph` from a subdir loads the
    subdir's file — proving the -a base is the cwd, not the toml dir.
    """
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path / "empty_home"))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "langstage.toml").write_text('[agent]\nspec = "root_agent.py:graph"\n')
    (proj / "root_agent.py").write_text(_AGENT_SRC)
    sub = proj / "src"
    sub.mkdir()
    (sub / "my_agent.py").write_text(_AGENT_SRC)
    monkeypatch.chdir(sub)

    r = CliRunner().invoke(main, ["-a", "my_agent.py:graph", "--no-interactive", "hi"])
    assert r.exit_code == 0, r.output
    assert "hi from my_agent" in r.output
    assert "not found" not in r.output.lower()
