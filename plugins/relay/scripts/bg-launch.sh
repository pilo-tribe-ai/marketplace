#!/usr/bin/env bash
# LC_ALL=C keeps the `[a-z0-9-]` glob ranges below case-sensitive: under a UTF-8
# locale, bash's collation can fold `[a-z]` to match uppercase too, which would
# silently accept a name the naming grammar must reject.
export LC_ALL=C
# relay: the only sanctioned launcher for a background Claude Code child (bg dispatch
# contract §1.3, §bg-launch.sh interface — docs/bg-dispatch-contract.md). EXECUTED,
# never sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-launch.sh" --name <name> --model <model> \
#     --permission-mode <mode> --prompt-file <path> [--fork-from <session-id>]
#
# Validate a session name only, without launching anything:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-launch.sh" --check-name <name>
#
# 4.30.0: first version.
#   - Builds the launch command in the proven shape: `claude --bg --name ... --model
#     ... --permission-mode ... "<prompt>"`, with the prompt as the LAST argument. No
#     variadic flag (one that consumes a list of following arguments, such as a
#     tool-allowlist flag) sits before it — a variadic flag silently swallows the
#     prompt and the child sits idle forever with an empty `intent` (launch trap 1,
#     spike findings doc "Launch mechanics"). This script never names such a flag.
#   - Confirms `intent` is non-empty in the child's state.json before reporting
#     success (spec §1.3 step 2). Never scans the jobs directory by the `name` field
#     to resolve the short id — names are not unique (S4-3). The short id is parsed
#     only from this script's own launch output.
#   - A classifier-denied launch (launch trap 2), an unparseable short id, and an
#     `intent` still empty at the wait ceiling all report the same typed outcome:
#     RELAY_BG_LAUNCH=LAUNCH_DENIED (spec §1.3 step 3). A denied launch is a normal,
#     honestly-reported outcome, never an assumption that the child exists.
#   - `--permission-mode dontAsk` is refused with a usage error. A dontAsk child
#     cannot run Bash (S3-1); this script never selects dontAsk and does not let a
#     caller reintroduce it.
#   - [inferred] Short-id extraction: `claude --bg` prints the short id to stdout at
#     launch, but this design leaves the exact surrounding text unspecified. This
#     script takes the LAST bare hex token of 6-10 lowercase hex characters in the
#     child process's combined stdout+stderr as the short id. Reconcile this regex
#     against real `claude --bg` output before the live round trip
#     (tests/e2e/bg-s1-roundtrip.sh) is trusted.
#
# Exit codes:
#   0  RELAY_BG_LAUNCH=OK.
#   1  RELAY_BG_LAUNCH=LAUNCH_DENIED (classifier refusal, unparseable short id, or
#      intent still empty at RELAY_BG_LAUNCH_TIMEOUT_SECONDS).
#   2  usage error — missing/unknown argument, unreadable or empty prompt file,
#      forbidden permission mode, or an invalid --name.
#
# Overridable for tests, so this script never launches a real session under test:
#   RELAY_BG_JOBS_DIR                 default "$HOME/.claude/jobs"
#   RELAY_BG_LAUNCH_TIMEOUT_SECONDS   default 15
#
# `claude` must be on PATH. Tests put a stub `claude` first on PATH and drive this
# script with `HOME` pointed at a scratch directory.
set -u

_bgl_usage='usage: bg-launch.sh --name <name> --model <model> --permission-mode <mode> --prompt-file <path> [--fork-from <session-id>]
       bg-launch.sh --check-name <name>'

_bgl_usage_exit() {
  printf '[relay] error: %s\n' "$1" >&2
  printf '[relay] %s\n' "$_bgl_usage" >&2
  exit 2
}

_bgl_deny() {
  printf '[relay] error: %s\n' "$1" >&2
  printf 'RELAY_BG_LAUNCH=LAUNCH_DENIED\n'
  exit 1
}

_bgl_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

# Roster source: role stems from roles/*.md (minus README), plus the registered agent
# slugs named as `relay:<slug>` in docs/agent-roster.md. Read at run time — never
# hard-coded — so a new role or agent needs no change here. [plan §D1.2.5]
_bgl_roster() {
  local f b
  for f in "$_bgl_root"/roles/*.md; do
    [ -e "$f" ] || continue
    b="$(basename "$f" .md)"
    [ "$b" = "README" ] && continue
    printf '%s\n' "$b"
  done
  if [ -f "$_bgl_root/docs/agent-roster.md" ]; then
    grep -oE '`relay:[a-z][a-z0-9-]*`' "$_bgl_root/docs/agent-roster.md" \
      | sed -E 's/`relay:([a-z0-9-]+)`/\1/'
  fi
}

# Reduced name validation (spec §1.2). Checks only what a validator can actually
# decide — `product` and `goal` are open kebab slugs and are never parsed out of the
# name. [plan §D1.2.5]
#
# [plan/deviation] Roster-position check. The spec names two fixed positions
# (`product-role` for the orchestrator, `product-role-goal` otherwise) but several
# roster roles are themselves multi-word kebab slugs (`code-reviewer`,
# `ui-accessibility-evaluator`), and `product`/`goal` are unbounded-length kebab slugs
# too, so a literal fixed array index cannot generally locate the role token without
# parsing `product`/`goal` — which the spec forbids. This script instead accepts the
# name when some roster role appears as a hyphen-bounded contiguous run of tokens
# anywhere in the stem (name with the runid suffix stripped). This is the same
# "roster hit at a fixed position, not a parse" leniency the spec calls for: it finds
# `implementer` in `roi-dashboard-implementer-feature-a`, and it still accepts a
# product slug that itself contains a role word, because it never tries to tell
# `product` and `role` apart.
_bgl_validate_name() {
  local name="$1" len stem role hit
  len=${#name}
  if [ "$len" -eq 0 ] || [ "$len" -gt 63 ]; then
    printf 'length must be 1-63 characters (got %d)' "$len"
    return 1
  fi
  case "$name" in
    *[!a-z0-9-]*)
      printf 'charset: only lowercase a-z, 0-9, and - are allowed'
      return 1
      ;;
  esac
  if ! printf '%s' "$name" | grep -qE -- '-[a-z0-9]{4,8}$'; then
    printf 'missing a runid suffix matching -[a-z0-9]{4,8} at the end (S4-3: a stopped session keeps its name and would collide with its own replacement)'
    return 1
  fi
  stem="$(printf '%s' "$name" | sed -E 's/-[a-z0-9]{4,8}$//')"
  if [ -z "$stem" ]; then
    printf 'name has no content before the runid suffix'
    return 1
  fi
  hit=0
  while IFS= read -r role; do
    [ -z "$role" ] && continue
    case "-$stem-" in
      *"-$role-"*) hit=1; break ;;
    esac
  done < <(_bgl_roster)
  if [ "$hit" -eq 0 ]; then
    printf 'no roster role token found in "%s" — role must be a slug from roles/*.md or docs/agent-roster.md' "$stem"
    return 1
  fi
  return 0
}

_bgl_name=""
_bgl_model=""
_bgl_mode=""
_bgl_prompt_file=""
_bgl_fork_from=""
_bgl_check_name=""
_bgl_check_name_mode=0

while [ $# -gt 0 ]; do
  case "$1" in
    --name)               _bgl_name="${2:-}"; shift 2 || _bgl_usage_exit "--name needs a value" ;;
    --name=*)              _bgl_name="${1#--name=}"; shift ;;
    --model)               _bgl_model="${2:-}"; shift 2 || _bgl_usage_exit "--model needs a value" ;;
    --model=*)              _bgl_model="${1#--model=}"; shift ;;
    --permission-mode)      _bgl_mode="${2:-}"; shift 2 || _bgl_usage_exit "--permission-mode needs a value" ;;
    --permission-mode=*)    _bgl_mode="${1#--permission-mode=}"; shift ;;
    --prompt-file)           _bgl_prompt_file="${2:-}"; shift 2 || _bgl_usage_exit "--prompt-file needs a value" ;;
    --prompt-file=*)         _bgl_prompt_file="${1#--prompt-file=}"; shift ;;
    --fork-from)             _bgl_fork_from="${2:-}"; shift 2 || _bgl_usage_exit "--fork-from needs a value" ;;
    --fork-from=*)           _bgl_fork_from="${1#--fork-from=}"; shift ;;
    --check-name)            _bgl_check_name="${2:-}"; _bgl_check_name_mode=1; shift 2 || _bgl_usage_exit "--check-name needs a value" ;;
    --check-name=*)          _bgl_check_name="${1#--check-name=}"; _bgl_check_name_mode=1; shift ;;
    -h|--help)               printf '%s\n' "$_bgl_usage"; exit 0 ;;
    *)                       _bgl_usage_exit "unknown argument: $1" ;;
  esac
done

if [ "$_bgl_check_name_mode" -eq 1 ]; then
  if _bgl_reason="$(_bgl_validate_name "$_bgl_check_name")"; then
    printf 'RELAY_BG_NAME_OK=1\n'
    exit 0
  fi
  printf '[relay] error: invalid session name: %s\n' "$_bgl_reason" >&2
  exit 2
fi

[ -n "$_bgl_name" ]         || _bgl_usage_exit "--name is required"
[ -n "$_bgl_model" ]        || _bgl_usage_exit "--model is required"
[ -n "$_bgl_mode" ]         || _bgl_usage_exit "--permission-mode is required"
[ -n "$_bgl_prompt_file" ]  || _bgl_usage_exit "--prompt-file is required"

if ! _bgl_reason="$(_bgl_validate_name "$_bgl_name")"; then
  _bgl_usage_exit "invalid session name: $_bgl_reason"
fi

# S3-1: a child under dontAsk cannot run Bash. This script never selects dontAsk and
# refuses it as an argument too, so no caller can reintroduce the blocker through it.
if [ "$_bgl_mode" = "dontAsk" ]; then
  _bgl_usage_exit "--permission-mode dontAsk is forbidden — a dontAsk child cannot run Bash (S3-1)"
fi

if [ ! -f "$_bgl_prompt_file" ] || [ ! -r "$_bgl_prompt_file" ]; then
  _bgl_usage_exit "--prompt-file '$_bgl_prompt_file' is not a readable file"
fi
if [ ! -s "$_bgl_prompt_file" ]; then
  _bgl_usage_exit "--prompt-file '$_bgl_prompt_file' is empty"
fi
_bgl_prompt="$(cat "$_bgl_prompt_file")"

# Command construction (spec §1.3 step 1). The prompt is the LAST argument. No
# variadic flag sits before it.
_bgl_cmd=(claude --bg --name "$_bgl_name" --model "$_bgl_model" --permission-mode "$_bgl_mode")
if [ -n "$_bgl_fork_from" ]; then
  _bgl_cmd+=(--resume "$_bgl_fork_from" --fork-session)
fi
_bgl_cmd+=("$_bgl_prompt")

_bgl_launch_out="$("${_bgl_cmd[@]}" 2>&1)"
_bgl_launch_rc=$?

# Short-id resolution (spec §1.3, S4-3): parsed from this launch's own output, never
# by scanning the jobs directory for a matching `name` field.
_bgl_short_id="$(printf '%s\n' "$_bgl_launch_out" | grep -oE '\b[0-9a-f]{6,10}\b' | tail -n 1)"

if [ "$_bgl_launch_rc" -ne 0 ] || [ -z "$_bgl_short_id" ]; then
  _bgl_deny "launch denied or no short id was parsed from the launch output (exit=$_bgl_launch_rc)"
fi

_bgl_jobs_dir="${RELAY_BG_JOBS_DIR:-$HOME/.claude/jobs}"
_bgl_state_file="$_bgl_jobs_dir/$_bgl_short_id/state.json"
_bgl_timeout="${RELAY_BG_LAUNCH_TIMEOUT_SECONDS:-15}"
_bgl_elapsed=0
_bgl_intent=""

# Wait ceiling (spec §1.3 step 2, "bg-launch.sh interface"). A missing file is "not
# ready", never a failure, until the ceiling is hit.
while [ "$_bgl_elapsed" -lt "$_bgl_timeout" ]; do
  if [ -f "$_bgl_state_file" ]; then
    _bgl_intent="$(jq -r '.intent // ""' "$_bgl_state_file" 2>/dev/null)"
    [ -n "$_bgl_intent" ] && break
  fi
  sleep 1
  _bgl_elapsed=$((_bgl_elapsed + 1))
done

if [ -z "$_bgl_intent" ]; then
  _bgl_deny "intent is still empty in $_bgl_state_file after ${_bgl_timeout}s (empty-intent launch, launch trap 1)"
fi

printf 'RELAY_BG_NAME=%s\n' "$_bgl_name"
printf 'RELAY_BG_SHORT_ID=%s\n' "$_bgl_short_id"
printf 'RELAY_BG_LAUNCH=OK\n'
exit 0
