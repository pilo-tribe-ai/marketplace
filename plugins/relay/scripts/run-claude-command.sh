#!/usr/bin/env bash
# Run one raw acpx Claude slash-command turn for /relay:implement polish leaves.
set -uo pipefail

usage() {
  echo "usage: run-claude-command.sh <worktree> <session> <command> [timeout_seconds]" >&2
}

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  usage
  echo "POLISH_CMD_RC=64"
  exit 64
fi

worktree="$1"
session="$2"
command_text="$3"
timeout_seconds="${4:-${RELAY_POLISH_TIMEOUT:-1800}}"

case "$command_text" in
  /*) ;;
  *)
    echo "run-claude-command.sh: command must be a bare slash command" >&2
    echo "POLISH_CMD_RC=64"
    exit 64
    ;;
esac

if [ ! -d "$worktree" ]; then
  echo "run-claude-command.sh: worktree not found: $worktree" >&2
  echo "POLISH_CMD_RC=66"
  exit 66
fi

# 69 (EX_UNAVAILABLE), not 127: acpx itself exits 127 when it cannot spawn the adapter, so
# passing 127 through would make "acpx missing" byte-identical to a genuine spawn failure.
if ! command -v acpx >/dev/null 2>&1; then
  echo "run-claude-command.sh: acpx not found on PATH" >&2
  echo "POLISH_CMD_RC=69"
  exit 69
fi

ensure_out="$(acpx --cwd "$worktree" claude sessions ensure --name "$session" 2>&1)"
ensure_rc=$?
if [ "$ensure_rc" -ne 0 ]; then
  [ -n "$ensure_out" ] && printf '%s\n' "$ensure_out"
  printf 'POLISH_CMD_RC=%s\n' "$ensure_rc"
  exit "$ensure_rc"
fi

turn_out="$(acpx --format quiet --approve-all --cwd "$worktree" --timeout "$timeout_seconds" claude -s "$session" "$command_text" 2>&1)"
turn_rc=$?

# This helper owns the whole session lifecycle: it opened the session with `ensure`, so it
# closes it here. Without this every polish run leaks two permanently open sessions, and a
# same-cwd re-run would resume the prior conversation instead of starting clean. History
# stays on disk (closed: true) for forensics. Never allowed to change the reported rc.
acpx --cwd "$worktree" claude sessions close "$session" >/dev/null 2>&1 || true

# The child's reply is fenced so the rc sentinel cannot be forged from inside it. The child
# runs /simplify or /code-review over a repo that may itself contain the literal string
# `POLISH_CMD_RC=` (this file does), and an unfenced reply would let the child's own text
# be read as this helper's exit status. Only the line after POLISH_CMD_OUTPUT_END counts.
if [ -n "$turn_out" ]; then
  printf 'POLISH_CMD_OUTPUT_BEGIN\n'
  printf '%s\n' "$turn_out"
  printf 'POLISH_CMD_OUTPUT_END\n'
fi
printf 'POLISH_CMD_RC=%s\n' "$turn_rc"
exit "$turn_rc"
