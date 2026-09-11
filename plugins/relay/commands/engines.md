---
description: "Configure and verify the codex and opencode engines for acpx dispatch: binary/version preflight, provider auth checks, live pinned-model probes, and a served-model audit. Run when adding an engine or when acpx dispatches start failing."
disable-model-invocation: true
argument-hint: "[codex|opencode|all]"
allowed-tools: Bash, Skill
---

## Step 0 — Argument parsing

`/relay:engines` takes one optional positional selecting which engine to verify:
`codex`, `opencode`, or `all` (default). Any other value or extra positional is an
error — report it and stop.

## Step 1 — Invoke the engine-setup assistant

Invoke the `relay:setting-up-engines` Skill with the selected engine scope. It runs the
acpx preflight, per-engine auth checks, live pinned-model probes, and the served-model
audit, then prints the readiness report. Like `/relay:setup`, this command PROVISIONS
and verifies — it must not gate on the very dependencies it exists to fix.
