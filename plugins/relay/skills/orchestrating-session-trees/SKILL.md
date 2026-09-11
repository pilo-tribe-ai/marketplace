---
name: orchestrating-session-trees
description: Use in MAIN when `--engine session-tree` is resolved by `/relay:implement` — the substrate that replaces the Workflow tool with a tree of background Claude sessions talking by message. MAIN spawns every session flat through `scripts/bg-launch.sh`, tracks the tree in a run manifest kept by `scripts/bg-manifest.sh`, routes `NEEDS_DECISION` questions worker → operator → orchestrator, and runs the end-of-run stop protocol. The second documented exception to "every L3 command generates one Workflow", alongside `/relay:drive`.
user-invocable: false
---

# orchestrating-session-trees

## Inputs

- `worktree` (optional) — the literal absolute path to this run's active worktree, passed
  as a `worktree: <literal>` prose line in the calling text of the `Skill` invocation, the
  same pattern `skills/implementing-spec/SKILL.md` uses for its own input block. No env
  var, no `Skill` tool argument. `commands/implement.md` passes this line when its Step
  0.55 printed `RELAY_WT_ACTIVE=<toplevel>`. When absent, every `bg-launch.sh` call below
  runs unwrapped and behavior is unchanged.

## Overview

This skill runs in MAIN — the session that is running `/relay:implement`. Under
`--engine session-tree` the command generates **no Workflow**. MAIN is the
orchestrator for the whole run. The §4.2.1 spine (`docs/orchestration-substrates.md`,
`docs/architecture.md`) still governs WHAT happens — the same roles run in the same
order — only the substrate changes: spine roles run as background sessions, not as
`agent()` Workflow nodes.

Shared layer: see `docs/bg-dispatch-contract.md` for the envelope grammar, the naming
grammar, the launch contract, the identity preamble, and liveness-and-truth. This
skill does not restate that contract. It holds the orchestrator prose the contract
has no other home for: spawn the tree, route questions, run the end-of-run stop
protocol (spec §Deliverable 3, Doctrine).

## Scope

v1 covers `/relay:implement` only. `/relay:refine`, `/relay:execute`, and
`/relay:drive` keep their current substrate and reject `--engine session-tree` with
an engine-not-supported error. Refine and verify loops migrate to session-tree, if
ever, after the implement path has run clean in practice (spec, "Not doing,
deliberately").

## Topology

The orchestrator spawns every session, flat, through `scripts/bg-launch.sh`. It never
delegates a spawn to an operator — a session running under `--permission-mode
dontAsk` cannot run Bash (S3-1), and any permission mode that allows Bash also allows
a spawn, which reintroduces the topology risk the cap below exists to avoid.

Parent and child are **logical**, not physical. The identity preamble (§Identity
preamble, `docs/bg-dispatch-contract.md`) sets who a session answers to; who actually
ran `bg-launch.sh` is a launch-time detail the child never sees.

**v1 cap: one operator per goal, and at most three workers under it** — the proven S3
shape (implementer + reviewer, plus headroom for one more). Fan-out and cost past
this cap are untested ("still unknown" in the spike findings), so the cap is
deliberate, not an oversight. When a run's shape would need more than one operator
per goal, or more than three workers under one operator, the run's final report
**must name the cap and say it bound** — never silently truncate the run's ambition
to fit.

## Bookkeeping

The orchestrator allocates the run's `runid` at the start of the run: a fresh
`[a-z0-9]{4,8}` string, the same shape §Naming needs, and the exact value every
session name's runid suffix carries in this run. This is **not** read from
`record-run-intent.sh` — that script never runs under session-tree, because
session-tree runs no Workflow and allocates no `wf_…` id (spec §Deliverable 3,
Bookkeeping). `record-run-intent.sh` itself is unchanged and is simply never called
here.

The orchestrator holds the allocated runid as `$RELAY_RUN_ID` for the whole run.
Every place this skill needs the value — every `bg-manifest.sh` call, the end-of-run
cleanup — reads it from that variable, and no second runid space is introduced.

The run manifest is the single source of truth for the tree: `${HOME}/.claude/relay
/runs/<runid>/manifest.json`, kept through `scripts/bg-manifest.sh` (`init`,
`add-session`, `set-phase`, `read`, `names`). It holds the runid and, per session,
the name, launch id, role, logical parent, and phase status. Every spawn and every
processed envelope rewrites the manifest.

A manifest write failure is **FATAL**. `bg-manifest.sh` exits `1` with `[relay]
error: manifest write failed: <path>` and this skill stops the orchestrator's turn
with an error — it does not degrade and continue. This is the opposite of
`record-run-intent.sh`'s advisory doctrine, and the difference is deliberate: the
manifest is the only resume path a session-tree run has.

## Spawning

Every session name is built per §Naming (`docs/bg-dispatch-contract.md`):
`<product>-<role>-<goal>-<runid>`. `product` is the worktree's directory name,
kebab-cased. `role` is `orchestrator`, `operator`, or a dispatchable role slug —
`docs/agent-roster.md`, "Session-tree topology roles" adds `orchestrator` and
`operator` to the closed roster the naming validator reads, alongside a bare
`worker` entry for a leaf under an operator with no more specific role. `goal` is
the phase or feature slug the orchestrator assigns to an operator's subtree (for
example `feature-a`); it is omitted for the orchestrator itself, the same way it is
omitted for bg-sessions leaves. `runid` is the one runid this run allocated in
Bookkeeping — one runid space, never a second one per session.

Every launch goes through `scripts/bg-launch.sh` — the only sanctioned launcher — and
every launch is validated with `bg-launch.sh --check-name` before it starts anything.
Operators never spawn (S3-1, restated in Topology above).

When the `worktree` input above is set, wrap every `bg-launch.sh` call site in
`(cd <literal> && bash scripts/bg-launch.sh …)` so each spawned session starts in the
run's active worktree. No flag is added to `bg-launch.sh` itself. When the input is
absent, call `bg-launch.sh` unwrapped, exactly as today.

## Waiting

`[unverified]` — S1 proved free waiting (a session ends its turn, and an inbound
message starts a new turn) for a **background child**, never for MAIN. MAIN under
session-tree is a foreground session mid-way through a slash command, and this
property was never measured for that shape. This subagent task had no live session
harness to run the D3.0 verification step (send an envelope to an idle MAIN session
mid-command; confirm both that the turn restarts and that the restarted turn still
holds the manifest path, the runid, and the spawned children's names) — the same
constraint the D2.0 check hit for bg-sessions multi-turn.

Per the spec's own stated fallback for a failed or unverified check, v1 of this
skill uses the bounded-poll shape instead of free waiting: the orchestrator holds a
bounded foreground poll over the run manifest, in the same shape
`skills/delegate-and-watch/SKILL.md`'s watcher uses for a bg-sessions leaf — reading
each tracked session's phase and running `bg-liveness.sh` across the manifest's
launch ids on a fixed interval, until a phase changes, a question needs routing, or
the poll budget is spent. Free waiting (MAIN ending its turn and an inbound envelope
re-invoking it) is deferred until the D3.0 property is verified live and this section
is updated to match.

The long fallback heartbeat still applies under the bounded-poll shape: on each poll
pass, run `bg-liveness.sh` across every launch id the manifest tracks. The heartbeat
catches silence — a dead child sends no message at all (S4-1) — it never polls for
task results; task results come only from an envelope.

## Questions

`NEEDS_DECISION` flows **worker → operator → orchestrator**, never straight from a
worker to the orchestrator.

- A worker sends `NEEDS_DECISION: <question>` to its operator and ends its turn.
- The operator answers with `DECISION: <answer>` when the run rubric already covers
  the question. When it does not, the operator relays it upward as `ESCALATION from
  <origin>: <question>` — never as `BLOCKED:`, so a relay is never read as the
  operator itself being stuck (§Envelope, `docs/bg-dispatch-contract.md`).
- The orchestrator answers from run context when it can, and replies with
  `DECISION: <answer>`.
- When the question is genuinely the human's call: an **interactive** run uses
  `AskUserQuestion` — the orchestrator is the one session in the tree that owns the
  user channel, per the identity preamble's "never address the user" rule for every
  other session. A **headless** run has no user to ask, so it escalates one hop
  further: by message, `ESCALATION from <origin>: <question>`, to the orchestrator's
  own parent session.

## End of run

The orchestrator sends each child a finish-and-stop instruction by name, then
confirms the `stopped` verdict for each through `bg-liveness.sh` — the contract's
single stop mechanism (§Spawn authority, `docs/bg-dispatch-contract.md`), not a
second one invented here. This skill does not restate that mechanism, only its use
here: bottom-up, workers before their operator, so an operator is never stopped
while a worker still expects to reach it.

After that stop protocol, the orchestrator runs `scripts/bg-cleanup.sh` with the
run's runid — the one allocated in `## Bookkeeping` and held as `$RELAY_RUN_ID` —
so both bg engines clean up through one code path:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-cleanup.sh" \
  --runid "$RELAY_RUN_ID" --outcome "<clean|failed>" [--keep]
```

`--outcome` is `clean` when the run completed and `failed` otherwise. `--keep`
mirrors `--keep-sessions`. Because the orchestrator has already stopped its
children, the script's stop step normally confirms `stopped` on the first call.

On exit `1`, the orchestrator DOES run the retry loop. It is the one session in the
tree that can `SendMessage`, so it sends the pinned finish-and-stop message from
`docs/bg-dispatch-contract.md` §Spawn authority to each printed
`RELAY_BG_STOP_REQUIRED=` name and re-runs the identical command, at most twice —
the same rule the spine follows. Only after that does the existing rule apply: any
child that still does not confirm `stopped` is **named** in the run's final report,
never silently left running and never silently reported as stopped. The two rules
are sequential, not alternatives: retry first, then name what survived. Exit `2`
and exit `3` follow the same four-row table the spine uses (see
`skills/running-implement-spine/SKILL.md` Step 4.5).

Stopped sessions keep their names (S4-3); the next run's fresh `runid` is what
prevents a collision, not renaming or deleting the old session.

## Resume

After an orchestrator crash: read the manifest (`bg-manifest.sh --runid <id> read`),
poll liveness on every recorded launch id (`bg-manifest.sh --runid <id> names` feeds
`bg-liveness.sh`), then re-attach to whatever is still alive or respawn whatever is
`stopped`/`unknown` under a fresh launch, updating the manifest as each session is
resolved. This replaces Workflow-native resume; there is no `runId` to hand back to
a `Workflow` tool because none was ever launched.

## Failure behavior

The orchestrator column of the spec's failure table (docs/bg-dispatch-contract.md,
§Failure behavior):

| Failure | Orchestrator response |
|---|---|
| Launch denied / empty `intent` | Same as bg-sessions — `LAUNCH_DENIED`, one retry, then `errored` — recorded in the manifest |
| Child dead, no envelope | Heartbeat finds it; one respawn under a fresh name, then `errored` |
| Child alive but silent | One nudge message, then `errored` after a stated staleness threshold |
| Send refused: no such agent / collision / HTTP 409 | Re-resolve via ListAgents; use the error's `[ref]`; a 409 routes to the dead-child path |
| Fork misidentification | Identity preamble + inert free text (§Envelope) |

## See also

- `docs/bg-dispatch-contract.md` — the shared envelope, naming, launch, identity
  preamble, liveness, and spawn-authority contract this skill defers to.
- `docs/orchestration-substrates.md` — "The session-tree exception", where this
  substrate is recorded as the second documented exception to the one-Workflow
  doctrine.
- `docs/superpowers/specs/2026-08-19-relay-bg-engines-design.md` — §Deliverable 3.
- `skills/dispatching-bg-agents/` — the per-leaf sibling engine (`bg-sessions`),
  which this substrate reuses for the shared launch and envelope mechanics but not
  for its Workflow-node dispatch shape.
- `skills/delegate-and-watch/SKILL.md` — the watcher whose bounded-poll shape this
  skill's `## Waiting` section mirrors while free waiting is unverified.
