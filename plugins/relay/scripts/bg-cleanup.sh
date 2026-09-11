#!/usr/bin/env bash
# relay: delete the bg sessions one run created (bg dispatch contract — Part 2a,
# docs/superpowers/plans/2026-08-25-relay-bg-auto-cleanup-nesting-plan.md §Step 4).
# EXECUTED, never sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/bg-cleanup.sh" --runid <id> --outcome <clean|failed> [--keep]
#
# Collects every short id a runid recorded, from BOTH registries:
#   1. sidecar env files at ~/.claude/relay/bg/<runid>/*.env (written by bg-dispatch.sh)
#   2. the run manifest at ~/.claude/relay/runs/<runid>/manifest.json, read via
#      bg-manifest.sh names
# Reading only one registry is the bug this script exists to prevent: `--engine
# bg-sessions` writes only sidecars, `--engine session-tree` writes only the manifest.
#
# Confirms every session reads as `stopped` first (via bg-liveness.sh — an observer,
# not a stopper) and deletes NOTHING until every session does. Any session that reads
# as anything else is printed as `RELAY_BG_STOP_REQUIRED=` and the script exits 1;
# the caller owns the actual stop, then re-runs this script. On `--outcome clean`
# without `--keep`, deletes the job directory at ~/.claude/jobs/<short-id>/ and, when
# safe, the session transcript named by that job's state.json `linkScanPath`. On
# `--outcome failed`, or with `--keep`, prints `RELAY_BG_KEPT=` and never deletes.
#
# Never deletes the registries themselves (sidecars, sidecar dir, manifest) — they are
# the record of what the run did, and keeping them is what makes a re-run idempotent.
#
# Exit codes:
#   0  cleanup ran to the end.
#   1  at least one session did not read as `stopped` — nothing was deleted, for any
#      session, on this run. All-or-nothing on purpose.
#   2  usage error (bad --runid, bad --outcome, missing jq, ...).
#   3  zero sessions found in either registry. Not an error.
#
# Overridable for tests, so this script never touches a real jobs directory or a real
# home directory under test:
#   HOME                 default the real $HOME
#   RELAY_BG_JOBS_DIR    default "$HOME/.claude/jobs"
set -u

_bgc_usage='usage: bg-cleanup.sh --runid <id> --outcome <clean|failed> [--keep]'

_bgc_usage_exit() {
  printf '[relay] error: %s\n' "$1" >&2
  printf '[relay] %s\n' "$_bgc_usage" >&2
  exit 2
}

if ! command -v jq >/dev/null 2>&1; then
  echo "[relay] error: jq is required by bg-cleanup.sh" >&2
  exit 2
fi

_bgc_runid_raw=""
_bgc_outcome=""
_bgc_keep=0

while [ $# -gt 0 ]; do
  case "$1" in
    --runid)     _bgc_runid_raw="${2:-}"; shift 2 || _bgc_usage_exit "--runid needs a value" ;;
    --runid=*)   _bgc_runid_raw="${1#--runid=}"; shift ;;
    --outcome)   _bgc_outcome="${2:-}"; shift 2 || _bgc_usage_exit "--outcome needs a value" ;;
    --outcome=*) _bgc_outcome="${1#--outcome=}"; shift ;;
    --keep)      _bgc_keep=1; shift ;;
    -h|--help)   printf '%s\n' "$_bgc_usage"; exit 0 ;;
    *)           _bgc_usage_exit "unknown argument: $1" ;;
  esac
done

[ -z "$_bgc_runid_raw" ] && _bgc_usage_exit "--runid is required"
case "$_bgc_outcome" in
  clean|failed) ;;
  *) _bgc_usage_exit "--outcome must be 'clean' or 'failed' (got '$_bgc_outcome')" ;;
esac

# Runid normalization must match bg-dispatch.sh Step 3 exactly, or the two scripts
# resolve the same wf_ input to different runids and cleanup finds no sessions.
_bgc_runid_norm="$(printf '%s' "$_bgc_runid_raw" | tr '[:upper:]' '[:lower:]' | sed -E 's/^wf_//' | tr -cd 'a-z0-9')"
_bgc_runid_len=${#_bgc_runid_norm}
if [ "$_bgc_runid_len" -gt 8 ]; then
  _bgc_runid="${_bgc_runid_norm: -8}"
else
  _bgc_runid="$_bgc_runid_norm"
fi
if ! printf '%s' "$_bgc_runid" | grep -qE '^[a-z0-9]{4,8}$'; then
  _bgc_usage_exit "--runid '$_bgc_runid_raw' does not normalize to ^[a-z0-9]{4,8}\$ (got '$_bgc_runid')"
fi

_bgc_home="${HOME:-}"
[ -z "$_bgc_home" ] && _bgc_usage_exit "HOME must be set"
_bgc_jobs_dir="${RELAY_BG_JOBS_DIR:-$_bgc_home/.claude/jobs}"
_bgc_scripts_dir="$(cd "$(dirname "$0")" && pwd)"
_bgc_liveness_script="${_bgc_scripts_dir}/bg-liveness.sh"
_bgc_manifest_script="${_bgc_scripts_dir}/bg-manifest.sh"

_bgc_sidecar_dir="${_bgc_home}/.claude/relay/bg/${_bgc_runid}"
_bgc_manifest_path="${_bgc_home}/.claude/relay/runs/${_bgc_runid}/manifest.json"

# --- Step 1: collect short ids from BOTH registries, union keyed by short id. -------
_bgc_names=()
_bgc_ids=()

_bgc_add() {
  local name="$1" sid="$2" i
  if [ -z "$sid" ]; then
    printf '[relay] note: sidecar for %s has an empty short id (launch denied before it resolved), skipped\n' "$name" >&2
    return
  fi
  if ! printf '%s' "$sid" | grep -qE '^[0-9a-f]{6,10}$'; then
    printf '[relay] note: %s has a short id that does not match ^[0-9a-f]{6,10}$ (%s), skipped\n' "$name" "$sid" >&2
    return
  fi
  for i in "${!_bgc_ids[@]}"; do
    [ "${_bgc_ids[$i]}" = "$sid" ] && return
  done
  _bgc_names+=("$name")
  _bgc_ids+=("$sid")
}

if [ -d "$_bgc_sidecar_dir" ]; then
  for _bgc_env in "$_bgc_sidecar_dir"/*.env; do
    [ -e "$_bgc_env" ] || continue
    _bgc_name=""
    _bgc_sid=""
    while IFS='=' read -r _bgc_k _bgc_v; do
      case "$_bgc_k" in
        RELAY_BG_NAME)     _bgc_name="$_bgc_v" ;;
        RELAY_BG_SHORT_ID) _bgc_sid="$_bgc_v" ;;
      esac
    done < "$_bgc_env"
    _bgc_add "$_bgc_name" "$_bgc_sid"
  done
fi

if [ -f "$_bgc_manifest_path" ]; then
  _bgc_manifest_out="$(bash "$_bgc_manifest_script" --runid "$_bgc_runid" names 2>/dev/null)"
  _bgc_pending_name=""
  while IFS= read -r _bgc_line; do
    case "$_bgc_line" in
      RELAY_BG_NAME=*)     _bgc_pending_name="${_bgc_line#RELAY_BG_NAME=}" ;;
      RELAY_BG_SHORT_ID=*) _bgc_add "$_bgc_pending_name" "${_bgc_line#RELAY_BG_SHORT_ID=}" ;;
    esac
  done <<< "$_bgc_manifest_out"
fi

_bgc_count="${#_bgc_ids[@]}"
if [ "$_bgc_count" -eq 0 ]; then
  printf '[relay] note: no bg session recorded for runid %s in either registry\n' "$_bgc_runid" >&2
  if [ "$_bgc_outcome" = "clean" ] && [ "$_bgc_keep" -eq 0 ]; then
    printf 'RELAY_BG_CLEANUP=deleted 0 sessions\n'
  else
    printf 'RELAY_BG_CLEANUP=kept 0 sessions\n'
  fi
  exit 3
fi

# --- Step 2: stop each session, then confirm. ----------------------------------------
_bgc_live_ids=()
declare -A _bgc_verdict_of=()

for _bgc_i in "${!_bgc_ids[@]}"; do
  _bgc_sid="${_bgc_ids[$_bgc_i]}"
  if [ ! -d "${_bgc_jobs_dir}/${_bgc_sid}" ]; then
    _bgc_verdict_of["$_bgc_sid"]="no-job-directory"
    continue
  fi
  _bgc_live_ids+=("$_bgc_sid")
done

if [ "${#_bgc_live_ids[@]}" -gt 0 ]; then
  _bgc_liveness_args=()
  for _bgc_sid in "${_bgc_live_ids[@]}"; do
    _bgc_liveness_args+=(--short-id "$_bgc_sid")
  done
  # stderr flows through. A prior 2>/dev/null hid missing-jq, unwritable-jobs-dir,
  # and malformed-short-id from the operator; the loop below then errored with no clue.
  _bgc_liveness_out="$(RELAY_BG_JOBS_DIR="$_bgc_jobs_dir" bash "$_bgc_liveness_script" "${_bgc_liveness_args[@]}")"
  # bg-liveness emits SHORT_ID then STATE, AGE, VERDICT per session, in that order.
  _bgc_pending_sid=""
  while IFS= read -r _bgc_line; do
    case "$_bgc_line" in
      RELAY_BG_SHORT_ID=*) _bgc_pending_sid="${_bgc_line#RELAY_BG_SHORT_ID=}" ;;
      RELAY_BG_VERDICT=*)  _bgc_verdict_of["$_bgc_pending_sid"]="${_bgc_line#RELAY_BG_VERDICT=}" ;;
    esac
  done <<< "$_bgc_liveness_out"
  for _bgc_sid in "${_bgc_live_ids[@]}"; do
    if [ -z "${_bgc_verdict_of[$_bgc_sid]:-}" ]; then
      printf '[relay] error: bg-liveness.sh did not report a verdict for %s\n' "$_bgc_sid" >&2
      exit 2
    fi
  done
fi

_bgc_stop_required=0
for _bgc_i in "${!_bgc_ids[@]}"; do
  _bgc_sid="${_bgc_ids[$_bgc_i]}"
  _bgc_name="${_bgc_names[$_bgc_i]}"
  _bgc_v="${_bgc_verdict_of[$_bgc_sid]}"
  if [ "$_bgc_v" != "stopped" ] && [ "$_bgc_v" != "no-job-directory" ]; then
    printf 'RELAY_BG_STOP_REQUIRED=%s %s\n' "$_bgc_name" "$_bgc_sid"
    _bgc_stop_required=1
  fi
done

if [ "$_bgc_stop_required" -eq 1 ]; then
  exit 1
fi

# --- Step 3: --outcome failed, or --keep -> stop only, never delete. ----------------
if [ "$_bgc_outcome" = "failed" ] || [ "$_bgc_keep" -eq 1 ]; then
  if [ "$_bgc_outcome" = "failed" ]; then
    _bgc_reason="outcome-failed"
  else
    _bgc_reason="keep-flag"
  fi
  _bgc_n=0
  for _bgc_i in "${!_bgc_ids[@]}"; do
    _bgc_sid="${_bgc_ids[$_bgc_i]}"
    _bgc_name="${_bgc_names[$_bgc_i]}"
    _bgc_job_dir="${_bgc_jobs_dir}/${_bgc_sid}"
    printf 'RELAY_BG_KEPT=%s %s %s %s\n' "$_bgc_name" "$_bgc_sid" "$_bgc_job_dir" "$_bgc_reason"
    _bgc_n=$((_bgc_n + 1))
  done
  printf 'RELAY_BG_CLEANUP=kept %d sessions\n' "$_bgc_n"
  exit 0
fi

# --- Step 4: delete, on --outcome clean without --keep. ------------------------------
_bgc_deleted_n=0
for _bgc_i in "${!_bgc_ids[@]}"; do
  _bgc_sid="${_bgc_ids[$_bgc_i]}"
  _bgc_name="${_bgc_names[$_bgc_i]}"
  _bgc_job_dir="${_bgc_jobs_dir}/${_bgc_sid}"

  if [ ! -d "$_bgc_job_dir" ]; then
    printf 'RELAY_BG_CLEANUP_SKIPPED=%s %s no-job-directory\n' "$_bgc_name" "$_bgc_sid"
    continue
  fi

  _bgc_state_file="${_bgc_job_dir}/state.json"
  _bgc_link=""
  if [ -f "$_bgc_state_file" ]; then
    _bgc_link="$(jq -r '.linkScanPath // ""' "$_bgc_state_file" 2>/dev/null)"
  fi

  # Emit the exact rejection reason so a reviewer can tell a benign miss (no link
  # recorded) from a rejected path (`..` traversal, off-tree, wrong suffix).
  # Prefix check alone is not enough: `$HOME/.claude/projects/../../etc/passwd.jsonl`
  # matches the prefix and `-f` follows the resolved path — reject any `..` segment.
  _bgc_skip_reason=""
  if [ -z "$_bgc_link" ]; then
    _bgc_skip_reason="no-link"
  elif [[ "$_bgc_link" == *"/../"* || "$_bgc_link" == *"/.." ]]; then
    _bgc_skip_reason="unsafe-path"
  elif [[ "$_bgc_link" != "${_bgc_home}/.claude/projects/"* ]]; then
    _bgc_skip_reason="outside-projects"
  elif [[ "$_bgc_link" != *.jsonl ]]; then
    _bgc_skip_reason="not-jsonl"
  elif [ ! -f "$_bgc_link" ]; then
    _bgc_skip_reason="not-a-file"
  fi

  if [ -z "$_bgc_skip_reason" ]; then
    rm -f "$_bgc_link"
  else
    printf 'RELAY_BG_CLEANUP_SKIPPED=%s %s no-transcript (%s)\n' "$_bgc_name" "$_bgc_sid" "$_bgc_skip_reason"
  fi

  rm -rf "$_bgc_job_dir"
  _bgc_deleted_n=$((_bgc_deleted_n + 1))
done

printf 'RELAY_BG_CLEANUP=deleted %d sessions\n' "$_bgc_deleted_n"
exit 0
