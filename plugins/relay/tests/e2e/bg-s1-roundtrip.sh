#!/usr/bin/env bash
# relay: the live S1 round-trip check for the bg dispatch contract (spec §Tests,
# docs/bg-dispatch-contract.md "Live validation"). EXECUTED, never sourced:
#   RELAY_RUN_LIVE_BG=1 bash tests/e2e/bg-s1-roundtrip.sh
#
# This launches a REAL background Claude Code child. It cannot run in CI. Without
# RELAY_RUN_LIVE_BG=1 it prints BG_S1_ROUNDTRIP=SKIPPED and exits 0. Run it by hand
# before each engine's work (bg-sessions, session-tree) is called done, and record the
# printed line — and the date — in the commit body of the PR that depends on it.
#
# 4.30.0: first version. Drives the S1 round trip end to end:
#   1. Build a session name (spec §1.2) with a fresh runid.
#   2. Write a prompt file: the identity preamble plus an instruction that makes the
#      child ask one question with NEEDS_DECISION: and then wait.
#   3. Launch through scripts/bg-launch.sh. Assert RELAY_BG_LAUNCH=OK.
#   4. Wait for the child's turn to end (state -> blocked/done via
#      scripts/bg-liveness.sh) — the posture a child holds after it reports
#      NEEDS_DECISION: and stops to wait (S1).
#   5. Reply with a DECISION: line and re-invoke the child.
#   6. Assert the child finishes with ROLE_DONE and the value the answer chose.
#   7. Send the finish-and-stop instruction. Confirm `stopped` through bg-liveness.sh.
#   8. Print BG_S1_ROUNDTRIP=PASS or BG_S1_ROUNDTRIP=FAIL <step>.
#
# [inferred] Send mechanism. The design's SendMessage / ListAgents mechanism is a
# Claude-tool capability, not a shell command, so it is not invokable from bash. This
# script uses `claude --resume <short-id> "<message>"` (run in the FOREGROUND, no
# --bg) as its bash-invokable equivalent: it re-invokes the named session with a new
# turn and blocks until that turn's output is available, which both sends the
# message and gives this script the reply to check in one call. If a dedicated
# send-only CLI subcommand exists in your installed Claude Code version, prefer it and
# update this script; the typed outcomes below do not depend on which mechanism sends
# the message, only on what the child's envelope says.
set -u

_e2e_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_e2e_scripts="$(cd "$_e2e_here/../../scripts" && pwd)"

if [ "${RELAY_RUN_LIVE_BG:-0}" != "1" ]; then
  printf 'BG_S1_ROUNDTRIP=SKIPPED\n'
  printf '[relay] note: live bg round trip skipped. Set RELAY_RUN_LIVE_BG=1 to run it for real.\n' >&2
  exit 0
fi

_e2e_fail() {
  printf 'BG_S1_ROUNDTRIP=FAIL %s\n' "$1"
  printf '[relay] error: %s\n' "$2" >&2
  exit 1
}

# --- Step 1: name -----------------------------------------------------------------
_e2e_runid="$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-6)"
_e2e_name="bg-s1-roundtrip-scout-${_e2e_runid}"
if ! bash "$_e2e_scripts/bg-launch.sh" --check-name "$_e2e_name" >/dev/null 2>&1; then
  _e2e_fail step1 "generated name '$_e2e_name' failed naming validation"
fi

# --- Step 2: prompt file -----------------------------------------------------------
_e2e_prompt_file="$(mktemp)"
trap 'rm -f "$_e2e_prompt_file"' EXIT
cat > "$_e2e_prompt_file" <<PROMPT
Your name is ${_e2e_name}. Your parent is the session running this live check.
Never use AskUserQuestion. Send NEEDS_DECISION: <question> to your parent and end your
turn.
Never command a sibling. Never stop another session.
Never address the user. The orchestrator owns the user channel.
Report with the envelope grammar only.

Task: ask exactly one question using the line "NEEDS_DECISION: ALPHA or BRAVO?" as the
first line of your reply, then stop and wait for an answer. When you receive a reply
starting with "DECISION: ", finish with a final message whose first line is
"ROLE_DONE" followed by a line "CODENAME=<the chosen value>".
PROMPT

# --- Step 3: launch -----------------------------------------------------------------
_e2e_launch_out="$(bash "$_e2e_scripts/bg-launch.sh" \
  --name "$_e2e_name" --model haiku --permission-mode plan \
  --prompt-file "$_e2e_prompt_file" 2>&1)"
_e2e_launch_rc=$?
if [ "$_e2e_launch_rc" -ne 0 ] || ! printf '%s' "$_e2e_launch_out" | grep -q '^RELAY_BG_LAUNCH=OK$'; then
  _e2e_fail step3 "launch did not report OK: $_e2e_launch_out"
fi
_e2e_short_id="$(printf '%s\n' "$_e2e_launch_out" | sed -n 's/^RELAY_BG_SHORT_ID=//p')"
[ -n "$_e2e_short_id" ] || _e2e_fail step3 "no short id in launch output"

# --- Step 4: wait for the child's turn to end (NEEDS_DECISION posture) -------------
_e2e_turn_ended=0
_e2e_i=0
while [ "$_e2e_i" -lt 60 ]; do
  _e2e_live_out="$(bash "$_e2e_scripts/bg-liveness.sh" --short-id "$_e2e_short_id")"
  if printf '%s' "$_e2e_live_out" | grep -qE '^RELAY_BG_STATE=(blocked|done)$'; then
    _e2e_turn_ended=1
    break
  fi
  sleep 2
  _e2e_i=$((_e2e_i + 1))
done
[ "$_e2e_turn_ended" -eq 1 ] || _e2e_fail step4 "child never reached a turn-end posture (blocked/done)"

# --- Step 5: reply --------------------------------------------------------------
_e2e_reply_out="$(claude --resume "$_e2e_short_id" "DECISION: BRAVO" 2>&1)"

# --- Step 6: assert completion -----------------------------------------------------
printf '%s' "$_e2e_reply_out" | grep -q '^ROLE_DONE$' \
  || _e2e_fail step6 "no ROLE_DONE in the reply turn's output"
printf '%s' "$_e2e_reply_out" | grep -q '^CODENAME=BRAVO$' \
  || _e2e_fail step6 "ROLE_DONE did not carry CODENAME=BRAVO"

# --- Step 7: stop and confirm -------------------------------------------------------
claude --resume "$_e2e_short_id" "Finish and stop now." >/dev/null 2>&1 || true
_e2e_stopped=0
_e2e_i=0
while [ "$_e2e_i" -lt 30 ]; do
  _e2e_stop_out="$(bash "$_e2e_scripts/bg-liveness.sh" --short-id "$_e2e_short_id" 2>/dev/null)"
  if printf '%s' "$_e2e_stop_out" | grep -q '^RELAY_BG_VERDICT=stopped$'; then
    _e2e_stopped=1
    break
  fi
  sleep 2
  _e2e_i=$((_e2e_i + 1))
done
[ "$_e2e_stopped" -eq 1 ] || _e2e_fail step7 "child never reported stopped via bg-liveness.sh"

# --- Step 8: report -------------------------------------------------------------------
printf 'BG_S1_ROUNDTRIP=PASS\n'
exit 0
