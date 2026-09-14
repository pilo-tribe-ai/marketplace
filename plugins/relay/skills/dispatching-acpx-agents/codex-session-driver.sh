#!/usr/bin/env bash
# Thin codex-session driver. Runs as a child subprocess of acpx-dispatch.sh.
# Single-turn invocation — no multi-turn loop, no nudge, no artifact-freshness gate.
# Those responsibilities live in the delegate-and-watch watcher (L2 skill).
# Inputs via env vars (see the env-var contract in SKILL.md). Stdout is the envelope.
set -uo pipefail

# Resolved once. Trimming a suffix off BASH_SOURCE instead returns the whole word
# when the driver is invoked by bare name, which points sibling helpers at a
# path that is not a directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${ACPX_ENGINE:?required}"
: "${ACPX_MODEL:?required}"
: "${ACPX_CWD:?required}"
: "${ACPX_TIMEOUT:?required}"
: "${ACPX_SESSION_NAME:?required}"
: "${ACPX_PROMPT_FILE:?required}"
: "${ACPX_TERMINAL_TOKEN:=ROLE_DONE}"
: "${ACPX_VERIFY_ARTIFACT:=}"
: "${ACPX_EFFORT:=}"
# ACPX_POLICY_FILE arrives from the dispatcher's sidecar; the fallback keeps a
# hand-run driver working.
: "${ACPX_POLICY_FILE:=${SCRIPT_DIR}/../../bindings/acpx-policy.json}"
# ACPX_MODEL is a plain adapter-advertised model id (e.g. gpt-5.6-terra) and
# ACPX_EFFORT is the reasoning effort. Both are applied to the session record by the
# settle block below, the same way the claude and opencode drivers do it.
#
# History, in two steps:
#   4.20.0 — effort used to be baked into ACPX_MODEL as `${model}[${effort}]`. acpx
#            >= 0.12.0 validates --model against plain ids and rejects that form.
#            Effort moved to the CODEX_CONFIG adapter env instead.
#   4.51.0 — codex-acp 1.x advertises `model`, `reasoning_effort` and `mode` as
#            separate session config options, so this driver sets them directly.
#            It could not before: the `--agent` override relay carried for acpx's
#            broken codex pin cannot be combined with a positional engine, and the
#            session subcommands need that positional to scope the session. Removing
#            the override (acpx >= 0.12.1 pins a working adapter) unblocked this.
#            CODEX_CONFIG is still exported by the dispatcher for one release, but
#            this driver no longer reads it.

# Forensic log accumulates across runs; rotation deferred per spec §7 open issue 3. [inferred]
LOG_DIR="${HOME}/.acpx/sessions"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/${ACPX_SESSION_NAME}.driver.log"

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" >> "$LOG_FILE"; }

extract_envelope() {
  # $1 = reply text; echoes any line matching ^[A-Z][A-Z0-9_]*=.*$
  # plus the literal terminal-token line.
  # Capture regex (frozen public envelope contract): ^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$
  # Frozen first-line sentinels: BLOCKED: and NEEDS_DECISION:
  local reply="$1"
  printf '%s\n' "$reply" \
    | grep -E "^([A-Z][A-Z0-9_]*=.*|${ACPX_TERMINAL_TOKEN})$" || true
}

# Contract guard: the dispatcher prepends a DO_NOT_LOAD_SKILLS preamble to the
# prompt before invoking the driver. Direct callers (tests, future wrappers)
# MUST do the same — surface a BLOCKED envelope so the contract cannot be
# silently bypassed. [inferred — Task 9]
if [ -f "$ACPX_PROMPT_FILE" ]; then
  head -1 "$ACPX_PROMPT_FILE" | grep -q '<<DO_NOT_LOAD_SKILLS>>' || {
    echo "ROLE_RESULT=BLOCKED"
    echo "TURNS_USED=0"
    echo "BLOCKED_REASON=prompt missing DO_NOT_LOAD_SKILLS preamble"
    echo "$ACPX_TERMINAL_TOKEN"
    exit 1
  }
fi

# acpx scopes sessions by the tuple (engine, absolute cwd, name). Every
# session subcommand AND every turn must pass the same --cwd or they resolve
# to different scopes. `ensure` is the documented idempotent, re-run-safe verb.
acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" sessions ensure --name "$ACPX_SESSION_NAME" >>"$LOG_FILE" 2>&1 || {
  echo "ROLE_RESULT=BLOCKED"
  echo "TURNS_USED=0"
  echo "BLOCKED_REASON=acpx sessions ensure failed"
  echo "$ACPX_TERMINAL_TOKEN"
  exit 0
}
# Session cleanup (close) is the delegate-and-watch watcher's responsibility, not the driver's.

# Settle config once after ensure, before the single turn — mirrors the claude and
# opencode drivers. Order matters: set model first, because the adapter rebuilds its
# effort options when the model changes. Each call soft-degrades on rc≠0 (log a warn
# and continue at the adapter default) so a config option one adapter build does not
# advertise cannot fail the whole turn.
if [ -n "$ACPX_MODEL" ]; then
  set_model_out=$(acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" \
    set model "$ACPX_MODEL" -s "$ACPX_SESSION_NAME" 2>&1) || {
    log "[warn] model not applied (rc=$?): ${set_model_out:-<no output>}"
  }
fi
if [ -n "$ACPX_EFFORT" ]; then
  set_effort_out=$(acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" \
    set reasoning_effort "$ACPX_EFFORT" -s "$ACPX_SESSION_NAME" 2>&1) || {
    log "[warn] reasoning_effort not applied (rc=$?): ${set_effort_out:-<no output>}"
  }
fi
# Codex keeps a sandbox of its own, behind acpx's permission layer. `agent-full-access`
# is the widest mode the codex-acp adapter advertises, matching the --approve-all +
# policy grant on the acpx side. The one-shot `exec` path has no `set` subcommand and
# widens the same gate through CODEX_CONFIG instead (see build_codex_config).
set_mode_out=$(acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" \
  set mode agent-full-access -s "$ACPX_SESSION_NAME" 2>&1) || {
  log "[warn] mode not applied (rc=$?): ${set_mode_out:-<no output>}"
}

prompt_arg="@${ACPX_PROMPT_FILE}"
TURN_LOG_FILE="${LOG_DIR}/${ACPX_SESSION_NAME}.turn.log"
rc=0
# --format json --json-strict emits the raw ACP JSON-RPC stream; acpx-envelope.sh
# rebuilds the final assistant text from its message chunks. Codex tags each chunk
# with _meta.codex.phase, so the script keeps only the final_answer chunks and drops
# the commentary the old `--format quiet` capture mixed in. stderr is merged into the
# same file so a non-JSON failure line is still captured; the script skips it.
# --model is NOT passed: the settle block above put it on the session record, the
# same contract the claude and opencode drivers use.
TURN_NDJSON_FILE="${LOG_DIR}/${ACPX_SESSION_NAME}.turn.ndjson"
acpx --format json --json-strict --approve-all --permission-policy "$ACPX_POLICY_FILE" \
  --cwd "$ACPX_CWD" \
  --timeout "$ACPX_TIMEOUT" \
  "$ACPX_ENGINE" -s "$ACPX_SESSION_NAME" "$prompt_arg" > "$TURN_NDJSON_FILE" 2>&1 || rc=$?
final_reply=$("${SCRIPT_DIR}/acpx-envelope.sh" < "$TURN_NDJSON_FILE")
# Write full turn stdout to the dedicated turn-content channel (Phase D2 two-log contract).
# The watcher reads this file at each turn boundary; the driver.log carries metadata only.
printf '%s\n' "$final_reply" > "$TURN_LOG_FILE"
log "turn=1 rc=$rc reply_bytes=${#final_reply}"

# Classify result for the watcher.

# Replay-failure passthrough. acpx >= 0.13.1 re-applies a reconnected session's saved
# model and config options and reports when that fails; acpx-envelope.sh turns that
# report into this reason line. Without this branch the turn would fall through to
# NOT_DONE and the watcher would re-dispatch the worker on a model it did not ask
# for, so it is classified before every other outcome.
if printf '%s\n' "$final_reply" | grep -q '^ERRORED_REASON=config_replay_failed$'; then
  log "turn=1 config replay failed; reporting errored"
  echo "ROLE_RESULT=ERRORED"
  echo "TURNS_USED=1"
  echo "ERRORED_REASON=config_replay_failed"
  echo "$ACPX_TERMINAL_TOKEN"
  exit 0
fi

first_line=$(printf '%s\n' "$final_reply" | awk 'NF{print; exit}')
if [ -n "$final_reply" ] && printf '%s' "$first_line" | grep -q '^BLOCKED:'; then
  blocked_reason=$(printf '%s' "$first_line" | sed -E 's/^BLOCKED:[[:space:]]*//')
  echo "ROLE_RESULT=BLOCKED"
  echo "TURNS_USED=1"
  echo "BLOCKED_REASON=${blocked_reason}"
  echo "$ACPX_TERMINAL_TOKEN"
  exit 0
fi

if [ -n "$final_reply" ] && printf '%s' "$first_line" | grep -q '^NEEDS_DECISION:'; then
  question_text=$(printf '%s' "$first_line" | sed -E 's/^NEEDS_DECISION:[[:space:]]*//')
  echo "ROLE_RESULT=NEEDS_DECISION"
  echo "TURNS_USED=1"
  echo "QUESTION_TEXT=${question_text}"
  echo "$ACPX_TERMINAL_TOKEN"
  exit 0
fi

if [ "$rc" -ne 0 ] && [ -z "$final_reply" ]; then
  echo "ROLE_RESULT=ERRORED"
  echo "TURNS_USED=1"
  echo "$ACPX_TERMINAL_TOKEN"
  exit "$rc"
fi

has_token=0
printf '%s\n' "$final_reply" | grep -q "^${ACPX_TERMINAL_TOKEN}\$" && has_token=1

if [ "$has_token" -eq 1 ]; then
  echo "ROLE_RESULT=DONE"
  echo "TURNS_USED=1"
  extract_envelope "$final_reply" | grep -v "^${ACPX_TERMINAL_TOKEN}\$" || true
  echo "$ACPX_TERMINAL_TOKEN"
  exit 0
fi

# Token absent but no error — not-done; watcher decides whether to re-dispatch.
echo "ROLE_RESULT=NOT_DONE"
echo "TURNS_USED=1"
echo "$ACPX_TERMINAL_TOKEN"
exit 0
