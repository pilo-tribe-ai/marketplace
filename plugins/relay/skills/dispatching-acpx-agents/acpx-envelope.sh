#!/usr/bin/env bash
# NDJSON -> final assistant text.
#
# Reads the raw ACP JSON-RPC stream that `acpx --format json --json-strict` writes
# (one object per line) on stdin, and writes the turn's final assistant text on
# stdout. Every relay caller then greps that text for the frozen envelope contract
# (^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$) exactly as it did with `--format quiet`.
#
# Why this exists: `--format quiet` prints the assistant text with no structure, so
# a chunk boundary landing mid-line could glue two envelope lines together and
# corrupt the parse. The JSON stream carries a `messageId` on every chunk, so the
# split points are recoverable: chunks are grouped and concatenated, which rebuilds
# the text byte for byte. Live 0.13.2 samples show claude splitting mid-token
# ("ST" then "ATUS=ok\nROLE_DONE") and codex emitting one chunk per word.
#
# Rules:
#   1. A line that is not JSON is skipped (defensive; --json-strict emits none).
#   2. Keep session/update events with sessionUpdate == "agent_message_chunk"
#      and content.type == "text".
#   3. Codex tags each chunk with _meta.codex.phase; only "final_answer" chunks are
#      the reply, the rest are commentary. Claude and opencode send _meta: null and
#      no phase, so a missing phase counts as final_answer and every chunk is kept.
#   4. Keep only the LAST messageId's chunks and concatenate them with no separator
#      (rebuilds a token split across chunks byte for byte). A turn that uses a tool
#      emits its narration as its own earlier message and its final reply as the
#      last one, so the last message is the reply and nothing else.
#
#      Do not join every message instead. The `BLOCKED:` and `NEEDS_DECISION:`
#      sentinels are read from the FIRST line of this output (see the three
#      *-session-driver.sh files), so prepending a narration message demotes every
#      sentinel a tool-using role raises. Verified live on acpx 0.13.2: a role told
#      to narrate, call a tool, then reply `BLOCKED: ...` emits the narration under
#      one messageId and the bare sentinel under the next.
#   5. If any line reports a session-config replay failure, emit
#      ERRORED_REASON=config_replay_failed as the first output line. acpx >= 0.13.1
#      re-applies a reconnected session's saved model and config options and reports
#      when that fails, instead of silently continuing on adapter defaults.
#      delegate-and-watch routes this reason to `errored`, never to `not-done`, so a
#      worker is never re-dispatched on a model it did not ask for.
#
# Exit status is 0 whenever the input was readable: an empty or unparseable stream
# yields empty stdout, and the caller's own unparseable_envelope guard reports it.

set -uo pipefail

buf=$(mktemp)
trap 'rm -f "$buf"' EXIT
cat > "$buf"

# Rule 5 — checked against the raw stream, because the error may arrive as an ACP
# error object, a session/update notice, or (on older adapters) a plain stderr line.
# Exclude assistant message chunks: a role whose own reply quotes the phrase (relay
# dogfoods on this very codebase) must not be misread as a replay failure.
if grep 'Failed to replay saved session' "$buf" 2>/dev/null \
   | grep -qv '"sessionUpdate":"agent_message_chunk"'; then
    printf 'ERRORED_REASON=config_replay_failed\n'
fi

# Rules 1-4. One jq process reads and parses every line via `inputs` (no separate
# slurp stage): `-n` starts with no input, `-R` reads raw lines, `inputs` pulls them.
jq -nR -r '
    [inputs | fromjson? // empty]
    | map(
      select(
        .method == "session/update"
        and .params.update.sessionUpdate == "agent_message_chunk"
        and .params.update.content.type == "text"
      )
      | select((.params.update._meta.codex.phase // "final_answer") == "final_answer")
      | {mid: .params.update.messageId, text: (.params.update.content.text // "")}
    )
    | if length == 0 then empty
      else (last.mid) as $m
         # The last message is the reply; earlier messages are narration. Its chunks
         # join with no separator, which rebuilds a split token byte for byte.
         | map(select(.mid == $m) | .text)
         | join("")
      end
  ' < "$buf"
