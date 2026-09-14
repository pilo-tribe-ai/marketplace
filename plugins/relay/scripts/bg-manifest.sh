#!/usr/bin/env bash
# relay: the session-tree run manifest (bg dispatch contract, spec §Deliverable 3,
# Bookkeeping — docs/bg-dispatch-contract.md). EXECUTED, never sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-manifest.sh" --runid 7f3c init --command implement
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-manifest.sh" --runid 7f3c add-session \
#     --name roi-dashboard-implementer-feature-a-7f3c --launch-id abc123 \
#     --role implementer --parent MAIN --phase spawned
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-manifest.sh" --runid 7f3c set-phase \
#     --name roi-dashboard-implementer-feature-a-7f3c --phase done
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-manifest.sh" --runid 7f3c read
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-manifest.sh" --runid 7f3c names
#
# 4.30.0: first version.
#   - One file per run: `${HOME}/.claude/relay/runs/<runid>/manifest.json`. This is a
#     SEPARATE artifact from `~/.claude/relay/runs.jsonl` — `record-run-intent.sh`'s
#     advisory line never fires for session-tree, because session-tree runs no
#     Workflow and allocates no `wf_…` id (spec §Deliverable 3, Bookkeeping).
#     `record-run-intent.sh` itself is unchanged and unused by this script.
#   - The file holds CURRENT STATE, never a log of past events. `set-phase` updates a
#     session's record in place; it never appends a second record for the same name.
#   - Every write goes to a temporary path in the same directory, then `mv` into
#     place, so a reader never observes a half-written file (spec: "rewrites the
#     whole file atomically").
#   - A write failure is FATAL — the opposite of `record-run-intent.sh`'s ADVISORY
#     doctrine. The manifest is the only resume path for a session-tree run, so a
#     failed write prints `[relay] error: manifest write failed: <path>` and exits 1.
#     Nothing here degrades and continues.
#   - `<runid>` must match `^[a-z0-9]{4,8}$` — the same shape spec §1.2 requires of
#     every session name's runid suffix, because it IS that suffix (one runid space,
#     not two).
#
# Exit codes:
#   0  success.
#   1  read or write failure (FATAL — a missing/malformed manifest on `read`,
#      `add-session`, or `set-phase`; a write that could not be moved into place).
#   2  usage error — missing/unknown argument, bad --runid, unknown subcommand.
#
# Requires `jq`. jq is already a hard dependency of this plugin.
#
# Overridable for tests, so this script never writes into a real home directory
# under test:
#   HOME   default the real $HOME — tests point this at a scratch directory, the same
#          way test_record_run_intent.py drives record-run-intent.sh.
set -u

_bgm_usage='usage: bg-manifest.sh --runid <id> init --command <name>
       bg-manifest.sh --runid <id> add-session --name <n> --launch-id <short-id> --role <slug> --parent <name|MAIN> --phase <status>
       bg-manifest.sh --runid <id> set-phase --name <n> --phase <status>
       bg-manifest.sh --runid <id> read
       bg-manifest.sh --runid <id> names'

_bgm_usage_exit() {
  printf '[relay] error: %s\n' "$1" >&2
  printf '[relay] %s\n' "$_bgm_usage" >&2
  exit 2
}

_bgm_fatal() {
  printf '[relay] error: manifest write failed: %s\n' "$1" >&2
  exit 1
}

if ! command -v jq >/dev/null 2>&1; then
  echo "[relay] error: jq is required by bg-manifest.sh" >&2
  exit 2
fi

_runid=""
_cmd=""
_arg_command=""
_arg_name=""
_arg_launch_id=""
_arg_role=""
_arg_parent=""
_arg_phase=""

# First flag must be --runid, then a bare subcommand, then subcommand flags — the
# repo's long-flag idiom, extended with one positional subcommand token.
while [ $# -gt 0 ]; do
  case "$1" in
    --runid) _runid="${2:-}"; shift 2 || _bgm_usage_exit "--runid needs a value" ;;
    --runid=*) _runid="${1#--runid=}"; shift ;;
    --command) _arg_command="${2:-}"; shift 2 || _bgm_usage_exit "--command needs a value" ;;
    --command=*) _arg_command="${1#--command=}"; shift ;;
    --name) _arg_name="${2:-}"; shift 2 || _bgm_usage_exit "--name needs a value" ;;
    --name=*) _arg_name="${1#--name=}"; shift ;;
    --launch-id) _arg_launch_id="${2:-}"; shift 2 || _bgm_usage_exit "--launch-id needs a value" ;;
    --launch-id=*) _arg_launch_id="${1#--launch-id=}"; shift ;;
    --role) _arg_role="${2:-}"; shift 2 || _bgm_usage_exit "--role needs a value" ;;
    --role=*) _arg_role="${1#--role=}"; shift ;;
    --parent) _arg_parent="${2:-}"; shift 2 || _bgm_usage_exit "--parent needs a value" ;;
    --parent=*) _arg_parent="${1#--parent=}"; shift ;;
    --phase) _arg_phase="${2:-}"; shift 2 || _bgm_usage_exit "--phase needs a value" ;;
    --phase=*) _arg_phase="${1#--phase=}"; shift ;;
    init|add-session|set-phase|read|names)
      [ -n "$_cmd" ] && _bgm_usage_exit "more than one subcommand given"
      _cmd="$1"; shift ;;
    *) _bgm_usage_exit "unknown argument: $1" ;;
  esac
done

[ -z "$_runid" ] && _bgm_usage_exit "--runid is required"
if ! printf '%s' "$_runid" | grep -qE '^[a-z0-9]{4,8}$'; then
  _bgm_usage_exit "--runid must match ^[a-z0-9]{4,8}\$ (got '$_runid')"
fi
[ -z "$_cmd" ] && _bgm_usage_exit "a subcommand is required (init | add-session | set-phase | read | names)"

_bgm_home="${HOME:-}"
[ -z "$_bgm_home" ] && _bgm_usage_exit "HOME must be set"
_bgm_dir="${_bgm_home}/.claude/relay/runs/${_runid}"
_bgm_path="${_bgm_dir}/manifest.json"

# Atomic write: temp file in the SAME directory (so `mv` is a rename, not a
# cross-filesystem copy), then `mv` into place. A reader never sees a half-written
# file. A failed write is FATAL — print and exit 1, never degrade.
_bgm_write() {
  local json="$1" tmp
  mkdir -p "$_bgm_dir" 2>/dev/null || _bgm_fatal "$_bgm_path"
  tmp="${_bgm_path}.tmp.$$"
  if ! printf '%s' "$json" > "$tmp" 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null
    _bgm_fatal "$_bgm_path"
  fi
  if ! mv "$tmp" "$_bgm_path" 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null
    _bgm_fatal "$_bgm_path"
  fi
}

_bgm_read_or_fatal() {
  if [ ! -f "$_bgm_path" ]; then
    printf '[relay] error: manifest write failed: %s (no manifest for runid %s — run init first)\n' \
      "$_bgm_path" "$_runid" >&2
    exit 1
  fi
  if ! jq empty "$_bgm_path" >/dev/null 2>&1; then
    printf '[relay] error: manifest write failed: %s (manifest is not valid JSON)\n' "$_bgm_path" >&2
    exit 1
  fi
  cat "$_bgm_path"
}

case "$_cmd" in
  init)
    [ -z "$_arg_command" ] && _bgm_usage_exit "init requires --command"
    _now="$(date -u '+%Y-%m-%dT%H:%M:%S.000Z' 2>/dev/null || true)"
    _json="$(jq -n --arg runid "$_runid" --arg command "$_arg_command" --arg started_at "$_now" \
      '{runid: $runid, command: $command, started_at: $started_at, sessions: []}')"
    _bgm_write "$_json"
    ;;
  add-session)
    [ -z "$_arg_name" ] && _bgm_usage_exit "add-session requires --name"
    [ -z "$_arg_launch_id" ] && _bgm_usage_exit "add-session requires --launch-id"
    [ -z "$_arg_role" ] && _bgm_usage_exit "add-session requires --role"
    [ -z "$_arg_parent" ] && _bgm_usage_exit "add-session requires --parent"
    [ -z "$_arg_phase" ] && _bgm_usage_exit "add-session requires --phase"
    _existing="$(_bgm_read_or_fatal)"
    _json="$(printf '%s' "$_existing" | jq \
      --arg name "$_arg_name" --arg launch_id "$_arg_launch_id" \
      --arg role "$_arg_role" --arg parent "$_arg_parent" --arg phase "$_arg_phase" \
      '.sessions = ([.sessions[] | select(.name != $name)]
        + [{name: $name, launch_id: $launch_id, role: $role, parent: $parent, phase: $phase}])')"
    _bgm_write "$_json"
    ;;
  set-phase)
    [ -z "$_arg_name" ] && _bgm_usage_exit "set-phase requires --name"
    [ -z "$_arg_phase" ] && _bgm_usage_exit "set-phase requires --phase"
    _existing="$(_bgm_read_or_fatal)"
    if ! printf '%s' "$_existing" | jq -e --arg name "$_arg_name" '.sessions | any(.name == $name)' >/dev/null 2>&1; then
      printf '[relay] error: manifest write failed: %s (no session named %s — add-session first)\n' \
        "$_bgm_path" "$_arg_name" >&2
      exit 1
    fi
    _json="$(printf '%s' "$_existing" | jq \
      --arg name "$_arg_name" --arg phase "$_arg_phase" \
      '.sessions = [.sessions[] | if .name == $name then (.phase = $phase) else . end]')"
    _bgm_write "$_json"
    ;;
  read)
    _bgm_read_or_fatal
    ;;
  names)
    _existing="$(_bgm_read_or_fatal)"
    printf '%s' "$_existing" | jq -r '.sessions[] | "RELAY_BG_NAME=\(.name)\nRELAY_BG_SHORT_ID=\(.launch_id)"'
    ;;
esac

exit 0
