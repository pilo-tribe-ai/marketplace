#!/usr/bin/env bash
# Run one raw acpx Claude free-form-prompt turn for /relay:verify's fix step.
#
# Free-form sibling of run-claude-command.sh: same session lifecycle, same
# POLISH_CMD_OUTPUT_BEGIN/END fencing, same rc semantics (64/66/69). The
# difference is the payload: this helper accepts arbitrary prompt text instead
# of requiring a leading `/`, because the fix step sends a report body built
# from a /verify reply, not a slash command.
set -uo pipefail

usage() {
  echo "usage: run-claude-prompt.sh <worktree> <session> <prompt> [timeout_seconds]" >&2
}

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  usage
  echo "POLISH_CMD_RC=64"
  exit 64
fi

worktree="$1"
session="$2"
prompt="$3"
timeout_seconds="${4:-${RELAY_VERIFY_TIMEOUT:-${RELAY_POLISH_TIMEOUT:-1800}}}"

# An empty (or whitespace-only) prompt starts a child turn with nothing to do.
# That turn returns rc 0, which reads as a success report with no work behind
# it. Reject it here instead of letting a silent no-op look like a pass.
# No slash-prefix guard: a free-form prompt may legitimately start with `/`
# (a file path), so that check does not belong in this helper.
# A bash builtin regex test is used instead of `tr`/`sed`, so this guard has
# no external-command dependency to fail before the acpx-on-PATH check runs.
if [[ ! "$prompt" =~ [^[:space:]] ]]; then
  echo "run-claude-prompt.sh: prompt must not be empty" >&2
  echo "POLISH_CMD_RC=64"
  exit 64
fi

if [ ! -d "$worktree" ]; then
  echo "run-claude-prompt.sh: worktree not found: $worktree" >&2
  echo "POLISH_CMD_RC=66"
  exit 66
fi

# 69 (EX_UNAVAILABLE), not 127: acpx itself exits 127 when it cannot spawn the adapter, so
# passing 127 through would make "acpx missing" byte-identical to a genuine spawn failure.
if ! command -v acpx >/dev/null 2>&1; then
  echo "run-claude-prompt.sh: acpx not found on PATH" >&2
  echo "POLISH_CMD_RC=69"
  exit 69
fi

# A session must exist first, or acpx fails with NO_SESSION.
ensure_out="$(acpx --cwd "$worktree" claude sessions ensure --name "$session" 2>&1)"
ensure_rc=$?
if [ "$ensure_rc" -ne 0 ]; then
  [ -n "$ensure_out" ] && printf '%s\n' "$ensure_out"
  printf 'POLISH_CMD_RC=%s\n' "$ensure_rc"
  exit "$ensure_rc"
fi

# "$prompt" is one quoted argv element and never passes through eval. A
# /verify report can hold backticks, quotes, and shell metacharacters;
# word-splitting it would send a truncated prompt while still returning rc 0.
turn_out="$(acpx --format quiet --approve-all --cwd "$worktree" --timeout "$timeout_seconds" claude -s "$session" "$prompt" 2>&1)"
turn_rc=$?

# This helper owns the whole session lifecycle: it opened the session with `ensure`, so it
# closes it here. Without this every verify run leaks a permanently open session, and a
# same-cwd re-run would resume the prior conversation instead of starting clean. History
# stays on disk (closed: true) for forensics. Never allowed to change the reported rc.
acpx --cwd "$worktree" claude sessions close "$session" >/dev/null 2>&1 || true

# The child's reply is fenced so the rc sentinel cannot be forged from inside it. The child
# runs a free-form fix prompt built from a /verify report, which can itself contain the
# literal string `POLISH_CMD_RC=`, and an unfenced reply would let the child's own text be
# read as this helper's exit status. Only the line after POLISH_CMD_OUTPUT_END counts.
if [ -n "$turn_out" ]; then
  printf 'POLISH_CMD_OUTPUT_BEGIN\n'
  printf '%s\n' "$turn_out"
  printf 'POLISH_CMD_OUTPUT_END\n'
fi
printf 'POLISH_CMD_RC=%s\n' "$turn_rc"
exit "$turn_rc"
