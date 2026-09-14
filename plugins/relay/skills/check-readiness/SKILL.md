---
name: check-readiness
description: Non-interactive readiness check — runs check-deps.sh and acpx CLI preflight for the given agent set, returns a structured JSON matrix without prompting. Use before dispatching off-claude roles to validate the environment.
user-invocable: false
model-only: true
---

# check-readiness

Non-interactive, model-only readiness preflight. Called by the firework driver at run
start when the active preset binds any role off-claude. Returns a structured JSON matrix
without interactive output or user prompts.

## Inputs

- `RELAY_AGENT` — the agent set to check (e.g. `claude`, `codex`, `hybrid`). Passed
  via skill args. Determines which dependency sets `scripts/check-deps.sh` probes.

## Steps

1. **Run check-deps.sh** for the given agent set:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/check-deps.sh" --agent "$RELAY_AGENT" --format json
   ```

   Parse the per-set JSON matrix `{"<set>":{"<skill>":"ok"|"missing"}}`.

2. **Acpx CLI preflight** for each non-claude engine referenced by `RELAY_AGENT`
   (skip when agent set is `claude` only). For each non-claude engine, run exactly two
   commands:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/acpx-floor.sh"   # prints RELAY_ACPX_VERSION=<v>, or fails
   acpx flow --help >/dev/null 2>&1                     # must exit 0
   ```

   Pass criteria: both exit 0. `scripts/acpx-floor.sh` owns the floor number and
   compares the version itself — never restate the number here.

   Per-engine `status` values:
   - `ok` — both commands exited 0
   - `missing` — the floor script printed `acpx is not on PATH`
   - `too-old` — the floor script printed `is below the floor`
   - `flow-subcommand-absent` — `acpx flow --help` exited non-zero

   Populate the `error` field with the raw stderr or version string on any failure.

## Output

Return a structured JSON matrix (no prose, no interactive output):

```json
{
  "ok": true,
  "agents": [
    {"name": "<engine>", "engine": "<engine>", "status": "ok"},
    {"name": "<engine>", "engine": "<engine>", "status": "missing", "error": "<stderr>"}
  ]
}
```

`ok` is `true` iff all agents have `status: ok`. This skill is invoked non-interactively
by the firework driver; no user prompts are issued. On failure the driver gates with a
structured message: "fall back to the all-claude preset for this run, or abort and run
the setup command."
