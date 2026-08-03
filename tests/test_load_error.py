"""Regression: a load/top-level exception with an empty ``str(e)`` is not blank (gh #109).

A bare ``assert x`` (``AssertionError('')``), ``raise NotImplementedError``, or
``RuntimeError()`` has an empty string representation, so the top-level handlers — which
printed only ``{e}`` — collapsed to a blank, typeless ``Error:`` with no class name and
no ``-v`` hint (strictly worse than, and inconsistent with, the runtime turn-error path,
which names the type). The fix names the exception class and always points at ``-v``.
"""

from click.testing import CliRunner

from langstage_cli.cli import main


def test_top_level_empty_message_exception_names_class_and_hints_at_v(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # A realistic "my agent doesn't load yet" trigger: a module that raises with no message.
    (tmp_path / "boom_agent.py").write_text(
        "raise NotImplementedError\ngraph = None\n", encoding="utf-8"
    )

    r = CliRunner().invoke(main, ["-a", "boom_agent.py:graph", "hi"])
    assert r.exit_code == 1, r.output
    # The class name appears even though str(e) == "" (the old blank `Error:` is gone)...
    assert "Error: NotImplementedError" in r.output, r.output
    # ...and the same -v nudge the user needs to get the traceback.
    assert "-v" in r.output, r.output


def test_top_level_bare_assert_is_not_a_blank_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "assert_agent.py").write_text("assert False\ngraph = None\n", encoding="utf-8")

    r = CliRunner().invoke(main, ["-a", "assert_agent.py:graph", "hi"])
    assert r.exit_code == 1, r.output
    assert "Error: AssertionError" in r.output, r.output
    # never a bare, typeless "Error:" line
    assert not any(ln.strip() in ("Error:", "⏺ Error:") for ln in r.output.splitlines()), r.output
