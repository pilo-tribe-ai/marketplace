#!/usr/bin/env bash
# relay: run-intent record (spec §3.7). EXECUTED, never sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/record-run-intent.sh" \
#     --run-id wf_xxx --command implement --task-kind feature \
#     --spine "refine-spec,refine-plan,implement,verify" \
#     --gates "polish=true,delegation=false" --axis-source default
#
# Appends ONE line to ~/.claude/relay/runs.jsonl so a later `--retro` can diff what the
# run was SUPPOSED to do against what it did. Called from Step 3.5, AFTER the Workflow
# tool returns — `run_id` exists only then.
#
# ADVISORY: bookkeeping must never take down a run that already succeeded. Every
# failure prints a reason and exits non-zero, and every caller is instructed to report
# it and continue. Nothing downstream reads a missing record as an error; the retro
# simply degrades C1 to "spine unknown" (spec §3.5 rung 1).
#
# WHAT IS DELIBERATELY *NOT* RECORDED. Only fields that are provably unrecoverable
# from the run artifacts belong here; anything durable elsewhere would create a second
# source of truth that can disagree with the script:
#   - runId          -> also in the Workflow tool result and wf_<runId>.json.runId, but
#                       recorded here as the JOIN KEY. It is the one duplicate, and it
#                       is what makes the line addressable at all.
#   - axis VALUES    -> persisted as `const ENGINE` / `const AGENT` in the script text.
#                       Only axis_source (flag | pin | prompt | default) is recorded —
#                       provenance appears in no artifact.
#   - task text      -> persisted as `const TASK` in the script text.
#   - phase list     -> wf_<runId>.json.phases[] is a static pre-scan of phase()
#                       literals, so it is already declared intent that survives the
#                       run's death.
# Genuinely absent everywhere, and therefore recorded: `relay_command` (workflowName is
# free text and does not identify the command), `kind` (the classifier's output is never
# persisted), `intended_spine`, and `gates`.
#
# `gates` KEYS ON NODE LABELS — the same strings recorded in `intended_spine`. The retro
# suppresses a role by looking that role up in `gates`, so a key naming anything else
# (a feature, an engine, a flag) matches no role and suppresses nothing.
#
# Record a gate ONLY for a role the run deliberately did not dispatch. A setting that
# changes HOW a node runs rather than WHETHER it runs is not a gate: with delegation off,
# every spine role still dispatches — `relay:delegate-leaf` stands in for
# `relay:delegate-and-watch` — so `delegation=false` suppresses nothing and belongs
# nowhere near this field. C4 AXIS already reports on delegation wiring from the script's
# own `ENGINE`/`AGENT` consts.
#
# No command has a genuinely skippable spine role today, so every command records `""`.
# The mechanism is kept wired because the alternative — reconstructing it under a future
# soft-zone gate — is strictly more work than leaving one empty argument in place.
#
# `intended_spine` snapshots the §4.2.1 branch-table row AT RUN TIME, so retroing an old
# run does not diff it against a table that has since changed. Commands with no hard
# spine (`execute`, `drive`) record `[]`, and the retro reports coverage descriptively
# rather than as a deviation.
#
# WHY ~/.claude AND NOT THE REPO'S .claude/. Leaf agents commit with `git add -A`-style
# flows and would sweep run records into the branch under review — a retro must not
# dirty the branch it audits. The home path is also cwd-independent, so it survives the
# EnterWorktree slug migration that moves everything else.
set -uo pipefail

_ri_usage='usage: record-run-intent.sh --run-id <id> --command <name> [--task-kind <kind>]
                            [--spine "a,b,c"] [--gates "name=true,other=false"]
                            [--axis-source <flag|pin|prompt|default|...>]'

_ri_fail() {
  printf 'RELAY_INTENT=NOT_RECORDED\n'
  printf 'RELAY_INTENT_REASON=%s\n' "$1"
  printf '[relay] run intent not recorded: %s\n' "$2"
  printf '[relay] This is advisory bookkeeping — report it and continue. A later\n'
  printf '[relay] --retro degrades to "spine unknown"; every other comparison still runs.\n'
  exit 1
}

_ri_run_id=""
_ri_command=""
_ri_kind=""
_ri_spine=""
_ri_gates=""
_ri_axis_source=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)     printf '%s\n' "$_ri_usage"; exit 0 ;;
    --run-id)      _ri_run_id="${2:-}"; shift 2 || _ri_fail usage "--run-id needs a value" ;;
    --command)     _ri_command="${2:-}"; shift 2 || _ri_fail usage "--command needs a value" ;;
    --task-kind)   _ri_kind="${2:-}"; shift 2 || _ri_fail usage "--task-kind needs a value" ;;
    --spine)       _ri_spine="${2:-}"; shift 2 || _ri_fail usage "--spine needs a value" ;;
    --gates)       _ri_gates="${2:-}"; shift 2 || _ri_fail usage "--gates needs a value" ;;
    --axis-source) _ri_axis_source="${2:-}"; shift 2 || _ri_fail usage "--axis-source needs a value" ;;
    *)             _ri_fail usage "unexpected argument '$1'. $_ri_usage" ;;
  esac
done

[ -n "$_ri_run_id" ]  || _ri_fail usage "--run-id is required (take it from the Workflow tool result). $_ri_usage"
[ -n "$_ri_command" ] || _ri_fail usage "--command is required. $_ri_usage"

# Reject a path separator so a caller-supplied id cannot steer the join key.
case "$_ri_run_id" in
  *[!A-Za-z0-9._-]*) _ri_fail bad_run_id "run id '$_ri_run_id' is not a bare run identifier" ;;
esac

command -v python3 >/dev/null 2>&1 || _ri_fail python3_missing "python3 is required to emit correctly escaped JSON"
[ -n "${HOME:-}" ] || _ri_fail no_home "\$HOME is unset, so ~/.claude/relay cannot be resolved"

# Session dir — same rule as every other relay reader: NEVER derive the project slug
# from $PWD. The slug is fixed at session launch and EnterWorktree does not update it.
# An unresolvable session dir is recorded as "" rather than guessed.
_ri_session_dir=""
if [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] && [ -d "$HOME/.claude/projects" ]; then
  _ri_session_dir="$(find "$HOME/.claude/projects" -mindepth 2 -maxdepth 2 -type d \
                       -name "$CLAUDE_CODE_SESSION_ID" 2>/dev/null | head -n 1)"
fi

# Plugin version — the record must say which relay wrote it, because the intended-spine
# vocabulary is versioned. Resolve next to this script, not from CLAUDE_PLUGIN_ROOT,
# so the value is right even when the script is run directly.
_ri_manifest="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.claude-plugin/plugin.json"

_ri_dir="$HOME/.claude/relay"
if ! mkdir -p "$_ri_dir" 2>/dev/null; then
  _ri_fail mkdir_failed "could not create $_ri_dir"
fi
_ri_file="$_ri_dir/runs.jsonl"

_ri_line="$(
  python3 - "$_ri_run_id" "$_ri_command" "$_ri_kind" "$_ri_spine" "$_ri_gates" \
            "$_ri_axis_source" "$_ri_session_dir" "$_ri_manifest" <<'PY'
import datetime
import json
import os
import sys

(run_id, command, kind, spine, gates_raw,
 axis_source, session_dir, manifest) = sys.argv[1:9]

version = ""
try:
    with open(manifest, "r", encoding="utf-8") as handle:
        version = json.load(handle).get("version", "")
except (OSError, ValueError):
    version = ""

# gates: "name=true,other=false". Anything that is not exactly true/false is kept as a
# string — a gate whose value we cannot read is better recorded verbatim than dropped,
# because a missing gate makes the retro emit a false deviation.
gates = {}
for item in gates_raw.split(","):
    item = item.strip()
    if not item:
        continue
    name, _, value = item.partition("=")
    name = name.strip()
    if not name:
        continue
    value = value.strip().lower()
    gates[name] = True if value == "true" else False if value == "false" else value

record = {
    "schema": "relay.run-intent/1",
    "run_id": run_id,
    "relay_command": command,
    "kind": kind or None,
    "intended_spine": [s.strip() for s in spine.split(",") if s.strip()],
    "gates": gates,
    "axis_source": axis_source or None,
    "plugin_version": version or None,
    "session_dir": session_dir or None,
    "cwd": os.getcwd(),
    "started_at": datetime.datetime.now(datetime.timezone.utc)
                  .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
sys.stdout.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
PY
)" || _ri_fail serialize_failed "the record could not be serialized"

[ -n "$_ri_line" ] || _ri_fail serialize_failed "the serializer produced no output"

# One append of one line. `>>` on a local filesystem writes a short line atomically, so
# concurrent relay runs interleave lines but never corrupt one. The file is append-only
# by construction: nothing in relay ever rewrites or truncates it.
if ! printf '%s\n' "$_ri_line" >>"$_ri_file" 2>/dev/null; then
  _ri_fail write_failed "could not append to $_ri_file"
fi

printf 'RELAY_INTENT=RECORDED\n'
printf 'RELAY_INTENT_FILE=%s\n' "$_ri_file"
printf 'RELAY_INTENT_RUN_ID=%s\n' "$_ri_run_id"
printf '[relay] run intent recorded for %s (%s)\n' "$_ri_run_id" "$_ri_command"
exit 0
