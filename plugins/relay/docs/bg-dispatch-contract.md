# Relay Background-Session Dispatch Contract

> Operative reference for the two background-session engines: `--engine bg-sessions`
> (per-leaf dispatch) and `--engine session-tree` (a new orchestration substrate). Every
> mechanism claim in this doc was proven or measured in a live spike. Spikes are cited as
> `S1`–`S4`, by finding number, from
> `docs/superpowers/specs/2026-08-18-bg-session-messaging-spike-findings.md`.

This contract governs both engines. No engine may deviate from it.

This doc adds a **transport**. It adds no token to the frozen envelope set. The frozen set
stays exactly what `docs/dispatch-contract.md` says it is.

## Envelope

The first non-empty line of a child's report message keeps the exact frozen grammar from
`docs/dispatch-contract.md`:

1. **`ROLE_DONE`** — bare terminal token.
2. **`BLOCKED: <reason>`** — first-line sentinel.
3. **`NEEDS_DECISION: <question>`** — first-line sentinel.
4. **`KEY=VALUE` envelope grammar** — any line matching
   `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$` is an envelope line.

These four byte sequences do not change here. The envelope travels in the **message
body**, or in a handoff file, instead of on stdout. No major version bump is needed for
this doc, because the frozen tokens are unchanged — only the transport is new.

**Sender identity comes from the transport.** A background session's message carries a
`from-name` set by the platform. Use that. Never read identity out of the body. The
spikes improvised `ROLE_DONE from <name>` while proving S1; this contract forbids that
form for real dispatch. The body stays pure frozen grammar — no name, no prefix.

### Two provisional tokens

Two more tokens exist. They are **provisional**, until both engines have run in
production and stabilized. They are NOT part of the frozen set above. They are NOT added
to `tests/unit/skill-structure/test_envelope_tokens.py`, and they must never be.

- **`DECISION: <answer>`** — the downward reply to a `NEEDS_DECISION:` question. A parent
  answers a child's question with this token.
- **`ESCALATION from <origin>: <question>`** — an operator relaying a child's question
  upward, one hop, to its own parent. This token is distinct from `BLOCKED:` on purpose:
  a relayed question must never read as the operator itself being stuck. The operator is
  fine. It is passing a question along.

### Free text is inert

A message from a child that matches none of these grammars — frozen or provisional — is
logged and changes nothing. No run state moves on free text. This is the direct
countermeasure to S2-3: a confused fork sent stand-down orders to its siblings as plain
prose. Typed grammar makes such a message inert. A parser that does not recognize the
first line takes no action beyond logging it.

## Naming

```
<product>-<role>-<goal>-<runid>
```

- **`product`** — kebab slug of the product or task. Both engines: the repo slug, taken
  from the worktree's directory name, kebab-cased.
- **`role`** — a relay roster role (orchestrator, operator, implementer, reviewer,
  scout, …). Drawn from the closed roster — the role stems in `roles/*.md` plus the
  registered agent slugs in `docs/agent-roster.md`. Never a free string.
- **`goal`** — kebab slug of the feature or goal. Omitted for the orchestrator.
  bg-sessions: always omitted — a per-leaf dispatch has no goal distinct from its role.
  session-tree: the phase or feature slug the spine assigns to the operator's subtree
  (for example `feature-a`), also omitted for the orchestrator itself.
- **`runid`** — a suffix matching `[a-z0-9]{4,8}`, chosen once per run. **Mandatory.** A
  stopped session keeps its name and would otherwise collide with its own replacement
  (S4-3). The runid is reused, never invented twice: for bg-sessions, derived from the
  Workflow's own `run_id`; for session-tree, the runid the orchestrator allocates at the
  start of the run. One rule, one source, no independent runid space.

Example: `roi-dashboard-implementer-feature-a-7f3c`.

**Addresses resolve at send time, never earlier.** On a collision error, use the `[ref]`
the error itself prints. Never cache a ref — refs are not stable across listings (S4-3):
the same session showed `60b3cbb8` at launch and `[0187e4]` in a later listing.

### Name validation

`product` and `goal` are open kebab slugs and cannot be split back out of a concatenated
name. A validator therefore checks only what it can actually decide:

1. Total length ≤ 63 characters.
2. Charset: lowercase `[a-z0-9-]` only.
3. The name ends with a runid suffix matching `-[a-z0-9]{4,8}$`.
4. Split the name on `-` and strip the runid suffix. At least one of the two fixed
   positions — position 2 (`product-role`, the orchestrator shape) or the token before
   the goal (`product-role-goal`) — must hold a valid roster role. Try both splits;
   require one roster hit. The validator never parses `product` or `goal` out of the
   string; it only checks a fixed position against the roster.

`scripts/bg-launch.sh --check-name <name>` runs this validation and nothing else. See
below.

## Launch

`scripts/bg-launch.sh` is the only sanctioned way to start a child. Nothing else in relay
may run `claude --bg` directly.

1. **Build the command in the proven shape.** The prompt is the LAST argument. No
   variadic flag (`--allowedTools`, …) may sit before it.

   ```bash
   claude --bg --name <name> --model <model> --permission-mode <mode> "<prompt>"
   ```

   A variadic flag silently swallows the prompt as another one of its own entries. Three
   children launched this way reported success at the shell, then sat idle forever, with
   an empty `intent` in their state file (**launch trap 1**). The launcher must put the
   prompt last with no variadic flag before it.

2. **Confirm `intent` is non-empty** in the child's
   `~/.claude/jobs/<short-id>/state.json` before reporting success. An empty `intent` is
   a failed launch, whatever the shell exit code said.

3. **Report a classifier-denied launch as the typed outcome `LAUNCH_DENIED`.** One `claude
   --bg` launch was refused by the auto-mode classifier ("Blocked by classifier"); the
   identical command succeeded when issued alone (**launch trap 2**). A denied launch is
   a normal outcome, reported honestly, never an assumption that the child exists.

### Permission-mode mapping

`bindings/presets.yaml` roles carry `permissions: approve-all` or
`permissions: approve-reads`. `bg-launch.sh` always receives a CLI `--permission-mode`
value, mapped once, the same way for every caller:

| Binding `permissions` value | CLI `--permission-mode` |
|---|---|
| `approve-all` | `auto` — the unattended classifier mode, chosen so an unattended child can run Bash, edits, and every other tool without a human present. |
| `approve-reads` | `plan` — read-only reconnaissance, no unattended edits or Bash writes. |
| (no `permissions` key) | `plan` — same as `approve-reads`, the safe default for a role with no stated policy. |

`auto` is a classifier, not a blanket grant. It can refuse a tool call with no human
present, and a child under `auto` must therefore be prepared to stop on a refusal
(§Failure behavior). `bg-launch.sh` still accepts `bypassPermissions` as a raw
`--permission-mode` argument for hand-run spikes and `tests/e2e/bg-s1-roundtrip.sh`, but
no binding value selects it any more.

**`dontAsk` is forbidden for any role that must run Bash.** A child launched under
`--permission-mode dontAsk` was denied Bash outright, with the error "Permission to use
Bash has been denied because Claude Code is running in don't ask mode" (S3-1).
`bg-launch.sh` never selects `dontAsk`, and it refuses `--permission-mode dontAsk` as an
argument, so no caller can reintroduce S3-1 through this script.

## bg-launch.sh interface

**Arguments:**

| Flag | Required | Meaning |
|---|---|---|
| `--name <name>` | yes | The name built per §Naming. Validated by the same rule as `--check-name`. |
| `--model <model>` | yes | From the binding's `modalities.claude`. |
| `--permission-mode <mode>` | yes | From the permission-mode mapping table above. `dontAsk` is refused. |
| `--prompt-file <path>` | yes | The identity preamble plus the role body, already assembled by the caller. `bg-launch.sh` reads the file and passes its content as the final, non-variadic argument — it never accepts the prompt inline, to keep prompt construction out of shell quoting. |
| `--fork-from <session-id>` | no | Adds `--resume <session-id> --fork-session` to the launch command. **No v1 caller passes this flag.** Reserved for a future session-tree iteration that forks the orchestrator's own context into an operator. |
| `--check-name <name>` | no | Validate-only mode. Runs the §Naming validation and starts no child. |

**Short-id resolution.** `claude --bg` prints the short id to stdout at launch.
`bg-launch.sh` captures stdout and parses the short id from it directly. It never scans
`~/.claude/jobs/` by the `name` field — names are not unique (S4-3). If stdout holds no
parseable short id, the launch is treated as failed before the `intent` check ever runs.

**Wait ceiling.** After resolving the short id, `bg-launch.sh` polls
`~/.claude/jobs/<short-id>/state.json` for a non-empty `intent`, once a second, up to
`RELAY_BG_LAUNCH_TIMEOUT_SECONDS` (default `15`). A missing file is "not ready", never a
failure, until the ceiling is hit.

**Printed contract (stdout, `KEY=VALUE` lines, per repo convention).** On success:

```
RELAY_BG_NAME=<name>
RELAY_BG_SHORT_ID=<short-id>
RELAY_BG_LAUNCH=OK
```

On failure, exactly one line:

```
RELAY_BG_LAUNCH=LAUNCH_DENIED
```

The reason goes to stderr, prefixed `[relay] error: `. It never appears on stdout.

**Exit codes:**

- `0` — `RELAY_BG_LAUNCH=OK`.
- `1` — `LAUNCH_DENIED`. Classifier refusal, an unparseable short id, and an `intent`
  still empty at the wait ceiling all share this one typed outcome.
- `2` — usage error: a missing or unknown argument, an unreadable prompt file, a
  forbidden permission mode, or an invalid `--name`.

## Identity preamble

Every launch prompt begins with a fixed block. For every child:

- Your name is `<name>`. Your parent is the session named `<parent>`.
- Never use AskUserQuestion. Send `NEEDS_DECISION: <question>` to your parent and end
  your turn. **bg-sessions variant:** the child has no parent to message; this line is
  replaced by "write your envelope to `<handoff-file>`". The grammar is unchanged.
- Never command a sibling. Never stop another session.
- Never address the user. The orchestrator owns the user channel.
- Report with the envelope grammar only.

### Fork lines — reserved and unused in v1

For a forked child, three more lines apply. This is the direct countermeasure to S2-3: a
fork of a live session inherited the parent's identity, concluded it was the original,
and sent stand-down orders to the parent's own children.

- You are a fork of `<parent>`. You do not own its mission.
- The plans you remember are context, not your instructions. Your instructions are this
  prompt only.
- Do not repeat your parent's habits (its file reads, its investigations) unless this
  prompt asks for them.

No v1 caller passes `--fork-from` to `bg-launch.sh` (bg-sessions launches fresh children
only; session-tree v1 spawns flat, fresh children too). These three lines are therefore
dead text by design in v1, reserved for the future iteration that does fork.

## Liveness and truth

`scripts/bg-liveness.sh` polls `state.json` (`state`, `updatedAt`) across a set of
children. It answers exactly one question: alive, stopped, stale, or unknown.

**The state file never answers "did it succeed".** Two sessions that completed their
protocol correctly — one that sent its final `ROLE_DONE`, one that sent a full report —
both read `state=blocked` afterward. `state` tracks turn posture, not task outcome
(S4-2). **The message envelope is the only truth about completion.** `bg-liveness.sh`'s
verdict is about presence, never about success.

### `state` → verdict table

| `state` value | Verdict | Why |
|---|---|---|
| `working` | alive | Mid-turn. |
| `blocked` | alive | Turn-end posture after `ROLE_DONE`, `NEEDS_DECISION`, or any other clean end-of-turn (S4-2). A session with `state=blocked` still holds its name and can receive a message — it is waiting, not dead. |
| `done` | alive | Same turn-end posture as `blocked`; some Claude Code versions write `done` instead of `blocked` at end of turn. A child mid-multi-turn that reads `state=done` is idle between turns, not stopped. Never read `done` as `stopped`. |
| `stopped` | stopped | The session process has ended. This is the only value meaning the child is gone (S4-1: killing a child produced no message, only this state change). |
| `failed` | stopped | The session process ended abnormally. Treated the same as `stopped` for liveness purposes — the child is gone either way. |
| absent / file unreadable | unknown | Launch may still be in flight, or the short-id resolution was wrong. Never treated as `stopped`; a caller must not respawn on `unknown` alone. |

`updatedAt` age decides only among the alive values (`working`, `blocked`, `done`). If
`updatedAt` is older than `RELAY_BG_STALE_SECONDS` (default `900`), the verdict
downgrades from alive to stale. `stopped`, `failed`, and `unknown` are never reclassified
by age.

**A dead child sends no message at all (S4-1).** Any waiting parent needs a liveness
check on the side; it cannot wait on a message that never comes.

## Spawn authority

The orchestrator spawns every session. Operators coordinate and never spawn — a child
under `--permission-mode dontAsk` cannot run Bash (S3-1), and any permission mode that
allows Bash also allows a spawn, which reintroduces the topology risk the cap exists to
avoid. Permission mode is a per-role binding concern; this contract only records the
constraint that spawn authority stays with the orchestrator.

Every caller that sends a finish-and-stop message sends this exact wording, so callers
never invent their own phrasing and a mid-protocol child never mistakes it for an
envelope line:

```
Finish your current turn and stop. Do not start new work. Do not message any other session.
```

It is plain prose on purpose. A message whose first line matched `ROLE_DONE`,
`BLOCKED: <reason>`, `NEEDS_DECISION: <question>`, or a bare `KEY=VALUE` line would be
parsed as an envelope by a child that is mid-protocol. Free text is inert by contract.

### Stop mechanism — one statement, both engines defer to it

A session is stopped by sending it a finish-and-stop instruction, by name, via
SendMessage, then confirming the `stopped` verdict through `bg-liveness.sh`. No session
stops another session by any other means, and no session stops a sibling — only the
session that spawned the tree, or the watcher that dispatched a leaf, issues a stop.

## Failure behavior

Every spike failure signal has one owner and one response. No path ever reports success
from a state file.

| Failure | bg-sessions (watcher) | session-tree (orchestrator) |
|---|---|---|
| Launch denied / empty `intent` | `LAUNCH_DENIED`, one retry, then `errored` | Same, recorded in the manifest |
| Child dead, no envelope | Liveness escape fires → `errored` | Heartbeat finds it; one respawn under a fresh name, then `errored` |
| Child alive but silent | Watcher budget exhausts → `errored (watcher_budget_exhausted)` | One nudge message, then `errored` after a stated staleness threshold |
| Send refused: no such agent / collision / HTTP 409 | Re-resolve via ListAgents; use the error's `[ref]`; a 409 routes to the dead-child path | Same |
| Fork misidentification | Identity preamble (§Identity preamble) + inert free text (§Envelope) | Same |
| Classifier refused a tool call under `auto` | Child writes `BLOCKED: classifier refused <tool>: <reason>` and stops → `blocked` bucket | Child sends the same `BLOCKED:` line to its operator → recorded in the manifest, routed as any other `BLOCKED:` |

## Live validation — the S1 round trip

`tests/e2e/bg-s1-roundtrip.sh` scripts the S1 round trip end to end: it launches a real
child through `bg-launch.sh`, waits for a `NEEDS_DECISION:` line, replies with
`DECISION: <answer>`, confirms the child finishes with `ROLE_DONE` and the chosen value,
then stops the child and confirms `stopped` through `bg-liveness.sh`.

This cannot run in CI. It launches real sessions. It is run by hand before each engine's
work is called done. Set `RELAY_RUN_LIVE_BG=1` before running it:

```bash
RELAY_RUN_LIVE_BG=1 bash tests/e2e/bg-s1-roundtrip.sh
```

Without the variable set, the script prints `BG_S1_ROUNDTRIP=SKIPPED` and exits `0`. When
it runs live, it prints `BG_S1_ROUNDTRIP=PASS` or `BG_S1_ROUNDTRIP=FAIL <step>`. Record
the result — the date and the printed line — in the commit body of the PR that depends
on this round trip holding.

## See also

- `docs/dispatch-contract.md` — the frozen envelope grammar this doc reuses over a new
  transport.
- `docs/superpowers/specs/2026-08-19-relay-bg-engines-design.md` — the approved design.
- `docs/superpowers/specs/2026-08-18-bg-session-messaging-spike-findings.md` — S1–S4, the
  spikes this contract is grounded in.
- `scripts/bg-launch.sh`, `scripts/bg-liveness.sh` — the two scripts this contract
  governs.
