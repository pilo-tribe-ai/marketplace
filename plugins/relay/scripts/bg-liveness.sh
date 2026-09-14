#!/usr/bin/env bash
# relay: liveness poll for background Claude Code children (bg dispatch contract §1.5
# — docs/bg-dispatch-contract.md). EXECUTED, never sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-liveness.sh" --short-id <id> [--short-id <id> ...] \
#     [--stale-seconds <n>]
#
# 4.30.0: first version. Answers exactly one question per child: alive, stopped,
# stale, or unknown. It NEVER answers whether the child's task succeeded — `state`
# reports turn posture, not task outcome (S4-2). The envelope is the only truth about
# completion; that check belongs to the caller, never to this script.
#
# state -> verdict (spec §1.5 — the full mapping, definitional for this contract):
#   working  -> alive    mid-turn.
#   blocked  -> alive    turn-end posture after a clean end-of-turn (a terminal
#                         envelope, or a decision request). Still holds its name,
#                         still reachable.
#   done     -> alive    SAME turn-end posture as blocked; some Claude Code versions
#                         write `done` instead of `blocked`. This is the one
#                         counter-intuitive row. Do NOT read `done` as `stopped`.
#   stopped  -> stopped  the session process has ended (S4-1: killing a child produced
#                         no message, only this state change — this is the only value
#                         meaning the child is gone).
#   failed   -> stopped  the process ended abnormally; treated the same as `stopped`.
#   absent/unreadable -> unknown   launch may still be in flight. Never treated as
#                         stopped; a caller must not respawn on `unknown` alone.
#
# `updatedAt` age decides ONLY among the alive values (working/blocked/done). Past
# the stale ceiling, the verdict downgrades from alive to stale. `stopped`, `failed`,
# and `unknown` are NEVER reclassified by age.
#
# Exit codes:
#   0  every verdict is alive.
#   1  at least one verdict is stopped. (The bg-sessions watcher's liveness escape
#      fires on this code.)
#   2  usage error.
#   3  no stopped verdict, but at least one stale or unknown.
#
# Overridable for tests, so this script never reads a real jobs directory under test:
#   RELAY_BG_JOBS_DIR       default "$HOME/.claude/jobs"
#   RELAY_BG_STALE_SECONDS  default 900; --stale-seconds overrides this per invocation.
set -u

_bgv_usage='usage: bg-liveness.sh --short-id <id> [--short-id <id> ...] [--stale-seconds <n>]'

_bgv_usage_exit() {
  printf '[relay] error: %s\n' "$1" >&2
  printf '[relay] %s\n' "$_bgv_usage" >&2
  exit 2
}

_bgv_ids=()
_bgv_stale_flag=""

while [ $# -gt 0 ]; do
  case "$1" in
    --short-id)          _bgv_ids+=("${2:-}"); shift 2 || _bgv_usage_exit "--short-id needs a value" ;;
    --short-id=*)         _bgv_ids+=("${1#--short-id=}"); shift ;;
    --stale-seconds)      _bgv_stale_flag="${2:-}"; shift 2 || _bgv_usage_exit "--stale-seconds needs a value" ;;
    --stale-seconds=*)    _bgv_stale_flag="${1#--stale-seconds=}"; shift ;;
    -h|--help)            printf '%s\n' "$_bgv_usage"; exit 0 ;;
    *)                    _bgv_usage_exit "unknown argument: $1" ;;
  esac
done

[ "${#_bgv_ids[@]}" -gt 0 ] || _bgv_usage_exit "at least one --short-id is required"

_bgv_stale="${_bgv_stale_flag:-${RELAY_BG_STALE_SECONDS:-900}}"
case "$_bgv_stale" in
  ''|*[!0-9]*) _bgv_usage_exit "--stale-seconds / RELAY_BG_STALE_SECONDS must be a whole number of seconds, got '$_bgv_stale'" ;;
esac

_bgv_jobs_dir="${RELAY_BG_JOBS_DIR:-$HOME/.claude/jobs}"

_bgv_alive=0
_bgv_stale_n=0
_bgv_stopped=0
_bgv_unknown=0

for _bgv_id in "${_bgv_ids[@]}"; do
  _bgv_state_file="$_bgv_jobs_dir/$_bgv_id/state.json"
  _bgv_state=""
  _bgv_age=-1
  _bgv_verdict="unknown"

  if [ -f "$_bgv_state_file" ] && [ -r "$_bgv_state_file" ]; then
    _bgv_raw_state="$(jq -r '.state // ""' "$_bgv_state_file" 2>/dev/null)"
    if [ $? -eq 0 ] && [ -n "$_bgv_raw_state" ]; then
      _bgv_state="$_bgv_raw_state"

      # ISO-8601-with-milliseconds is not accepted by jq's fromdateiso8601, so the
      # fractional part is stripped first. [repo, measured against a live jobs dir]
      _bgv_epoch="$(jq -r '(.updatedAt // "") | sub("\\.[0-9]+Z$";"Z") | fromdateiso8601' \
                     "$_bgv_state_file" 2>/dev/null)"
      if printf '%s' "$_bgv_epoch" | grep -qE '^[0-9]+$'; then
        _bgv_now="$(date +%s)"
        _bgv_age=$(( _bgv_now - _bgv_epoch ))
        [ "$_bgv_age" -lt 0 ] && _bgv_age=0
      else
        _bgv_age=-1
      fi

      case "$_bgv_state" in
        working|blocked|done)
          if [ "$_bgv_age" -ge 0 ] && [ "$_bgv_age" -gt "$_bgv_stale" ]; then
            _bgv_verdict="stale"
          else
            _bgv_verdict="alive"
          fi
          ;;
        stopped|failed)
          _bgv_verdict="stopped"
          # stopped/failed are never reclassified by age.
          ;;
        *)
          _bgv_verdict="unknown"
          ;;
      esac
    fi
  fi

  case "$_bgv_verdict" in
    alive)   _bgv_alive=$((_bgv_alive + 1)) ;;
    stale)   _bgv_stale_n=$((_bgv_stale_n + 1)) ;;
    stopped) _bgv_stopped=$((_bgv_stopped + 1)) ;;
    unknown) _bgv_unknown=$((_bgv_unknown + 1)) ;;
  esac

  printf 'RELAY_BG_SHORT_ID=%s\n' "$_bgv_id"
  printf 'RELAY_BG_STATE=%s\n' "$_bgv_state"
  printf 'RELAY_BG_AGE_SECONDS=%s\n' "$_bgv_age"
  printf 'RELAY_BG_VERDICT=%s\n' "$_bgv_verdict"
done

printf 'RELAY_BG_SUMMARY=alive=%d,stale=%d,stopped=%d,unknown=%d\n' \
  "$_bgv_alive" "$_bgv_stale_n" "$_bgv_stopped" "$_bgv_unknown"

if [ "$_bgv_stopped" -gt 0 ]; then
  exit 1
elif [ "$_bgv_stale_n" -gt 0 ] || [ "$_bgv_unknown" -gt 0 ]; then
  exit 3
else
  exit 0
fi
