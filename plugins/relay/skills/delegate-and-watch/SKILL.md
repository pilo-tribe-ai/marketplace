---
name: delegate-and-watch
description: Use to background one acpx worker turn, block on it in the same turn with a bounded foreground poll, classify the outcome into one of five exit buckets (done/not-done/blocked/needs-decision/errored), and route via a router-loop — the watcher accumulates at each turn boundary, so context cost is O(turns).
user-invocable: false
---

<!-- EXECUTION PATH: run_in_background + blocking in-turn poll (never end the turn while waiting) -->

# delegate-and-watch

delegate-and-watch backgrounds one acpx worker turn, blocks on that turn inside the same
watcher turn with a bounded foreground poll, and routes through a five-bucket gate on each
turn boundary.

## TURN-LIFETIME RULE (non-negotiable)

- **Turn end IS termination.** An agent node has exactly one turn. When its final message is
  emitted the process is torn down; nothing resumes it, and no notification is delivered to a
  turn that has ended. Any child process still running is orphaned.
- **Never end a turn while waiting.** If the final message would say *"awaiting"*, *"parking
  until"*, *"I'll classify once it exits"*, or *"the harness will notify me"*, the node has
  already failed.
- **`park` is not available to an agent node.** It is a Workflow-graph control-flow primitive;
  a leaf has no resumable pause.
- **`Monitor` is not a wait mechanism here.** It arms an out-of-band watcher whose event is
  delivered to a future turn. There is no future turn.
- **Backgrounding is permitted; abandoning is not.** `run_in_background: true` is correct only
  when it is immediately followed, in the same turn, by a blocking in-turn poll.
- **On budget exhaustion, emit a typed failure, never park.** Surface `ROLE_RESULT=ERRORED`
  with `ERRORED_REASON=watcher_budget_exhausted`. A typed failure beats a null node.

The mandated wait primitive is one foreground `Bash` call that does not return until the
condition holds or a bounded timeout expires, re-issued as many times as the worker needs:

```bash
timeout "${WATCH_BUDGET:-580}" bash -c '
  until grep -qE "^(ROLE_RESULT=|ROLE_DONE$)" "'"$OUT"'" 2>/dev/null \
     || ! pgrep -f "[a]cpx-dispatch.sh" >/dev/null 2>&1; do
    sleep 10
  done'
```

The bracket in `"[a]cpx-dispatch.sh"` is load-bearing. `pgrep -f` matches against whole
command lines, and this very command line contains the pattern — written plainly, `pgrep`
matches its own `bash -c` and the liveness escape can never fire, so a worker that dies
without writing an envelope burns the full budget instead of being detected. The bracketed
form still matches the real dispatch and no longer matches itself.

`$OUT` is the worker's turn-content log (`~/.acpx/sessions/${session}.turn.log`, the two-log
contract below). A 30-minute dispatch costs about four of these. That is cheap; a null node
is not.

## Watcher tier

The watcher's `agent()` node is generated with the pinned pair `scripts/resolve-tier.sh
watcher` prints — `model=sonnet effort=low` — not with a per-role tier and not with the
session model. This is a node-kind constant: the watcher does the same job (launch, wait,
classify, route) whatever role it delegates, and the real reasoning happens inside the
acpx worker session, whose model comes from the binding's `modalities.*`. Sonnet is the
floor rather than haiku because two duties carry judgment — composing the continuation
prompt each turn and routing `blocked`/`needs-decision` — and nothing downstream reviews
the prompts, only the artifacts. Effort stays low because the watcher is the long-lived
node: its context accumulates O(turns), so its per-token cost compounds. The pin honors
the same `in_session_tiers` gate as every role row — when tiers are off the watcher line
prints `inherit` and the node takes neither opt.

## Steps

This skill realizes the `multi-turn-dispatch` L1 shape: one WARM-session actor is driven
across multiple turns while the watcher maintains its own accumulated context. Drive it
as follows:

1. **Source the env sidecar.** On each watcher entry, `read` the `${session}.env` sidecar
   written by `acpx-dispatch.sh`. It carries the 9-var (codex) or 10-var (claude/opencode)
   driver contract already resolved from the binding and turn protocol. Do not re-derive
   those values in the watcher body. The sidecar exists only after a dispatch has started —
   `acpx-dispatch.sh` writes it before it starts the driver, so a watcher that finds no
   sidecar has not dispatched yet.

2. **Background the worker turn, then block on it in the same turn.** `delegate` one worker
   turn via `run_in_background=true` so the turn's stdout lands in a file rather than in the
   watcher's context. The entry command is
   `bash "${CLAUDE_PLUGIN_ROOT}/skills/dispatching-acpx-agents/acpx-dispatch.sh"`; it takes
   no positionals in the dispatch path — every input is env-passed, per its own usage
   header: `ACPX_ROLE_SLUG`, `ACPX_BINDING_PRESET` (or `ACPX_BINDING_JSON`),
   `ACPX_INPUTS_JSON`, `ACPX_RUN_ID`, `WORKTREE` are required, `ACPX_EXPECTED_MAJOR` and
   `ACPX_DRY_RUN` are optional, and its stdout is one line of JSON, the dispatch result. See
   `relay:dispatching-acpx-agents` for the wrapper contract this entry command implements.
   The worker runs its session under the name given in the env sidecar
   (`ACPX_SESSION_NAME`). Immediately after the launch — same turn, no intervening final
   message — issue the mandated wait primitive from the turn-lifetime rule above:
   `timeout "${WATCH_BUDGET:-580}" bash -c 'until grep -qE … || ! pgrep -f "[a]cpx-dispatch.sh" …;
   do sleep 10; done'`. Re-issue that same call as many times as the worker needs; a
   30-minute dispatch costs about four of them. When the budget is spent and the worker has
   still produced no envelope, surface `ROLE_RESULT=ERRORED` with
   `ERRORED_REASON=watcher_budget_exhausted` rather than ending the turn on an outstanding
   dispatch.

3. **Read bounded output.** Once the wait returns, `read` the tail of the worker's turn
   content log (`~/.acpx/sessions/${session}.turn.log` — the dedicated turn-content
   channel written by the thinned driver). Bound to one `Read` tool-call pair per turn.
   Extract the envelope lines matching `^([A-Z][A-Z0-9_]*=.*|${terminal_token})$`.

4. **Classify into the five-bucket gate.** `classify` the captured envelope against this
   closed label set — reject any value outside it rather than guessing a route:

   > **Unparseable-envelope guard:** if `classify` produces no matching bucket because the
   > driver output contains neither the terminal token nor any `KEY=VALUE` envelope line (raw
   > prose only), the watcher MUST route to `errored` with `ROLE_RESULT=ERRORED` and
   > `ERRORED_REASON=unparseable_envelope`. This must never silently fall through to `not-done`
   > and re-dispatch. [inferred]

   | bucket | condition |
   |--------|-----------|
   | `done` | terminal-token line present AND (no verify_artifact OR artifact freshness verified) AND (role is not writer-class OR landing-verify passed — edits present OR valid no-change signal with pre-flight pin confirmed) |
   | `not-done` | terminal-token absent, reply non-empty (rc=0 in-progress — or rc≠0 with partial output) — eligible for re-dispatch |
   | `blocked` | first content line matches `^BLOCKED:` |
   | `needs-decision` | first content line matches `^NEEDS_DECISION:` (terminal; session left open-but-detached; PARKED=1) |
   | `errored` | non-zero rc AND empty reply, OR unrecoverable driver error, OR the envelope carries `ERRORED_REASON=config_replay_failed` |

   > **Session-config replay failure:** acpx >= 0.13.1 re-applies a reconnected session's
   > saved model and config options, and reports a failure instead of continuing on adapter
   > defaults. `acpx-envelope.sh` turns that report into `ERRORED_REASON=config_replay_failed`
   > and each session driver emits it as `ROLE_RESULT=ERRORED`. Route it to `errored`, never
   > to `not-done`: re-dispatching would run the worker on a model it did not ask for, and
   > the turn's output would be attributed to the pinned model.

   > **Writer-role landing-verify in the done-gate:** When the dispatched role has
   > `role-class: writer`, run the landing-verify from `docs/dispatch-contract.md`
   > (Writer-Role Landing Contract) after the terminal token is confirmed. Run it in
   > `WORKTREE` or `WORKTREE_PATH`, the path the entry-point command set. NOT `ACPX_CWD`:
   > that is an internal session-driver env var, not the fixer's target path. When the
   > landing-verify fails, reclassify the turn as `errored` with
   > `ERRORED_REASON=landing_verify_failed`; do not accept `done`. This stops a
   > wrong-worktree dispatch (Variant B) from green-lighting a round that changed nothing.

5. **Route via the router-loop.** `branch` on the bucket:
   - `done`: exit the loop, surface the result envelope.
   - `not-done`: `loop-until` re-enters step 2 within the turn cap (value from
     `RELAY_MAX_TURNS`, default 10; set `ROLE_RESULT=MAX_TURNS_REACHED` when the
     cap is reached).
   - `blocked`: `abort` with the blocked reason; surface `ROLE_RESULT=BLOCKED`.
   - `needs-decision`: call `acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" sessions detach --name "$ACPX_SESSION_NAME"`,
     set `PARKED=1`, surface `ROLE_RESULT=NEEDS_DECISION` and
     `QUESTION_TEXT=<text after the colon>`, exit normally — do NOT call `sessions close`.
   - `errored`: `abort` with the error detail; surface `ROLE_RESULT=ERRORED`.

6. **Crash-cleanup trap.** The watcher owns the `sessions close` cleanup. Register the
   PARKED-conditional trap (see Bash scaffolding below) on the watcher script — NOT on
   the individual session drivers (which are thinned to single-turn invocations). The trap
   must gate on `[[ "$PARKED" != "1" ]]` so that a deliberately parked needs-decision
   session is never closed on exit.

## Bash scaffolding

The watcher script must open with the following crash-cleanup trap immediately after sourcing
the env sidecar. This is the Phase D2 gate criterion: the trap must be present in the
delegate-and-watch SKILL.md bash scaffolding, not merely in hypothetical generated code.

```bash
#!/usr/bin/env bash
# delegate-and-watch watcher scaffold.
# Source the env sidecar written by acpx-dispatch.sh before any other logic.
# shellcheck disable=SC1090
source "${HOME}/.acpx/sessions/${SESSION_NAME}.env"

LOG_DIR="${HOME}/.acpx/sessions"
LOG_FILE="${LOG_DIR}/${ACPX_SESSION_NAME}.driver.log"

# Initialize PARKED before the main loop.
# Set to 1 in the needs-decision route to prevent the trap from closing a
# deliberately parked session (S1 spike outcome: close + re-ensure silently forks
# a blank session under the same name, losing all accumulated context).
PARKED=0

# Crash-cleanup trap: close the session on any exit path (normal, error, signal),
# UNLESS the session was intentionally parked for a needs-decision gate.
# The trap fires in the watcher only — thin session drivers are single-turn and
# do NOT register this trap.
trap 'if [[ "$PARKED" != "1" ]]; then
  acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" sessions close "$ACPX_SESSION_NAME" >>"$LOG_FILE" 2>&1 || true
fi' EXIT SIGTERM SIGINT
```

The sidecar write must append `RELAY_MAX_TURNS=${RELAY_MAX_TURNS:-10}` so the
sidecar carries the turn cap for the watcher. No session driver reads it.

The trap is the watcher's sole responsibility for session lifecycle management. The individual
session drivers (codex-session-driver.sh, claude-session-driver.sh, opencode-session-driver.sh)
are thinned to single-turn invocations and must not register this trap.

## Two-log contract

The watcher reads from and writes to two log files:

- `~/.acpx/sessions/${session}.driver.log` — forensic turn log: one entry per worker turn
  with timestamp, turn number, rc, and reply byte count. Written by the watcher after each
  turn boundary.
- `~/.acpx/sessions/${session}.turn.log` — turn-content channel: the thinned driver runs
  exactly one turn and captures the full turn stdout into this dedicated file. The watcher
  reads the tail of this file at each turn boundary (one bounded `Read` per turn).

The `${session}.turn.log` file is the documented turn-content channel (Phase D2 gate
criterion). The watcher samples it once per turn boundary. Rotation deferred (spec §7
open issue 3).

## Env sidecar contract

`acpx-dispatch.sh` writes `~/.acpx/sessions/${session}.env` before spawning the watcher.
The sidecar carries the fully-resolved per-mechanism driver vars plus the sidecar-only vars.
The canonical table is in `docs/dispatch-contract.md` (Driver env-var table). The watcher
sources the sidecar at entry (`source "${session}.env"`) so it never re-derives
`ACPX_ENGINE`, `ACPX_SESSION_NAME`, `ACPX_CWD`, the model, or the effort from the binding.

Watcher-relevant notes:

- `CODEX_CONFIG` (codex only) carries `model_reasoning_effort`. The watcher must re-export
  it on a re-invocation, or the next turn drops to the adapter default. claude/opencode
  carry `ACPX_EFFORT` and `ACPX_PERMISSIONS` instead; the session record re-applies both per
  turn, so the watcher passes neither on the turn command.
- `RELAY_MAX_TURNS` — turn cap for this loop (default 10); the sidecar appends
  `RELAY_MAX_TURNS=${RELAY_MAX_TURNS:-10}` so the watcher receives it. It is a
  sidecar value read here, not a driver env var — no driver reads it.

Calm imperatives only. Describe the target form; the session drivers do the turn work.

## The bg-sessions leg

When `$RELAY_ENGINE` is `bg-sessions`, the watcher runs the same five-bucket router
loop above with two substitutions and one new first step. See
`docs/bg-dispatch-contract.md` for the shared mechanism this leg defers to, and
`skills/dispatching-bg-agents/SKILL.md` for the sidecar and handoff file this leg
reads.

- **Step 1 substitution.** Source `~/.claude/relay/bg/${runid}/${role_slug}.env`
  instead of the acpx `~/.acpx/sessions/${session}.env`. Branch the poll target on
  which sidecar was found — the acpx sidecar carries `ACPX_SESSION_NAME`; the bg
  sidecar carries `RELAY_BG_HANDOFF`.
- **Poll target substitution.** Grep `$RELAY_BG_HANDOFF` instead of the acpx turn
  log.
- **Liveness escape substitution.** The escape is `bg-liveness.sh --short-id
  "$RELAY_BG_SHORT_ID"` reporting `stopped` (exit `1`), instead of the bracketed
  `pgrep`. The wait primitive, in the same shape as the acpx one:

  ```bash
  timeout "${WATCH_BUDGET:-580}" bash -c '
    until grep -qE "^(ROLE_RESULT=|ROLE_DONE$)" "'"$RELAY_BG_HANDOFF"'" 2>/dev/null \
       || bash "'"$CLAUDE_PLUGIN_ROOT"'/scripts/bg-liveness.sh" --short-id "'"$RELAY_BG_SHORT_ID"'" >/dev/null 2>&1; [ $? -eq 1 ]; do
      sleep 10
    done'
  ```

  The escape fires on rc `1` only. rc `3` (`stale` or `unknown`, per
  `docs/bg-dispatch-contract.md` §Liveness and truth) does NOT fire the escape — a
  caller must not treat `unknown` as gone.
- **TURN discipline.** The watcher discards an envelope whose `TURN=` does not match
  the turn it just sent, and keeps polling — the same rule
  `skills/dispatching-bg-agents/SKILL.md` states for the handoff file's writer side.
- **Stop on a terminal bucket.** `done` and `errored` end with the stop instruction
  and a `stopped` confirmation, via `bg-liveness.sh` (§Spawn authority,
  `docs/bg-dispatch-contract.md`). `needs-decision` leaves the child alive and
  records its name.

## Vocabulary

```relay-vocab
l1-shape: multi-turn-dispatch
l0-deps: delegate, session-grounding, loop-until, marker, branch, classify, typed-output
acpx-leg-required: true
```
