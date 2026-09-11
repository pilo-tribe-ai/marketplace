# Relay Orchestration Substrate

Relay uses **two orchestration substrates**. The rule is **one Workflow per session.
Nesting happens across sessions, through dispatch.** Every L3 command generates one
dynamic Workflow inline in its own session, with in-session-vs-acpx-vs-bg-sessions
demoted to a per-leaf binding resolved per role at Workflow-generation time — except
`/relay:implement` under `--engine session-tree`, which generates no Workflow at all.
See "The session-tree exception" below. A bg child dispatched from a Workflow leaf runs
in its own session, so it may generate a Workflow of its own; see "The nested-dispatch
exception" below.

## Substrate: Native Workflow Tool

**Used by:** every L3 command — `/relay:diagnose`, `/relay:refine`, `/relay:implement`,
`/relay:execute`, `/relay:drive`.
**Pattern:** each command generates one dynamic Workflow inline via Claude Code's built-in
`Workflow` tool. Leaf roles are dispatched by role slug; `mechanism-resolve` demotes
in-session-vs-acpx to a per-leaf binding (spec §5), reading the per-role binding source in
`bindings/presets.yaml` and routing each leaf through `relay:dispatching-acpx-agents` or
`relay:dispatching-in-session-agents`.
**When to use:** all structured-handoff flows — the substrate provides native resume and
deterministic phasing, with each leaf's execution mechanism resolved per role rather than as a
pipeline-wide concern.
**Contract:** `docs/dispatch-contract.md`.

## The `/relay:drive` exception: MAIN may own one long-lived process

`/relay:drive` is the one documented exception to "MAIN holds nothing": before generating its
Workflow, MAIN may launch a single long-lived process as a background task (when the oracle
declares one — e.g. a dev server that must outlive every step), because a process launched inside
an ephemeral Workflow leaf dies with that leaf; it still generates **exactly one** dynamic Workflow
that runs the oracle-gated loop, so the single-substrate doctrine is intact.

## The session-tree exception: a run may have no Workflow at all

`--engine session-tree` is the **second** documented exception to "every L3 command
generates one Workflow", next to `/relay:drive`. Under `session-tree` the command
generates no Workflow. MAIN — the session running the command — is the orchestrator
for the whole run.

The two exceptions are different in kind. `/relay:drive` still generates exactly one
Workflow and only holds one long-lived process outside it, so the single-Workflow
doctrine stays intact for that command. `session-tree` generates none: the §4.2.1
spine still governs WHAT happens, but spine roles run as background sessions, not as
`agent()` Workflow nodes.

**Contract:** `docs/bg-dispatch-contract.md`. **Orchestrator prose:**
`skills/orchestrating-session-trees/SKILL.md`.

**v1 scope:** `/relay:implement` only. `/relay:refine`, `/relay:execute`, and
`/relay:drive` reject `--engine session-tree` with an engine-not-supported error.

## The nested-dispatch exception: a bg child may run a Workflow of its own

A bg child dispatched from a leaf of a session's one Workflow may generate a Workflow
of its own, because it is a **different session**. The one-Workflow-per-session rule
holds in each session; nesting composes across sessions through dispatch, not inside
one session.

Depth is capped at 1: a bg child must not dispatch a further bg child. The cap is
enforced in `skills/dispatching-bg-agents/bg-dispatch.sh`, which refuses a nested
dispatch with a usage error and creates no sidecar, no handoff directory, and no prompt
file when the refusal fires.

`--engine session-tree` and nested bg dispatch now overlap in what an operator could
reach: both let work run as a tree of background sessions across more than one level.
Narrowing `session-tree`, or folding it into nested dispatch, is possible future work.
This is recorded, not scheduled — no change narrows `session-tree` here.

## `flows/` — a leaf capability, not a substrate

`flows/` retains the acpx-native brainstorm grounding artifact (`flows/brainstorm.flow.ts`) — a
leaf capability, not a pipeline substrate. It is invoked as a grounding step within a leaf, not as
an orchestration tier. `flows/package-lock.json` is intentionally tracked for reproducibility.

## The diagnose → refine → implement Ladder

```
/relay:diagnose
        ↓ identifies root-cause hypotheses
/relay:refine
        ↓ converges the spec/plan
/relay:implement
        ↓ executes the task cycle
```

The ladder is advisory: each command is independently invocable, and each generates its own
dynamic Workflow inline on the single Native Workflow Tool substrate.
