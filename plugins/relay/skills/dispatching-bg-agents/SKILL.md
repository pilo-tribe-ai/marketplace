---
name: dispatching-bg-agents
description: Use to dispatch a primitive role as a background Claude session through `scripts/bg-launch.sh` — resolves bindings from bindings/presets.yaml (no new field), validates capabilities, materializes the role body behind the bg-sessions identity preamble, and captures the child's envelope from a handoff file instead of stdout, because a background session has no parent to message. The background-session counterpart of dispatching-acpx-agents; it swaps the acpx driver and session mechanics for bg-launch.sh plus handoff-file completion.
user-invocable: false
---

# dispatching-bg-agents

## Overview

Implements the spec §Deliverable 2 (Dispatch, Completion) dispatcher for the
`bg-sessions` engine — the background-session counterpart of
`dispatching-acpx-agents`. Both honor the same `(role_slug, binding, inputs) → result`
interface (spec §5.1).

Shared layer: see `docs/bg-dispatch-contract.md` for the envelope grammar, the naming
grammar, the launch contract, the identity preamble, and liveness-and-truth. This skill
does not restate that contract; it names the one delta that matters for dispatch — the
envelope travels in an artifact file, not a message, because a Workflow watcher node
cannot receive messages.

## Wrapper contract (per spec §5.1)

`dispatch(role_slug, binding, inputs) →` the result shape in `docs/dispatch-contract.md`
(§5.1 Wrapper Contract). One delta: `output` is the captured envelope from the handoff
file, not stdout.

## Wrapper responsibilities (per spec §5.2)

1. **Resolve bindings.** Same `bindings/presets.yaml`, same `delegate_eligible` flag.
   The worker model comes from `modalities.claude`. No new binding field —
   `bindings/presets.yaml` is unchanged in v1 (spec §Deliverable 2, Bindings).
2. **Validate capabilities.** Unchanged. Same gate, same `capability-validate.js` —
   `requires ⊆` the leaf's tool set is enforced statically over every role by
   `tests/unit/skill-structure/test_capability_gate.py`, independent of dispatch
   mechanism.
3. **Materialize the role body.** Same `RELAY_ROLE_PATH` → `roles/<slug>.md` →
   `agents/<slug>.md` order and the same `ROLE_FILE_MISSING` typed error as
   `dispatching-acpx-agents`.
4. **Wrap with scaffolding.** Prepend `preamble.md` — the §1.4 identity preamble — then
   the role body. The bg-sessions preamble replaces the "send to your parent" line with
   *write your envelope to `<handoff-file>` — you have no parent to message*, because a
   Workflow watcher node has no session name to receive a message on. Adds the
   `TURN=<n>` echo instruction the child must carry in every envelope.
5. **Resolve the modality, then launch.** `modalities.claude` gives the model, unless
   the role carries a `category` and the matching model flag is set: a bg-session is
   always a Claude leg, so `--fixes-model` and `--verification-model` replace the
   model here exactly as they do on `acpx-claude`, and the script says so on stderr. The
   binding's `permissions` maps to `--permission-mode` through the §1.3 table
   (`approve-all` → `auto`; `approve-reads` or absent → `plan`). Launch
   through `scripts/bg-launch.sh` — the only sanctioned launcher — in the run's
   worktree, so the child inherits the launcher's cwd. `bg-dispatch.sh` never invokes
   `claude --bg` directly.
6. **Capture and verify.** Read the envelope from the handoff file, not from stdout.
   Apply the same capture regex, `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$`, to the file's
   content.

## Naming

Built per §1.2 (`docs/bg-dispatch-contract.md`, "Naming"): `<product>-<role>-<runid>`.
`goal` is always omitted for bg-sessions — a per-leaf dispatch has no goal distinct
from its role.

- `product` — the worktree's directory name, kebab-cased.
- `role` — the role slug, `$BG_ROLE_SLUG`.
- `runid` — derived from the Workflow's own `run_id` (`$BG_RUN_ID`, e.g.
  `wf_918a4deb-aba`): lowercased, `wf_` prefix stripped, every character outside
  `[a-z0-9]` removed, then the last 4 to 8 characters kept. **One rule, one source** —
  no independent runid space. The same input always derives the same suffix.

`bg-dispatch.sh` validates the built name through `bg-launch.sh --check-name` before
it creates any directory or writes any file.

## Sidecar contract

The counterpart of the acpx `${session}.env`. `bg-dispatch.sh` writes
`~/.claude/relay/bg/${runid}/${role_slug}.env` **before** launch, holding exactly
these six lines:

```
RELAY_BG_NAME=<name>
RELAY_BG_SHORT_ID=<short-id>
RELAY_BG_HANDOFF=<handoff-file-path>
RELAY_BG_MODEL=<model>
RELAY_BG_PERMISSION_MODE=<mode>
RELAY_BG_MAX_TURNS=<n>
```

`RELAY_BG_SHORT_ID` is written empty at first, then filled in after `bg-launch.sh`
returns it. The file is written before launch and completed after — a reader should
not expect a fully-populated sidecar the instant it appears on disk.

## Handoff file contract

Path: `$WORKTREE/.relay-bg/<runid>/<role_slug>.envelope`.

- `bg-dispatch.sh` creates the directory (and an empty handoff file) before launch.
  The child is the only writer of the file's content afterward.
- Each turn the child **truncates** the file and writes exactly one fresh envelope.
  Never append. Never leave a previous turn's content in place — a `BLOCKED:` line
  from a stale turn must never be read as the current turn's answer.
- The launch prompt and every follow-up prompt supplies a `TURN=<n>` line. The child
  echoes it as the first `KEY=VALUE` line of its envelope, directly under the sentinel
  or `ROLE_DONE`.
- The watcher discards any envelope whose `TURN=` does not match the turn it just
  sent, and treats the file as not-yet-updated (same as an empty file) until it does.

## Raw envelope → bucket

No bg child ever emits `ROLE_RESULT=`. The driver's grep target
`^(ROLE_RESULT=|ROLE_DONE$)` reads the handoff file's content, not stdout:

| First non-empty line of the handoff file | Bucket |
|---|---|
| `ROLE_DONE` (with matching `TURN=`) | done |
| `BLOCKED: <reason>` (with matching `TURN=`) | blocked |
| `NEEDS_DECISION: <question>` (with matching `TURN=`) | needs-decision |
| File empty, absent, or `TURN=` stale/missing | not-done (poll continues) |
| Liveness escape fires (`bg-liveness.sh` reports `stopped`) before any of the above | errored |

`not-done` at watcher-budget exhaustion becomes `errored (watcher_budget_exhausted)`,
same as the acpx leg's Failure behavior.

## Lifecycle

- On `done` or `errored`: the watcher sends the child a finish-and-stop instruction by
  name, then confirms `stopped` through `bg-liveness.sh` before the node ends.
- On `needs-decision`: the child is left alive. Its name is recorded in the run's
  bookkeeping so a later invocation, or a person, can resume it by message.
- On watcher crash: no stop instruction is sent. The orphan is caught by a sweep — the
  sweep reads the sidecar directories under `~/.claude/relay/bg/*/`, runs
  `bg-liveness.sh` over every recorded short id, and stops or records every child
  still alive, before the run uses a fresh runid.
- This is the contract's single stop mechanism (§Spawn authority,
  `docs/bg-dispatch-contract.md`), not a second one invented here. This skill does not
  restate it.

## Multi-turn

`[unverified]` The spikes proved session-to-session messaging from top-level sessions
only. Whether a Workflow watcher node can `SendMessage` a named session was not tested
by the spikes and could not be verified live in this task (no live session harness was
available). Per the spec's own stated fallback, v1 restricts `bg-sessions` dispatch to
roles with `one_shot: true` in `bindings/presets.yaml`. `bg-dispatch.sh` refuses a
role whose `delegate_eligible` is not `true`, and any future non-`one_shot` role must
keep the acpx leg until this property is verified and the restriction is lifted.

Every role in `bindings/presets.yaml` currently carries `one_shot: true`, so this
restriction costs nothing in practice today; it exists to stop a future
non-one-shot role from silently taking the unverified path.

When the restriction is lifted: the watcher sends the next prompt to the child by
name via SendMessage (address resolved at send time), then polls the handoff file
again. The child never messages the watcher.

## Nested dispatch

The nesting primitive is a **skill leaf**. The child's role body invokes a relay skill
by name — for example `relay:refining-specs` — and that skill generates the child's own
Workflow. The `Skill` tool call is the nesting primitive; `bg-dispatch.sh` needs
nothing new, because the child's prompt is already `preamble.md` plus the role body.

A slash-command leaf was considered and rejected. Relay command files carry
`disable-model-invocation: true` in their frontmatter, and a command cannot carry the
trailing envelope instructions the child needs to close with. Do not reintroduce it.

The nested Workflow returns immediately. The `Workflow` tool answers `Workflow launched
in background. Task ID: …`, so the child must `ToolSearch` for `TaskOutput` and
`TaskGet` and **collect the nested Workflow's result before writing its envelope**. A
child that writes `ROLE_DONE` on the launch acknowledgement reports a result that does
not exist yet.

The envelope does not change. A child running a nested Workflow still closes with
`ROLE_DONE`, `BLOCKED: <reason>`, or `NEEDS_DECISION: <question>`, with the `TURN=`
echo as the first `KEY=VALUE` line. A leaf inside the child's Workflow escalates, the
child turns that into `NEEDS_DECISION:`, and the parent watcher buckets it as
`needs-decision` exactly as it does today. No new token, no new bucket, no new routing.

Depth is capped at 1, enforced in `bg-dispatch.sh`.

This release adds no new role file and no new entry in `bindings/presets.yaml`. The
primitive is available to any existing `delegate_eligible: true` role whose body
invokes a skill.

**`[partially verified]`** The `Skill` tool is reachable from a bg child. The manual
gate — launching a real bg child through `scripts/bg-launch.sh` whose prompt invokes a
relay skill by name, and confirming from the child's transcript that a `Skill` tool
call was made and returned — has not been run yet. Running that gate is the one thing
that would lift the marker.

## Files

- `SKILL.md` (this file) — the wrapper's responsibilities, for discovery and review.
- `preamble.md` — the §1.4 identity preamble, bg-sessions variant.
- `bg-dispatch.sh` — dispatcher entry point (bash + `yq` + `jq`) implementing this
  skill's contract; launches only through `scripts/bg-launch.sh`.

## See also

- `docs/bg-dispatch-contract.md` — the shared contract this skill's dispatch and
  completion mechanics defer to.
- `docs/superpowers/specs/2026-08-19-relay-bg-engines-design.md` — §Deliverable 2.
- `skills/dispatching-acpx-agents/` — the sibling wrapper this skill mirrors.
- `skills/delegate-and-watch/SKILL.md` — the watcher; its `## The bg-sessions leg`
  section documents the poll-target and liveness-escape substitutions this skill's
  handoff file feeds.
