# Relay bg engines — design

Date: 2026-08-19
Status: approved design, pre-implementation.
Grounding: every mechanism claim below was proven or measured in live spikes. See
`2026-08-18-bg-session-messaging-spike-findings.md` (same directory). Findings are cited
as S1–S4 and by finding number.

## Goal

Add two dispatch engines to relay, both built on Claude Code background sessions and
cross-session messages:

- `--engine bg-sessions` — per-leaf dispatch. The Workflow substrate stays. Delegated
  leaves run as background Claude sessions instead of acpx workers.
- `--engine session-tree` — a new substrate. The command generates no Workflow. The main
  session orchestrates a tree of sessions that talk by message.

Both stand on one shared contract layer, built first. The build order is fixed:
contract → bg-sessions → session-tree. Each deliverable is its own PR, and each PR bumps
the plugin version — the version is the cache key for plugin distribution, and even the
contract PR ships scripts.

## Why sessions

A Workflow agent node has exactly one turn. It cannot receive a message, so it must hold
its turn open and poll (`delegate-and-watch`, TURN-LIFETIME RULE). A background session is
different: it ends its turn to wait, and an incoming message starts a new turn (S1).
Waiting costs nothing. A child can ask its parent a question and continue when the answer
arrives. This is the property that makes headless runs able to ask a person instead of
guessing.

## Deliverable 1 — the bg dispatch contract

New file: `docs/bg-dispatch-contract.md`. New scripts: `scripts/bg-launch.sh`,
`scripts/bg-liveness.sh`. The contract governs both engines. No engine may deviate from it.

### 1.1 Envelope

The first non-empty line of a child's report message keeps the exact frozen grammar from
`docs/dispatch-contract.md`:

- `ROLE_DONE` — bare terminal token.
- `BLOCKED: <reason>` — first-line sentinel.
- `NEEDS_DECISION: <question>` — first-line sentinel.
- `KEY=VALUE` lines follow, same capture grammar.

The envelope travels in the message body instead of on stdout. The frozen byte sequences
do not change, so no major version bump is needed.

Sender identity comes from the transport (`from-name` on the cross-session message), never
from the body. The spikes improvised `ROLE_DONE from <name>`; the contract forbids that
form — the body stays pure frozen grammar.

Two new tokens, **provisional** until both engines stabilize. They are not added to the
frozen set or to `tests/unit/skill-structure/test_envelope_tokens.py`:

- `DECISION: <answer>` — the downward reply to a `NEEDS_DECISION`.
- `ESCALATION from <origin>: <question>` — an operator relaying a child's question upward.
  Distinct from `BLOCKED:` so a relay is never read as the operator itself being stuck.

A message from a child that matches none of these grammars is logged and changes nothing.
No run state moves on free text (countermeasure to S2-3: a confused fork sent stand-down
orders as prose; typed grammar makes such messages inert).

### 1.2 Naming

```
<product>-<role>-<goal>-<runid>
```

- `product` — kebab slug of the product or task.
- `role` — a relay roster role (orchestrator, operator, implementer, reviewer, scout, …).
- `goal` — kebab slug of the feature or goal. Omitted for the orchestrator.
- `runid` — suffix matching `[a-z0-9]{4,8}`, chosen once per run. Mandatory: a stopped
  session keeps its name and collides with its own replacement (S4-3).

Example: `roi-dashboard-implementer-feature-a-7f3c`.

Addresses resolve at send time, never earlier. On a collision error, use the `[ref]` the
error itself prints. Never cache a ref — refs are not stable across listings (S4-3).

[inferred] Field sources, per engine:

- `product` — the repo slug (the worktree's directory name, kebab-cased), both engines.
- `role` — the role slug, drawn from the closed roster in `docs/agent-roster.md`. Never a
  free string.
- `goal` — bg-sessions: omitted (a per-leaf dispatch has no goal distinct from its role).
  session-tree: the phase or feature slug the spine assigns to the operator's subtree
  (e.g. `feature-a`), also omitted for the orchestrator itself.
- `runid` — reused, not invented, from the run's existing identifier: for bg-sessions,
  the last 4–8 characters of the Workflow's `run_id` (`wf_…`), lowercased and stripped of
  the `wf_` prefix and any non-`[a-z0-9]` characters; for session-tree, the same
  derivation applied to the runid the orchestrator allocates at the start of the run
  (§Deliverable 3, Bookkeeping). One rule, one source, no independent runid space.

[inferred] Reduced naming grammar test. `product` and `goal` cannot be split back out of
a concatenated name (both are open kebab slugs), so the test never attempts to parse
fields out of a name. It only checks what a validator can actually decide:

- total length ≤ 63 characters (a practical ceiling for session names).
- charset: lowercase `[a-z0-9-]` only.
- the name ends with a runid suffix matching `-[a-z0-9]{4,8}$`.
- the name holds a role from the closed roster in `docs/agent-roster.md`, as a
  hyphen-bounded run of tokens anywhere in the stem (the name with its runid suffix
  removed). The check is deliberately position-free. Several roster roles are themselves
  multi-word kebab slugs (`code-reviewer`, `ui-accessibility-evaluator`) and `product`
  and `goal` are open slugs of any length, so no index can locate the role without
  parsing `product` and `goal` back out — which the rule above forbids.

### 1.3 Launch

`bg-launch.sh` is the only sanctioned way to start a child. It:

1. Builds the command in the proven shape — the prompt is the LAST argument, and no
   variadic flag (`--allowedTools`, …) may sit before it. A variadic flag silently
   swallows the prompt, and the child sits idle forever (launch trap 1).

   ```bash
   claude --bg --name <name> --model <model> --permission-mode <mode> "<prompt>"
   ```

2. Confirms `intent` is non-empty in the child's `~/.claude/jobs/<short-id>/state.json`.
   Empty intent = failed launch, whatever the shell said.
3. Reports a classifier-denied launch as the typed outcome `LAUNCH_DENIED` (launch trap 2).
   A denied launch is a normal outcome, never an assumption that the child exists.

[inferred] Permission mode mapping. `bindings/presets.yaml` roles carry `permissions:
approve-all` or `permissions: approve-reads`; the CLI's `--permission-mode` takes
`acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, or `plan`. The contract
fixes one mapping, used by every launcher:

| Binding `permissions` value | CLI `--permission-mode` |
|---|---|
| `approve-all` | `bypassPermissions` — runs Bash and every tool unattended. |
| `approve-reads` | `plan` — read-only reconnaissance, no unattended edits or Bash writes. |
| (no `permissions` key) | `plan` (same as `approve-reads`) — the safe default for a role
  with no stated policy. |

`dontAsk` is forbidden for any role that must run Bash (S3-1: a child under `dontAsk`
was denied Bash outright). `bg-launch.sh` never selects `dontAsk`; it is not a target of
this mapping.

### bg-launch.sh interface

[inferred] Full interface, invented here because none exists elsewhere and both engines
are written against it.

**Arguments:**

- `--name <name>` — required. The name built per §1.2.
- `--model <model>` — required. From the binding's `modalities.claude`.
- `--permission-mode <mode>` — required. From the mapping table above.
- `--prompt-file <path>` — required. The identity preamble (§1.4) plus the role body,
  already assembled by the caller. `bg-launch.sh` reads the file and passes its contents
  as the final, non-variadic argument to `claude --bg` (§1.3 step 1) — it never accepts
  the prompt as an inline argument, to keep prompt construction out of shell quoting.
- `--fork-from <session-id>` (optional) — when present, the launch adds `--resume
  <session-id> --fork-session` to the `claude --bg` command and the caller is responsible
  for the fork preamble (§1.4). v1 of `bg-launch.sh` accepts this flag but neither engine
  in this design calls it yet: bg-sessions launches fresh children only, and session-tree
  v1 spawns flat, fresh children too (§Deliverable 3, Topology — "the orchestrator spawns
  every session flat"). The fork lines in §1.4 are reserved for a future session-tree
  iteration that forks the orchestrator's own context into an operator; until that PR,
  no caller passes `--fork-from` and the fork preamble block is dead text by design, not
  by omission.

**Short-id resolution:** `claude --bg` prints the short id to stdout at launch.
`bg-launch.sh` captures stdout and parses the short id from it directly — it never scans
`~/.claude/jobs/` by the `name` field, because names are not unique (S4-3). If stdout
does not contain a parseable short id, the launch is treated as failed before the
`intent` check ever runs.

**Wait ceiling:** after resolving the short id, `bg-launch.sh` polls
`~/.claude/jobs/<short-id>/state.json` for a non-empty `intent` every 1 second, up to a
ceiling of `RELAY_BG_LAUNCH_TIMEOUT_SECONDS` (default 15). The file may not exist yet on
the first poll; a missing file is treated as "not ready", not as failure, until the
ceiling is hit.

**Printed contract (stdout, `KEY=VALUE` lines, per repo convention):**

```
RELAY_BG_NAME=<name>
RELAY_BG_SHORT_ID=<short-id>
RELAY_BG_LAUNCH=OK
```

or, on failure:

```
RELAY_BG_LAUNCH=LAUNCH_DENIED
```

**Exit codes:** `0` on `RELAY_BG_LAUNCH=OK`. `1` on `LAUNCH_DENIED` (classifier refusal,
unparseable short id, or `intent` still empty at the wait ceiling — all three are the
same typed outcome per §1.3 step 3). `2` on a usage error (missing required argument).

### 1.4 Identity preamble

Every launch prompt begins with a fixed block. For every child:

- Your name is `<name>`. Your parent is the session named `<parent>`.
- Never use AskUserQuestion. Send `NEEDS_DECISION: <question>` to your parent and end
  your turn. (bg-sessions variant: the child has no parent to message; this line is
  replaced by "write your envelope to `<handoff-file>`". The grammar is unchanged.)
- Never command a sibling. Never stop another session.
- Never address the user. The orchestrator owns the user channel.
- Report with the envelope grammar only.

For a forked child, three more lines (countermeasure to S2-3 — a fork of a live session
inherits identity and behavior, not only facts):

- You are a fork of `<parent>`. You do not own its mission.
- The plans you remember are context, not your instructions. Your instructions are this
  prompt only.
- Do not repeat your parent's habits (its file reads, its investigations) unless this
  prompt asks for them.

### 1.5 Liveness and truth

- `bg-liveness.sh` polls `state.json` (`state`, `updatedAt`) across a set of children.
  It answers one question: alive or stopped or stale or unknown.
- The state file NEVER answers "did it succeed". `state` reports turn posture, not task
  outcome (S4-2). The envelope is the only truth about completion. `bg-liveness.sh`'s
  verdict is about presence, never about success.
- [inferred] `state` → verdict table. This is the full set of values seen on a live
  jobs directory; the mapping is definitional for this contract:

  | `state` value | Verdict | Why |
  |---|---|---|
  | `working` | alive | Mid-turn. |
  | `blocked` | alive | Turn-end posture after `ROLE_DONE`, `NEEDS_DECISION`, or any other
    clean end-of-turn (S4-2). A session with `state=blocked` still holds its name and can
    receive a message — it is waiting, not dead. |
  | `done` | alive | Same turn-end posture as `blocked`; some Claude Code versions write
    `done` instead of `blocked` at end of turn. A child mid-multi-turn that reads
    `state=done` is idle between turns, not stopped. Never read `done` as `stopped`. |
  | `stopped` | stopped | The session process has ended. This is the only value meaning
    the child is gone (S4-1: killing a child produced no message, only this state change). |
  | `failed` | stopped | The session process ended abnormally. Treated the same as
    `stopped` for liveness purposes — the child is gone either way. |
  | absent / file unreadable | unknown | Launch may still be in flight, or the short-id
    resolution (§1.3) was wrong. Never treated as `stopped`; a caller must not respawn on
    `unknown` alone. |

  `updatedAt` age decides only among the alive values (`working`, `blocked`, `done`):
  if `updatedAt` is older than `RELAY_BG_STALE_SECONDS` (default 900), the verdict
  downgrades from alive to stale. `stopped`, `failed`, and `unknown` are never
  reclassified by age.
- A dead child sends no message at all (S4-1). Any waiting parent needs a liveness check
  on the side; it cannot wait on a message that never comes.

### 1.6 Spawn authority

The orchestrator spawns every session. Operators coordinate and never spawn — a child
under `--permission-mode dontAsk` cannot run Bash (S3-1). Permission mode is a per-role
binding concern; the contract only records the constraint.

[inferred] Stop mechanism, the single statement both engines defer to: a session is
stopped by sending it a finish-and-stop instruction by name via SendMessage, then
confirming the `stopped` verdict through `bg-liveness.sh` (§1.5). No session stops
another session by any other means, and no session stops a sibling — only the session
that spawned the tree, or the watcher that dispatched a leaf, issues a stop.

## Deliverable 2 — `--engine bg-sessions` (per-leaf dispatch)

The one-Workflow doctrine is untouched. This engine swaps what a delegated leaf runs.

- **Axis.** `scripts/parse-engine-agent.sh` gains the enum value `bg-sessions`, with the
  invariant `bg-sessions ⇒ claude` (same shape as `in-session ⇒ claude`; there is no
  codex leg). Pinnable in `.claude/relay.json` like the other engines.
- **Bindings.** `bindings/presets.yaml` is unchanged in v1. The same `delegate_eligible`
  flag decides which roles delegate. The worker model comes from the binding's existing
  `modalities.claude`.
- **Dispatch.** New skill `relay:dispatching-bg-agents`, a mirror of
  `relay:dispatching-acpx-agents`, conforming to the same
  `(role_slug, binding, inputs) → result` wrapper (§5.1). It launches through
  `bg-launch.sh`, in the run's worktree (children inherit the launcher's cwd), with the
  identity preamble plus one extra line: *write your envelope to `<handoff-file>` — you
  have no parent to message.*
  [inferred] Command wiring: `commands/implement.md`, `refine.md`, `execute.md`, and
  `drive.md` each carry a "Delegation wiring note" keyed on `$RELAY_ENGINE`. That note
  gains a third arm for `bg-sessions`, alongside `acpx` and `smart-routing`, in all four
  commands — bg-sessions is a per-leaf dispatch engine and every command that delegates
  leaves is in scope. Each command's `argument-hint` and its Step 0.25 engine question add
  `bg-sessions` as a third option next to the current two. Without this edit,
  `--engine bg-sessions` parses but every command's wiring note falls through to the
  in-session path — a silent, unreported no-op.
  [inferred] bg sidecar: the counterpart of acpx's `~/.acpx/sessions/${session}.env`.
  The dispatcher writes `~/.claude/relay/bg/${runid}/${role_slug}.env` before launch,
  containing:

  ```
  RELAY_BG_NAME=<name>
  RELAY_BG_SHORT_ID=<short-id>
  RELAY_BG_HANDOFF=<handoff-file-path>
  RELAY_BG_MODEL=<model>
  RELAY_BG_PERMISSION_MODE=<mode>
  RELAY_BG_MAX_TURNS=<n>
  ```

  `delegate-and-watch` step 1 sources this file instead of the acpx sidecar when
  `$RELAY_ENGINE` is `bg-sessions`, and branches its poll target (handoff file vs. acpx
  turn log) on which sidecar it found.
- **Completion.** The envelope travels in an artifact file, not a message: the watcher is
  a Workflow node and cannot receive messages.
  [inferred] Handoff file contract: path
  `$WORKTREE/.relay-bg/<runid>/<role_slug>.envelope`. The dispatcher creates the
  directory before launch; the child is the only writer of the file itself. Each turn the
  child truncates the file and writes exactly one fresh envelope — never appends, never
  leaves a prior turn's content in place, so a `BLOCKED:` line is never silently
  overwritten and lost without first being read by the watcher's poll (the watcher polls
  every turn's file before the next prompt is sent). To stop a finished turn's sentinel
  from being read as the current turn's answer, the launch prompt (turn 1) and every
  follow-up prompt (§Multi-turn, below) supplies a `TURN=<n>` line the child must echo as
  the first `KEY=VALUE` line of its envelope, directly under the sentinel or `ROLE_DONE`.
  The watcher discards any envelope whose `TURN=` does not match the turn it just sent
  and treats the file as not-yet-updated (same as an empty file) until it does.

  The watcher keeps `delegate-and-watch`'s bounded foreground poll with two substitutions:
  it greps the handoff file instead of the acpx turn log, and its liveness escape is
  `bg-liveness.sh` reporting `stopped` (§1.5) instead of the bracketed `pgrep`.

  [inferred] Raw-envelope → bucket mapping, replacing the `ROLE_RESULT=` grep for the bg
  leg (no bg child ever emits `ROLE_RESULT=`; the driver's grep target
  `^(ROLE_RESULT=|ROLE_DONE$)` is read against the handoff file's content, not stdout):

  | First non-empty line of the handoff file | Bucket |
  |---|---|
  | `ROLE_DONE` (with matching `TURN=`) | done |
  | `BLOCKED: <reason>` (with matching `TURN=`) | blocked |
  | `NEEDS_DECISION: <question>` (with matching `TURN=`) | needs-decision |
  | File empty, absent, or `TURN=` stale/missing | not-done (poll continues) |
  | Liveness escape fires (`bg-liveness.sh` reports `stopped`) before any of the above | errored |

  `not-done` at watcher-budget exhaustion becomes `errored (watcher_budget_exhausted)`,
  same as the Failure behavior table.
- **Exit buckets.** Unchanged: done / not-done / blocked / needs-decision / errored.
  `needs-decision` stays terminal, session left open-but-detached, exactly as acpx today.
  [inferred] Lifecycle after a terminal bucket: on `done` or `errored`, the watcher sends
  the child a finish-and-stop instruction by name via SendMessage, then confirms
  `stopped` through `bg-liveness.sh` before the node ends. On `needs-decision`, the child
  is left alive and its name is recorded in the run's bookkeeping so a later
  `delegate-and-watch` invocation (or a human) can resume it by message. On watcher crash
  (the Workflow node itself never completes), no stop instruction is ever sent; the
  orphaned child is caught by a sweep of the next run's manifest-equivalent bookkeeping,
  which checks liveness on every previously-recorded name before assuming a fresh runid
  is collision-free. This is the same stop mechanism session-tree uses (§Deliverable 3,
  End of run); §1.6 is the contract's single statement of it, and both engines defer to
  it rather than each inventing their own.
- **Multi-turn.** Watcher → child only. The watcher sends the next prompt to the child by
  name via SendMessage (address resolved at send time), then polls the handoff file again.
  The child never messages the watcher. `[unverified]` The spikes proved session→session
  messaging only from top-level sessions; a Workflow node sending to a named session was
  not tested. The bg-sessions PR must verify this first. Fallback if it fails: v1
  restricts bg-sessions to `one_shot: true` roles, and multi-turn roles keep the acpx leg.
- **Not this engine's job.** Free waiting and live question-answer belong to
  session-tree. This engine's value is dropping the acpx/codex dependency and gaining
  native session resume, at semantics identical to the acpx leg.

## Deliverable 3 — `--engine session-tree` (new substrate)

- **Doctrine.** `docs/orchestration-substrates.md` records this as the second documented
  exception to "every L3 command generates one Workflow", next to `/relay:drive`. Under
  `session-tree` the command generates no Workflow. MAIN — the session running the
  command — is the orchestrator. The §4.2.1 spine still governs WHAT happens; only the
  substrate changes: spine roles run as sessions, not `agent()` nodes.
  [inferred] `session-tree` is an engine-axis value, resolving the disagreement between
  Deliverable 2 and this heading: `scripts/parse-engine-agent.sh` gains the enum value
  `session-tree`, with the invariant `session-tree ⇒ claude` (same shape as
  `bg-sessions ⇒ claude` and `in-session ⇒ claude` — there is no codex leg for
  session-tree either) and the same default-agent arm as `in-session`. The enum error
  strings list `session-tree` alongside the existing values. This PR also adds the new
  skill `relay:orchestrating-session-trees`, which holds the orchestrator prose (spawn
  the tree, route questions, run the end-of-run stop protocol) that has no other named
  home, and it edits `commands/implement.md` Step 1: when `$RELAY_ENGINE` resolves to
  `session-tree`, Step 1 skips Workflow generation entirely and instead invokes
  `relay:orchestrating-session-trees` in the current (MAIN) session. Every other L3
  command's Step 1 is unchanged — Scope v1 below confines `session-tree` to
  `/relay:implement`, so `refine.md`, `execute.md`, and `drive.md` reject the value with
  the standard engine-not-supported error.
- **Scope v1.** `/relay:implement` only. Refine and verify loops keep their current
  substrates.
- **Topology.** The orchestrator spawns every session flat (S3-1). Parent-child is
  logical, set by the identity preamble, not by who spawned whom. v1 cap: one operator
  per goal, at most three workers under it (the proven S3 shape: implementer + reviewer).
  Fan-out and cost are untested (findings, "still unknown"), so the cap is deliberate and
  the report states it when it binds.
- **Bookkeeping.** [inferred] The run manifest is its own artifact, not an extension of
  `record-run-intent.sh`'s file: `record-run-intent.sh` appends one advisory line to
  `~/.claude/relay/runs.jsonl` after a Workflow tool returns, and session-tree runs no
  Workflow and allocates no `wf_…` id, so that append point never fires here. The
  manifest instead lives at `~/.claude/relay/runs/<runid>/manifest.json`, one file per
  run, holding the runid and every session's name, launch id, role, logical parent, and
  phase status. `<runid>` is allocated by the orchestrator at the start of the run (a
  fresh `[a-z0-9]{4,8}` string, the same shape §1.2 requires and the same value fed into
  every session name's runid suffix) — not read from `record-run-intent.sh`, which never
  runs. The orchestrator rewrites the whole file atomically (write to a temp path, then
  rename) at each spawn and each envelope, so the manifest always holds current state,
  never a log of past events. A manifest write failure is FATAL for session-tree — unlike
  the advisory `runs.jsonl` line, which `record-run-intent.sh`'s own doctrine allows to
  fail without taking down a run, the manifest is the only resume path here and a failed
  write must stop the orchestrator's turn with an error, not continue silently. Resume
  after an orchestrator crash = read the manifest, poll liveness on each name, re-attach
  or respawn. This replaces Workflow-native resume. `record-run-intent.sh` itself is
  unchanged; session-tree simply never calls it.
- **Waiting.** `[unverified]` Free waiting — the orchestrator ends its turn and an
  envelope re-invokes it — was proven by S1 for a BACKGROUND child, not for MAIN. MAIN
  under session-tree is a foreground session mid-way through a slash command; S1 never
  measured whether an inbound message re-invokes such a session or whether a re-invoked
  turn still holds the command's run state. This is the load-bearing property of the
  whole substrate, and the design's grounding rule ("every mechanism claim below was
  proven or measured") is not met for it. The first task of the Deliverable 3 PR must
  verify it directly: send an envelope to an idle MAIN session mid-command and confirm
  both that it re-invokes and that the re-invoked turn still holds command state (the
  manifest path, the runid, and the spawned children's names). Fallback if it fails: the
  orchestrator holds a bounded poll over the manifest instead, the same shape as
  `delegate-and-watch`'s watcher, and free waiting is deferred to a later iteration. Only
  once this is confirmed does the rest of this section hold: the orchestrator also arms a
  long fallback heartbeat (ScheduleWakeup) that runs `bg-liveness.sh` across the
  manifest. The heartbeat catches silence; it never polls for results.
- **Questions.** `NEEDS_DECISION` flows worker → operator → orchestrator. The operator
  answers when the run rubric covers it; otherwise it relays as `ESCALATION from …`. The
  orchestrator answers from run context when it can. When the question is genuinely the
  human's: an interactive run uses AskUserQuestion (the orchestrator is the one session
  that owns the user channel); a headless run escalates one hop further, by message to
  the orchestrator's own parent session.
- **End of run.** The orchestrator sends each child a finish-and-stop instruction,
  confirms `stopped` via liveness, and names any child it could not stop. Stopped
  sessions keep their names; the next run's fresh runid prevents collision.

## Failure behavior

Every spike failure signal has one owner and one response. No path ever reports success
from a state file.

| Failure | bg-sessions (watcher) | session-tree (orchestrator) |
|---|---|---|
| Launch denied / empty `intent` | `LAUNCH_DENIED`, one retry, then `errored` | Same, recorded in the manifest |
| Child dead, no envelope | Liveness escape fires → `errored` | Heartbeat finds it; one respawn under a fresh name, then `errored` |
| Child alive but silent | Watcher budget exhausts → `errored (watcher_budget_exhausted)` | One nudge message, then `errored` after a stated staleness threshold |
| Send refused: no such agent / collision / HTTP 409 | Re-resolve via ListAgents; use the error's `[ref]`; a 409 routes to the dead-child path | Same |
| Fork misidentification | Preamble (§1.4) + inert free text (§1.1) | Same |

## Tests

- Unit (existing pytest layout under `tests/`):
  - `bg-launch.sh` — prompt-last construction, `intent` check against `state.json`
    fixtures, `LAUNCH_DENIED` path.
  - `bg-liveness.sh` — alive / stopped / stale against state fixtures.
  - Naming grammar — accept/reject cases, runid presence.
  - Provisional token grammar (`DECISION:`, `ESCALATION from …:`) — in their own test
    file, explicitly NOT in `test_envelope_tokens.py`'s frozen set.
- Skill-structure tests cover the new skills' frontmatter, per the existing convention.
- Live validation: the S1 round trip, scripted, documented in the contract doc. It cannot
  run in CI (it launches real sessions). It is re-run manually before each engine PR
  merges, and the PR description records the run.

## Not doing, deliberately

Each omission has a named add-later path.

- **No codex/opencode workers in bg engines.** The acpx leg keeps them. Add-later:
  interop binding if wanted.
- **No fan-out past the v1 cap.** Add-later: a load spike (ten workers messaging one
  operator) unlocks a bigger cap.
- **session-tree v1 covers the implement spine only.** Add-later: refine and verify
  loops migrate after the implement path has run clean in practice.
- **smart-routing does not learn the bg legs in v1.** Add-later: routing rules once both
  engines have cost data.
- **No token cost accounting in v1** beyond noting it is unknown in the manifest.
  Add-later: per-child cost capture once the harness exposes it.
- **The auto-spec skill stays punted.** It was this session's original goal and is now a
  consumer of session-tree's headless escalation. Its settled decisions are recorded in
  Appendix B so a future session does not re-litigate them.

## Appendix A — decision record (this session)

| # | Question | Decision |
|---|---|---|
| 1 | Keep the prompt's adversarial debate phase in the auto-spec skill? | Slim design-level debate before the spec is written; `refine-spec` still runs after. |
| 2 | What counts as "a spec exists"? | Path named in the task wins; else scan `docs/superpowers/specs/` and confirm one plausible match with the user; never decide fuzzily in silence. |
| 3 | Headless run, no spec, nobody to confirm? | All three offered options rejected. The user's fourth option — ask a parent session by message — became this design. Session pivoted. |
| 4 | Substrate or per-leaf? | Both: `--engine session-tree` and `--engine bg-sessions`. |
| 5 | What must the prototype prove? | All four: two-way messaging, fork inheritance, three-level tree, failure behavior. All ran; see the findings doc. |
| 6 | Sequence? | Spikes first, then spec. Done in that order. |
| 7 | Build order? | Contract first, then bg-sessions, then session-tree. |

Spike verdicts: S1 PASS, S2 PASS with hazard S2-3 (fork identity), S3 PASS with blocker
S3-1 (dontAsk children cannot spawn), S4 four typed signals recorded. Loops that hit
caps: none. Assumptions made without a proxy answer: none.

## Appendix B — parked auto-spec decisions

For the future session that builds the auto-spec skill on top of session-tree:

1. The skill runs a slim design-level debate on the DESIGN before the spec is written.
   The spine's `refine-spec` node still pressure-tests the written spec after.
2. Spec detection: a spec path named in the task text wins. Otherwise scan
   `docs/superpowers/specs/` for a topic match; one plausible match → ask "use this
   spec?"; no match → offer generation. A fuzzy match never decides silently.
3. The headless confirmation question is answered by this design: the run escalates
   `NEEDS_DECISION` to its parent session instead of using AskUserQuestion.

## Refinement Status

Refinement: CONVERGED round 1.

Gaps closed:

- §1.5 Liveness and truth — added the `state` → verdict table (`working`/`blocked`/
  `done` → alive, `stopped`/`failed` → stopped, absent/unreadable → unknown) and stated
  that `updatedAt` age decides only among the alive values.
- Deliverable 2, Completion — pinned the handoff file's path, writer, truncate-then-write
  rule, the `TURN=<n>` marker that keys the watcher's read, and the raw-envelope →
  bucket table replacing the acpx `ROLE_RESULT=` grep.
- §1.3 Launch; §1.6 Spawn authority — added the binding `permissions` → CLI
  `--permission-mode` mapping table and named `dontAsk` as forbidden for any
  Bash-running role (S3-1).
- §1.3 Launch — added `bg-launch.sh`'s full interface: arguments, short-id resolution by
  parsing launch stdout (never scanning by `name`, per S4-3), the bounded wait ceiling,
  the printed `KEY=VALUE` contract, and exit codes; marked the fork preamble in §1.4 as
  reserved and unused by any v1 caller.
- §1.2 Naming — gave per-engine field sources for `product`/`role`/`goal`, tied `runid`
  to the existing run identifier instead of a second runid space, and reduced the naming
  test to length/charset/runid-suffix/roster-role checks that do not require parsing
  `product` or `goal` back out of a name.
- Deliverable 3, heading and Doctrine — resolved the enum disagreement: `session-tree`
  is a `parse-engine-agent.sh` value with invariant `session-tree ⇒ claude`, named the
  new skill `relay:orchestrating-session-trees`, and named the exact
  `commands/implement.md` Step 1 branch that skips Workflow generation.
- Deliverable 2, Dispatch and Completion — named the four command files' wiring-note and
  Step 0.25 edits in scope for `bg-sessions`, and specified the bg sidecar
  (`~/.claude/relay/bg/<runid>/<role_slug>.env`) as the counterpart of acpx's
  `${session}.env`.
- Deliverable 2, Exit buckets — added the stop lifecycle after `done`/`errored`, the
  open-but-detached rule for `needs-decision`, and the crash-orphan sweep; stated the
  single stop mechanism once in §1.6 for both engines to share.
- Deliverable 3, Bookkeeping — gave the manifest its own path
  (`~/.claude/relay/runs/<runid>/manifest.json`), stated it is rewritten atomically at
  each spawn and envelope, stated a manifest write failure is FATAL (unlike the advisory
  `runs.jsonl` line), and stated the runid is orchestrator-allocated since no Workflow
  runs to produce one.
- Deliverable 3, Waiting — tagged the MAIN re-invocation property `[unverified]`, added a
  first-task verification step, and named the bounded-manifest-poll fallback if it fails.
