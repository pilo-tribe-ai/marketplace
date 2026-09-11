---
name: refining-ui
description: Thin shim over relay:refining configured for the UI target — scored convergence with threshold-AND across 5 dimensions, plateau→pivot, and a running dev server. Called from /relay:refine (ui path).
user-invocable: false
---

# Refining UI

Thin shim over the generic `relay:refining` loop, configured for the UI target with scored
convergence mode.

Core principle: evaluate a live running website across 5 quality dimensions, iterating code
fixes until every dimension reaches its threshold or max rounds is exhausted.

Announce at start: "I'm using the refining-ui skill to refine this UI with scored convergence."

## What to do

### Pre-flight: ensure the server is running

Before invoking the engine, call `relay:running-web-apps` via the Skill tool to:
1. Perform the one-time setup (Playwright MCP, permissions, framework detection) if not yet done.
2. Start the dev server and health-check the URL.

`relay:running-web-apps` returns `{base_url, dev_command, framework, server_status}`.
- If `server_status == "SERVER_FAILED"`, abort with a clear error — do not enter the refining loop.
- Pass the `{base_url, source_root, dev_command}` handle to the engine as the adapter's
  pre-warmed subject input.

### Pre-flight: Playwright CLI check

```bash
npx playwright --version || { echo "BLOCKED: playwright-cli-missing"; exit 1; }
```

If absent, abort with `BLOCKED: playwright-cli-missing` — do not enter the refining loop.

### Engine invocation

Invoke `relay:refining` via the Skill tool with the config below. The UI adapter's `load()`
receives the pre-warmed handle from `relay:running-web-apps` directly — it does not re-invoke
that skill. The engine owns the scored-mode mechanics (threshold-AND, plateau → pivot,
`merge_scores` / `cap`); `adapters/ui.md` owns `persist()` (the `refine(ui): round N ...`
score-commit) and the terminal states.

```yaml
# The Workflow supplies resolved literals, for example engine: acpx / agent: codex.
# If the fields are absent, relay:refining uses in-session / claude.
engine: ${RELAY_ENGINE}
agent: ${RELAY_AGENT}
subject: live website (rendered + source tree)
subject_adapter: adapters/ui.md
convergence_mode: scored
scored:
  dimensions: {design_quality: 7, originality: 7, craft: 7, functionality: 7, accessibility: 7}
  max_findings_per_cycle: 5
  plateau_window: 3
  plateau_epsilon: 0.5
max_rounds: 10
aggregator: scored
critics:
  # `model:` values below mirror each role's flat tier in bindings/presets.yaml and are
  # resolved at dispatch via scripts/resolve-tier.sh — the binding wins if they ever differ.
  # ui-code-evaluator is browser-free (source-only); runs in parallel with browser critics
  # roles/ui-code-evaluator.md (role-class: reader) → relay:leaf-reader
  - {role: roles/ui-code-evaluator.md,          leaf: relay:leaf-reader, model: sonnet, parallel: true}
  # browser critics share one Playwright instance and MUST run sequentially
  # roles/ui-visual-evaluator.md (role-class: reader) → relay:leaf-reader
  - {role: roles/ui-visual-evaluator.md,        leaf: relay:leaf-reader, model: sonnet, parallel: false}
  # roles/ui-ux-evaluator.md (role-class: reader) → relay:leaf-reader
  - {role: roles/ui-ux-evaluator.md,            leaf: relay:leaf-reader, model: sonnet, parallel: false}
  # roles/ui-accessibility-evaluator.md (role-class: reader) → relay:leaf-reader
  - {role: roles/ui-accessibility-evaluator.md, leaf: relay:leaf-reader, model: sonnet, parallel: false}
fixer:
  # roles/ui-generator.md (role-class: writer) → relay:leaf-worker
  role: roles/ui-generator.md
  leaf: relay:leaf-worker
  post: re-read
```

### Delegation split (`--engine acpx`)

Only the two source-only roles are `delegate_eligible` in `bindings/presets.yaml`:

| Role | Eligible | Why |
|---|---|---|
| `ui-code-evaluator` | ✅ | Static source analysis — no browser, no vision. |
| `ui-generator` | ✅ | File-producing writer, same shape as `fix-coder`. Runs with `isolation: none` so its edits land in the loop's own git-backed worktree. |
| `ui-visual-evaluator` | ❌ | Must read rendered screenshots to score `design_quality`/`originality`. Relay models no vision capability, so a non-vision worker would score blind and silently corrupt scored convergence. |
| `ui-ux-evaluator` | ❌ | Drives the shared Playwright browser alongside the visual critic. |
| `ui-accessibility-evaluator` | ❌ | Same shared-browser constraint. |

So `--engine acpx --agent codex` delegates the fixer and the code critic to codex
(`gpt-5.6-terra` for both, per `modalities.codex`), while the three browser critics
continue to run in-session on Claude. This is a per-role split, not a pipeline-wide fork.

### Roles (dispatched via leaf agents)

| Role file | Leaf agentType | Type | Dimensions | parallel |
|---|---|---|---|---|
| `roles/ui-code-evaluator.md` | `relay:leaf-reader` | critic | `craft` | `true` |
| `roles/ui-visual-evaluator.md` | `relay:leaf-reader` | critic | `design_quality`, `originality` | `false` |
| `roles/ui-ux-evaluator.md` | `relay:leaf-reader` | critic | `functionality` | `false` |
| `roles/ui-accessibility-evaluator.md` | `relay:leaf-reader` | critic | `accessibility` | `false` |
| `roles/ui-generator.md` | `relay:leaf-worker` | fixer | — | — |

The three browser critics share one Playwright instance (driven via `npx playwright` through
the leaf's `Bash` tool), so they run sequentially; `ui-code-evaluator` reads source only and
runs in parallel with them. Each evaluator returns `{dimension, scores{…}, findings[]}`.
