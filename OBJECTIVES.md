# Objectives & scope — langstage-cli

*What this repo is for, who it serves, and what it deliberately is **not** — the yardstick
for deciding whether a proposed change or filed issue belongs here. When triaging an issue,
start here.*

## Objective

A Claude-Code-style **terminal client** for *any* LangGraph `CompiledGraph`: streaming,
tool-call rendering, human-in-the-loop approval, one-shot and interactive, with cross-invocation
session persistence — driven over langstage-core's chunk wire.

## Who it's for

A developer who wants to talk to their agent from the terminal, script it, or gate CI — with
no server and no browser.

## In scope

- The interactive loop and the one-shot path; quiet/`--json` output for scripting.
- HITL rendering and resume (including the plain-string `interrupt()` "collect input" pattern).
- Session persistence: `--continue` / `--resume <id>` / `--list-sessions` over a durable
  per-workspace checkpointer the CLI provides itself.
- `--demo`, `init` (a minimal runnable scaffold), `--show-config`.

## Out of scope (anti-scope)

- Becoming a server or a long-running daemon.
- A workspace file manager or file browser — that's the **langstage** web app.
- A full IDE, or project scaffolding beyond a minimal `init`.
- Rendering or wire logic that should live in **langstage-core** — keep the CLI a thin consumer
  so it never drifts from the other surfaces.

## How this fits the family

langstage-cli is the **terminal surface** of the family: a thin consumer of langstage-core. If
a fix here would also be needed by the web, JupyterLab, or VS Code surface, it belongs in core.

## Using this to triage

Before acting on an issue or PR: does it serve the objective above? Is it in scope or
anti-scope? Weigh its value — **security > correctness > advertised-≠-honored > DX/docs >
polish > net-new feature** — against the cost of a manual release. Then **fix, defer, or
decline with a reason.** Not every filed issue is worth acting on.
