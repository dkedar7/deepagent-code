"""`langstage-cli init` scaffolds a runnable starter agent + langstage.toml (gh #104).

`--demo` proves the CLI works; `init` proves *your graph* works — the missing rung
between "see it work" and "run my own graph". It writes a keyless stdlib agent and a
langstage.toml wired to it, so the very next `langstage-cli "..."` runs the user's own
graph with no -a and no hand-editing. It never clobbers existing files without --force.
"""

from pathlib import Path

from click.testing import CliRunner

from langstage_cli.cli import main


def test_init_scaffolds_files_that_load_and_run(monkeypatch, tmp_path):
    # Isolate the global config so the scaffolded project langstage.toml is what runs.
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path / "empty_home"))
    r = CliRunner()
    with r.isolated_filesystem() as fs:
        res = r.invoke(main, ["init"])
        assert res.exit_code == 0, res.output
        assert (Path(fs) / "my_agent.py").exists()
        assert (Path(fs) / "langstage.toml").exists()
        assert "Wrote my_agent.py and langstage.toml" in res.output

        # The scaffold then loads + runs under the CLI with no -a needed.
        run = r.invoke(main, ["--no-interactive", "Hello!"])
        assert run.exit_code == 0, run.output
        assert "You said: Hello!" in run.output


def test_init_refuses_to_overwrite_without_force(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path / "empty_home"))
    r = CliRunner()
    with r.isolated_filesystem():
        assert r.invoke(main, ["init"]).exit_code == 0
        # A second init refuses (non-zero) rather than clobbering the user's agent.
        second = r.invoke(main, ["init"])
        assert second.exit_code != 0
        assert "refusing to overwrite" in second.output
        # ...unless --force is passed.
        assert r.invoke(main, ["init", "--force"]).exit_code == 0
