#!/usr/bin/env bash
# Thin opencode-session driver. Runs as a child subprocess of acpx-dispatch.sh.
# Single-turn invocation — no multi-turn loop, no nudge, no artifact-freshness gate.
# Those responsibilities live in the delegate-and-watch watcher (L2 skill).
# Inputs via env vars — 10-var contract (see SKILL.md). Stdout is the envelope.
# Near-identical to claude-session-driver.sh; engine is ACPX_ENGINE=opencode.
# opencode effort probe result (2026-05-27, acpx 0.10.0 / opencode 1.15.10): VERIFIED config-id=effort.
#   The adapter implements session/set_config_option and recognizes configId "effort" — the key is
#   correct, no remap needed. Accepted effort VALUES are model-dependent; the default model
#   opencode/big-pickle defines none, so `set effort <e>` returns ACP -32602
#   {"error":"Effort not found: <value>"}. Soft-degrade (warn on rc!=0, continue) covers this: the
#   session proceeds at the model's default reasoning effort. A reasoning-capable opencode model may
#   accept effort values; the driver passes ACPX_EFFORT through unchanged.
# Model probe result (2026-07-13, acpx 0.12.0 / opencode 1.17.18): requires acpx >= 0.12.0 —
#   0.10.0 persists the model from `set model` but re-applies it at prompt time via generic ACP
#   model selection, which the opencode adapter does not advertise → every prompt errors.
#   0.12.0 applies it correctly (verified end-to-end; served provider/model confirmed via
#   opencode's sqlite message store). Caveat: the model binds at the session's FIRST prompt —
#   a later `set model` on a live session reports success but does NOT switch the serving
#   model. One session = one role = one model; never reuse a session across models.
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
# New vars for claude/opencode: effort is set via session config (not CLI flag).
: "${ACPX_EFFORT:=}"
: "${ACPX_PERMISSIONS:=}"

LOG_DIR="${HOME}/.acpx/sessions"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/${ACPX_SESSION_NAME}.driver.log"

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" >> "$LOG_FILE"; }

extract_envelope() {
  # Capture regex (frozen public envelope contract): ^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$
  # Frozen first-line sentinels: BLOCKED: and NEEDS_DECISION:
  local reply="$1"
  printf '%s\n' "$reply" \
    | grep -E "^([A-Z][A-Z0-9_]*=.*|${ACPX_TERMINAL_TOKEN})$" || true
}

# Preamble guard: first line must contain <<DO_NOT_LOAD_SKILLS>>.
if [ -f "$ACPX_PROMPT_FILE" ]; then
  head -1 "$ACPX_PROMPT_FILE" | grep -q '<<DO_NOT_LOAD_SKILLS>>' || {
    echo "ROLE_RESULT=BLOCKED"
    echo "TURNS_USED=0"
    echo "BLOCKED_REASON=prompt missing DO_NOT_LOAD_SKILLS preamble"
    echo "$ACPX_TERMINAL_TOKEN"
    exit 1
  }
fi

# Ensure session — idempotent, re-run-safe.
acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" sessions ensure --name "$ACPX_SESSION_NAME" \
  >>"$LOG_FILE" 2>&1 || {
  echo "ROLE_RESULT=BLOCKED"
  echo "TURNS_USED=0"
  echo "BLOCKED_REASON=acpx sessions ensure failed"
  echo "$ACPX_TERMINAL_TOKEN"
  exit 0
}
# Session cleanup (close) is the delegate-and-watch watcher's responsibility, not the driver's.

# Settle config once after ensure, before the single turn.
# Order: set model first (adapter rebuilds effort options when model changes).
# Soft-degrade on rc≠0: log warn and continue at adapter default.
if [ -n "$ACPX_MODEL" ]; then
  set_model_out=$(acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" \
    set model "$ACPX_MODEL" -s "$ACPX_SESSION_NAME" 2>&1) || {
    log "[warn] model not applied (rc=$?): ${set_model_out:-<no output>}"
  }
fi
if [ -n "$ACPX_EFFORT" ]; then
  set_effort_out=$(acpx --cwd "$ACPX_CWD" "$ACPX_ENGINE" \
    set effort "$ACPX_EFFORT" -s "$ACPX_SESSION_NAME" 2>&1) || {
    log "[warn] effort not applied (rc=$?): ${set_effort_out:-<no output>}"
  }
fi

# The widest grant acpx exposes, on every turn. `--approve-all` answers each ACP
# permission request; the policy file sets the same default for acpx's per-tool rule
# engine. Before 4.51.0 this was gated on ACPX_PERMISSIONS == approve-all, so a role
# bound to `approve-reads` fell through to acpx's non-TTY default of `deny` and had
# every write refused with nothing reporting it. ACPX_PERMISSIONS now records the
# role's intent only. ACPX_POLICY_FILE arrives from the dispatcher's sidecar; the
# fallback keeps a hand-run driver working.
: "${ACPX_POLICY_FILE:=${SCRIPT_DIR}/../../bindings/acpx-policy.json}"

prompt_arg="@${ACPX_PROMPT_FILE}"
TURN_LOG_FILE="${LOG_DIR}/${ACPX_SESSION_NAME}.turn.log"
rc=0
# Turn command: model+effort are set on the session record; do NOT pass
# --model or --effort here (unlike the codex driver which bakes effort into model id).
# --format json --json-strict emits the raw ACP JSON-RPC stream; acpx-envelope.sh
# rebuilds the final assistant text from its message chunks. Chunks split mid-token
# (live 0.13.2: "ST" then "ATUS=ok\nROLE_DONE"), which the old `--format quiet`
# capture could glue into a corrupted envelope line. The raw stream is kept beside
# the turn log for forensics; TURN_LOG_FILE still holds plain text, so the watcher's
# reader is unchanged.
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


# Replay-failure passthrough. acpx >= 0.13.1 re-applies a reconnected session's
# saved model and config options and reports when that fails; acpx-envelope.sh
# turns that report into this reason line. Without this branch the turn would fall
# through to NOT_DONE and the watcher would re-dispatch the worker on a model it
# did not ask for, so it is classified before every other outcome.
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
