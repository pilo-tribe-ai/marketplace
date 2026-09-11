# Relay

Relay is a multi-agent orchestration toolkit for Claude Code, layered directly
on top of Jesse Vincent's [superpowers](https://github.com/obra/superpowers).
It is a port and extension of superpowers' orchestration roles and refinement
loops, repackaged as a sibling plugin that delegates its runtime primitives
(brainstorming, plan/spec authoring, debugging, TDD, worktrees, code
review) back into the `superpowers:*` namespace. **Relay requires the
`superpowers` plugin to be installed** — every relay command runs a presence
check first and blocks with an install hint if it is missing. Relay adds the
ACPX-driven and in-session dispatch layer, a generic adversarial refinement
loop with three target adapters, and a five-command surface on top of that
foundation.

## Prerequisite: install superpowers first

Relay delegates its development primitives to skills that ship in the canonical
`obra/superpowers-marketplace` build, so install superpowers from there. The closed
upstream set is the 14 `obra/superpowers` rows in
[`scripts/upstream-superpowers-skills.txt`](scripts/upstream-superpowers-skills.txt);
relay may reference no others.

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers
```

The in-command blocking hint also points at `obra/superpowers-marketplace`, so
the install source and the on-disk presence gate stay in lockstep.[^aaf]

[^aaf]: The `ai-advanced-futures/claude-code-dev-plugins` build also satisfies
the presence gate and ships the same delegated skills, but
`obra/superpowers-marketplace` is the canonical source relay standardizes on.

## Install relay

```
/plugin marketplace add ai-advanced-futures/claude-code-dev-plugins
/plugin install relay
```

## Commands

Relay exposes eight commands. Most source a superpowers presence check, resolve the
`--engine` / `--agent` axis, then generate one dynamic Workflow. The task kind is
always auto-classified from context — there is no `--kind` flag.

| Command | Purpose |
|---|---|
| `/relay:implement` | Autonomous end-to-end implementation of a spec — scout → refine spec → write plan → refine plan → execute every task (TDD) → review → e2e tests → verify. The spec is resolved from the task text and context. Add `--verify` to append the verify-until-clean loop (`--rounds 1-5`); `/relay:implement --verify` is exactly `/relay:implement` followed by `/relay:verify`. A bare run stops at `verify` and runs no cleanup. |
| `/relay:refine` | Thin-L3 adversarial refinement. Classifies the task, then generates one dynamic Workflow over an improve-loop spine keyed on `--target spec\|plan\|pr\|ui` (spec-simulator ↔ fixer, plan loop, experimental/beta PR review → validate → run → fix, or the scored UI generator ↔ evaluator loop via `relay:refining-ui`). Accepts `--target`. |
| `/relay:execute` | Thin-L3 open-ended composition. Classifies the task to bias soft-zone guidance only (advisory kind — no hard floor), then freely composes one dynamic Workflow from the L2 library with no required spine. |
| `/relay:setup` | Provision a machine for relay before running `/relay:implement` with the acpx engine or a codex agent — acpx preflight + engine-aware superpowers dependency check + codex skill provisioning. Takes `[engine] [agent]` **positionally**. |
| `/relay:engines` | Interactive engine assistant — preflights the acpx version, checks provider auth, probes the pinned models live, and audits served models against each engine's own session records. Takes `[codex\|opencode\|all]`. |
| `/relay:diagnose` | Standalone problem diagnosis: gather context → theorize root causes → rank by likelihood. |
| `/relay:drive` | Autonomous run-to-done: drives a long-running, multi-step process to a verifiable done criterion without a human in the loop — surviving `/compact` and worktree loss. MAIN owns at most one long-lived process; one dynamic Workflow runs the oracle-gated loop (orient → delegate → verify → branch → record → consecutive-clean-runs → closeout). Takes `[--resume] <oracle-file>`. |
| `/relay:verify` | Repeat `/simplify` → `/code-review medium --fix` → `/verify` over the current branch until it verifies clean or the round cap is spent. Reports `clean`, `findings`, or `unverified`. Takes `[--rounds 1-5]` and `[--engine in-session\|acpx]`. The default `in-session` invokes each command through the Skill tool and asks nothing; `--engine acpx` runs each step as a headless child turn and asks you to agree to the approvals-off sessions first. |

> `/relay:diagnose` takes **no** `engine`/`agent` arguments and runs on Claude
> Code's native Workflow substrate. Dynamic workflows are enabled by default; if
> they have been turned off (`/config` → Dynamic workflows, `"disableWorkflows": true`
> in settings, or `CLAUDE_CODE_DISABLE_WORKFLOWS=1`) the `Workflow` tool is absent and
> the command cannot run as designed.

### Argument table

The dispatch axis is passed as **flags**, not positionals — `implement`, `execute`,
`refine` and `drive` all accept both. `/relay:verify` resolves the axis too, but it
picks a substrate rather than a worker: it dispatches no role, and it supports
`in-session` and `acpx` only, rejecting the other three. `/relay:diagnose` resolves no
axis and takes `--retro` only, and `/relay:setup` is the one command that still reads
`[engine] [agent]` positionally.

| Flag | Values | Default | Notes |
|---|---|---|---|
| `--engine` | `in-session`, `acpx`, `smart-routing`, `bg-sessions`, `session-tree` | `in-session` | Where a leaf runs: inside the current session, out-of-process via ACPX, as a background Claude session, or (`/relay:implement` only) as a tree of orchestrated sessions. |
| `--agent` | `claude`, `codex`, `opencode`, `hybrid`, `smart-routing` | `claude` (in-session) / `hybrid` (acpx) | The backing model family for dispatched roles. |
| `--retro` | `<runId>` \| `last` | — | Post-run audit. Bare `--retro` runs the command then audits it; with a target it is audit-only. All five L3 commands. |
| `--target` | `spec`, `plan`, `pr`, `ui` | — | `/relay:refine` only. |
| `--resume` | — | — | `/relay:drive` only. |

Both axis flags may also be pinned in `.claude/relay.json`. Resolution is layered
**per axis**: flag > pin > default.

**Invariants**, enforced loudly rather than coerced: `engine=in-session` requires
`agent=claude` (the parent harness is Claude), `engine=bg-sessions` requires
`agent=claude` (no codex leg), `engine=session-tree` requires `agent=claude` (no
codex leg either), and `engine=smart-routing` cannot be combined with a literal
worker agent.

The axis selects a *family*, not a pipeline mode — each role's actual mechanism comes
from its own binding, so one `acpx` run can still keep vision-dependent critics
in-session. See [ADR-0005](docs/adr/0005-dispatch-axis-is-a-per-role-binding.md).

Examples:

```
/relay:implement add rate limiting to the API      # stops after verify, no cleanup
/relay:implement --verify add rate limiting to the API   # ... then the verify-until-clean loop
/relay:implement --engine acpx --agent hybrid add rate limiting to the API
/relay:refine --target spec                        # pressure-test a spec before planning
/relay:refine --target pr                          # adversarial PR refinement
/relay:implement --retro last                      # audit the most recent run, change nothing
```

## How it works

- **Implement pipeline.** `/relay:implement` drives the full
  scout → spec-refine → plan → plan-refine → per-task-execute → review → e2e
  pipeline by dispatching roles through the two generic execution leaves
  (`relay:leaf-worker`, `relay:leaf-reader`), delegating non-orchestration
  primitives to `superpowers:*` skills, and finishing through
  `superpowers:finishing-a-development-branch`. The relay roster is
  **7 agents total**: 2 user-facing primitives (`code-reviewer`, `scout`),
  2 generic execution leaves (`leaf-worker`, `leaf-reader`), and 3 Workflow-only
  diagnosis agents (`gatherer`, `strategist`, `analyst`). The 22 roles live in
  `roles/README.md`; 24 bindings are registered in `bindings/presets.yaml`.
  See [`docs/agent-roster.md`](docs/agent-roster.md) for the full agent inventory.
- **Refinement loops.** A single generic `refining/` loop (round → critics →
  optional aggregator → fixer → post-fix → persist → converge) is configured by
  four thin shims — `refining-specs`, `refining-plans`, `refining-prs`, `refining-ui` — each
  supplying per-target critics, fixer, and convergence predicate. The generic `/relay:refine`
  command is the interactive entry point that classifies the target and routes to the correct shim.
- **Dispatch.** Roles run either in-session (parent subagent tool) or via ACPX
  (`acpx <engine> exec`), selected by the `engine`/`agent` arguments and resolved
  through `bindings/presets.yaml`.

The full contract every refining skill implements is documented in
[`docs/refinement-contract.md`](docs/refinement-contract.md).

## Documentation

Start with the architecture overview; it explains the model the rest of the
documents assume.

| Document | What it covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | How relay works — layers, the agent/role split, the envelope, tiers, the dispatch axis, the reliability spine. **Read this first.** |
| [`docs/contributing.md`](docs/contributing.md) | How a change lands — the local gate, what the tests enforce, per-change checklists, and the traps. |
| [`docs/adr/`](docs/adr/README.md) | Architecture Decision Records — why relay is built this way, and whether each decision still holds. |
| [`docs/dispatch-contract.md`](docs/dispatch-contract.md) | The `(role_slug, binding, inputs) → result` envelope and both dispatch legs. |
| [`docs/refinement-contract.md`](docs/refinement-contract.md) | The generic refinement loop and its four target adapters. |
| [`docs/orchestration-substrates.md`](docs/orchestration-substrates.md) | Why there is exactly one substrate. |
| [`docs/language-reference.md`](docs/language-reference.md) | The L0/L1 vocabulary an L2 skill may declare. |
| [`docs/agent-roster.md`](docs/agent-roster.md) | The 7 registered agents and their tool grants. |
| [`roles/README.md`](roles/README.md) | The 22 roles and their consuming skills. |

## License & attribution

Relay is MIT-licensed. It is derived from superpowers (Copyright (c) 2025 Jesse
Vincent); relay's additions are Copyright (c) 2026 Yassel Piloto. See
[`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).
