---
name: using-relay
description: Use when starting work with the relay plugin or when asked how relay's commands, engine/agent arguments, implement pipeline, or refinement loops work — orients you to the relay surface and its hard superpowers dependency before you run /relay:implement or /relay:refine.
---

# Using Relay

`relay` is a multi-agent orchestration layer for Claude Code. It does not reimplement the
SDLC primitives (drafting specs, writing plans, finishing a branch, …). Those live in the
installed `superpowers` plugin and are invoked through the `superpowers:*` namespace. Relay
adds the orchestration: an autonomous end-to-end implementation pipeline, four adversarial
refinement loops (spec, plan, pr, ui), and a standalone diagnosis workflow. It can fan heavy
roles out to external CLI agents via ACPX.

This skill is the map. It names every command, its argument shape, and where each pipeline
lives. For the depth of any pipeline, read its backing skill.

## Hard dependency: superpowers

Relay is layered on superpowers and cannot run without it. The dependency-gated commands
(`/relay:setup`, `/relay:refine`, `/relay:drive`) source `scripts/check-deps.sh` as their
first line. That gate probes for the installed `superpowers` plugin (project-local →
user-global → marketplace cache). If it is absent, the gate blocks with `[relay] BLOCKING:`
and a `/plugin install` hint, and returns non-zero so the command aborts. `/relay:implement`
and `/relay:diagnose` are thin-L3 Workflow commands and do not source `check-deps.sh`; the
dependency surfaces inside the generated Workflow's leaf bindings. If a command refuses to
run, install superpowers from the canonical `obra/superpowers-marketplace` source first:

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers
```

## Commands

| Command | What it does | Backing skill |
|---|---|---|
| `/relay:setup` | Interactive provisioning: acpx floor preflight, engine-aware dependency check, codex skill provisioning. Run once on a fresh machine. | `relay:setting-up-relay` |
| `/relay:implement` | Thin-L3 autonomous implementation. Auto-classifies the task into a closed kind from context, then generates one dynamic Workflow over the kind's hard spine (the §4.2.1 branch table). Accepts `--engine`/`--agent`. For the spine's phase details, see the §4.2.1 branch table in commands/implement.md. | `relay:delegate-leaf` (per-kind hard spine) |
| `/relay:refine` | Thin-L3 adversarial refinement. Classifies the task, then generates one dynamic Workflow over an `relay:improve-loop` spine keyed on `--target spec\|plan\|pr\|ui` (spec/plan/pr critic, or the scored UI generator ↔ evaluator loop via `relay:refining-ui`). Accepts `--target`. For loop details, see `relay:refining`. | `relay:refining-specs` (default target's critic) / `relay:refining-ui` (ui target) |
| `/relay:execute` | Thin-L3 open-ended composition. Auto-classifies the task to bias soft-zone guidance only (advisory kind — no hard floor), then freely composes one dynamic Workflow from the L2 library. | `relay:delegate-leaf` (cited among the free library) |
| `/relay:diagnose` | Standalone problem diagnosis: gather context → 3 root cause theories → ranked recommendation. Workflow-only (needs dynamic workflows enabled — the default). No engine/agent args. | Workflow substrate (no backing skill) |
| `/relay:drive` | Autonomous run-to-done: drives a long-running, multi-step process to a verifiable done criterion without a human in the loop — surviving `/compact` and worktree loss. MAIN owns at most one long-lived process; one dynamic Workflow runs the oracle-gated loop (orient → delegate → verify → branch → record → consecutive-clean-runs → closeout). Takes `[--resume] <oracle-file>`. | `relay:driving-to-done` |

Where each command's logic lives (the command bodies hold no orchestration logic):

- `/relay:setup` validates `[engine] [agent]` via `scripts/parse-engine-agent.sh`, then dispatches `relay:setting-up-relay`.
- `/relay:implement` classifies via `relay:classifying-task-kind`; the spine is the §4.2.1 branch table in `commands/implement.md`.
- `/relay:refine` classifies via `relay:classifying-task-kind`; the loop is `relay:refining` (ui target: `relay:refining-ui`).
- `/relay:execute` composes freely from the L2 library; see `relay:delegate-leaf`.
- `/relay:diagnose` generates one Workflow inline from `$ARGUMENTS`; `AskUserQuestion` is reserved for genuine choices.
- `/relay:drive` resolves an oracle path and `--resume`, may launch one long-lived process before its Workflow; see `relay:driving-to-done`.

## Preflight: worktree isolation (Step 0.5)

Before a source-modifying command (`implement`, `refine`, `execute`, `drive`) generates its
Workflow, it sources `scripts/worktree-preflight.sh --classify` and invokes
`relay:ensuring-worktree-isolation`, which owns the confirm / create / enter state machine.
That skill enters a worktree via `EnterWorktree({path})` exactly once; on `drive --resume`
it runs verify-only from the recorded `RELAY_DRIVE_WORKSPACE`. `diagnose` and `setup` have
no worktree gate.

When a repo needs newly-created worktrees to install dependencies or build generated
artifacts before verification, configure `.claude/relay.json` with a `bootstrap` command.
See `docs/superpowers/references/relay-repo-config.md` for the supported config shape.

## Arguments

The thin-L3 commands auto-classify the task kind from context — there is no `--kind` flag.
`/relay:implement` takes `--engine`/`--agent`, `/relay:refine` takes `--target`; `/relay:setup`
still takes the two optional positionals:

```
/relay:implement [--engine in-session|acpx|smart-routing] [--agent claude|codex|opencode|hybrid|smart-routing] <task>
/relay:refine    [--target spec|plan|pr|ui] <subject>
/relay:execute   <task>
/relay:setup     [engine] [agent]
```

`/relay:execute` is 100% soft: the auto-classified kind is advisory only. It biases which
patterns' when-to-use signals the soft zone weights and keys no hard floor.

`/relay:diagnose` takes no flags. `/relay:implement` infers a closed kind from context and
keys its hard spine on it; `/relay:refine` keys its spine on `--target`.
`/relay:implement`'s `--engine`/`--agent` flags select the dispatch family and resolve to
per-leaf bindings inside the generated Workflow (next subsection).

Each command carries its own default for that pair. `/relay:implement` and `/relay:verify`
default to `--engine acpx --agent claude`: leaf work runs as watched external Claude workers,
so the calling session keeps its context. `/relay:refine`, `/relay:execute` and `/relay:drive`
default to `--engine in-session --agent claude`. A flag beats the command default, and an
`engine`/`agent` pin in `.claude/relay.json` beats it too, so one pin makes every command
agree.

### Choosing the model for a group of roles

`/relay:implement`, `/relay:refine`, `/relay:execute` and `/relay:drive` also take two model
flags. Each addresses one named group of roles, not one role:

```
--fixes-model sonnet|opus|fable          # the roles that repair an artifact after a critic
--verification-model sonnet|opus|fable   # the critics that decide whether the work is done
```

The defaults are `sonnet` for the fixes group and `opus` for the verification group. A flag
replaces the model of every role of its group and changes no `effort`. `.claude/relay.json`
carries the same two values as the keys `fixes_model` and `verification_model`; a flag beats
a pin. `/relay:verify` and `/relay:diagnose` take neither flag — `/relay:verify` dispatches no
role, and `/relay:diagnose` has no argument step. `skills/selecting-the-right-model/SKILL.md`
lists which role is in which group.

### Per-leaf binding (engine / agent)

Inside a generated Workflow, each leaf role carries its own binding selecting where it runs.
The binding surface is the same vocabulary that `/relay:setup` takes as positionals:

- `engine` — `in-session` (default) or `acpx`. `in-session` runs the primitive role inside
  the current Claude session as a subagent; `acpx` fans the role out to an external CLI
  agent per `bindings/presets.yaml`.
- `agent` — `claude` | `codex` | `hybrid` | `opencode`. Default depends on the engine:
  `in-session` ⇒ `claude`; `acpx` ⇒ `hybrid`.

Invariant (spec §2): `engine=in-session` requires `agent=claude` — the in-session harness
only runs Claude, so `in-session codex`/`in-session opencode` bindings are rejected with a
non-zero return. Inputs are lowercased before validation. Examples: default →
`in-session claude`; `acpx` → `acpx hybrid`; `acpx opencode` → ok; `in-session codex` → error.

When no spec is supplied, the generated implement Workflow resolves the target itself.

## Pipelines

- **Implement** — the spine has one written authority: the §4.2.1 branch table in
  `commands/implement.md`. Read it there.
- **Refine** — the loop algorithm and per-target critic/fixer wiring live in
  `relay:refining`; the 7-field contract is in `docs/refinement-contract.md`.

## Orchestration substrate

The native Workflow tool is the single substrate: every L3 command generates one dynamic
Workflow. in-session vs acpx is a per-leaf binding (`relay:dispatching-acpx-agents` /
`relay:dispatching-in-session-agents`). See `docs/orchestration-substrates.md`.

## Registered agents (7 agents total)

- User-facing primitives: `agents/code-reviewer`, `agents/scout`
- Generic execution leaves: `agents/leaf-worker` (writer roles), `agents/leaf-reader` (reader/critic roles)
- Workflow-only diagnosis agents: `agents/gatherer`, `agents/strategist`, `agents/analyst`

22 roles live in `roles/*.md` and are dispatched through the two generic leaves; they are
not registered agents. See `docs/agent-roster.md` and `roles/README.md`.

## Delegation rule

For an SDLC primitive it does not own, relay invokes it through the `superpowers:*`
namespace (e.g. `superpowers:brainstorming`, `superpowers:writing-plans`,
`superpowers:finishing-a-development-branch`). Relay's own coordinators and shims are
invoked as `relay:<name>` (e.g. `relay:refining-specs`, `relay:delegate-leaf`,
`relay:panel`, `relay:classifying-task-kind`). Leaf roles are dispatched through the two
generic leaves — writer roles (e.g. `roles/implementer.md` via `relay:leaf-worker`) and
reader roles (e.g. `roles/spec-reviewer.md` via `relay:leaf-reader`). Relay owns spec
verification (the implement Workflow's verify phase) and Phase-0 context gathering (the
`agents/scout` agent producing the `CONTEXT_SUMMARY`); these are not delegated to superpowers.
