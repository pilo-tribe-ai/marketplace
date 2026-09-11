#!/usr/bin/env bash
# relay: bg-sessions dispatcher entry point — the counterpart of
# skills/dispatching-acpx-agents/acpx-dispatch.sh for the background-session engine
# (spec §Deliverable 2, Dispatch — docs/bg-dispatch-contract.md). EXECUTED, never
# sourced:
#   BG_ROLE_SLUG=implementer BG_RUN_ID=wf_918a4deb-aba WORKTREE=/abs/path \
#     bash skills/dispatching-bg-agents/bg-dispatch.sh
#
# 4.30.0: first version. Far smaller than acpx-dispatch.sh: it resolves one role's
# binding from the SAME bindings/presets.yaml (no new field — spec §Deliverable 2,
# Bindings), materializes the identity preamble (§1.4, bg-sessions variant) plus the
# role body, writes the sidecar and creates the handoff directory BEFORE launch, then
# launches the child through scripts/bg-launch.sh — the only sanctioned launcher.
# It never calls `claude --bg` itself.
#
# Inputs (env-passed):
#   BG_ROLE_SLUG       — required. Role slug, e.g. implementer.
#   BG_RUN_ID          — required. The Workflow's own run id (e.g. wf_918a4deb-aba).
#                         The runid suffix is derived from this ONE input, never
#                         invented twice (spec §1.2: "one rule, one source") —
#                         lowercased, `wf_` prefix stripped, every character outside
#                         [a-z0-9] removed, then the last 4-8 characters kept.
#   WORKTREE           — required. Absolute path to the active worktree. The child
#                         inherits this as its cwd (bg-launch.sh is invoked from here).
#   BG_INPUTS_JSON     — optional, default "{}". JSON object of slot-name -> value for
#                         the role body's {{SLOT_*}} substitution.
#   RELAY_ROLE_PATH    — optional. External role file, ahead of the default
#                         roles/<slug>.md -> agents/<slug>.md lookup (same contract as
#                         acpx-dispatch.sh's identically-named var).
#   BG_PRESETS_PATH    — optional test seam, default <plugin-root>/bindings/presets.yaml.
#   BG_LAUNCH_OVERRIDE — optional test seam, default <plugin-root>/scripts/bg-launch.sh.
#
# Output (stdout, KEY=VALUE lines, per repo convention):
#   RELAY_BG_SIDECAR=<path>
#   RELAY_BG_HANDOFF=<path>
#   RELAY_BG_NAME=<name>
#   RELAY_BG_SHORT_ID=<short-id>   (only on RELAY_BG_DISPATCH=OK)
#   RELAY_BG_DISPATCH=OK|LAUNCH_DENIED
#
# Exit codes:
#   0  a child was launched (RELAY_BG_DISPATCH=OK).
#   1  RELAY_BG_LAUNCH=LAUNCH_DENIED, one retry, then RELAY_BG_DISPATCH=LAUNCH_DENIED
#      (spec §Failure behavior: "LAUNCH_DENIED, one retry, then errored" — this
#      script reports the typed outcome; the caller decides whether that means
#      `errored`).
#   2  usage error — missing required var, missing role file (ROLE_FILE_MISSING),
#      missing binding, or `yq`/`jq` not on PATH.
#
# Does not touch bindings/presets.yaml (unchanged in v1, spec §Deliverable 2,
# Bindings) — it only reads it. Does not run capability-validate.js itself; the
# requires/provides gate is enforced statically over every role by
# tests/unit/skill-structure/test_capability_gate.py, the same guard
# dispatching-acpx-agents relies on (spec §Deliverable 2, Wrapper responsibilities,
# step 2 — "Unchanged. Same gate.").
set -u

_bgd_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_bgd_root="$(cd "$_bgd_here/../.." && pwd)"

_bgd_err() { printf '[relay] error: %s\n' "$1" >&2; exit "${2:-2}"; }

command -v yq >/dev/null 2>&1 || _bgd_err "yq not on PATH (mikefarah/yq v4)"
command -v jq >/dev/null 2>&1 || _bgd_err "jq not on PATH"

[ -n "${BG_ROLE_SLUG:-}" ] || _bgd_err "BG_ROLE_SLUG is required"
[ -n "${BG_RUN_ID:-}" ]    || _bgd_err "BG_RUN_ID is required"
[ -n "${WORKTREE:-}" ]     || _bgd_err "WORKTREE is required"
# Written long-hand on purpose. `: "${BG_INPUTS_JSON:={}}"` looks like it defaults to an
# empty JSON object, but bash ends the expansion at the first `}` and assigns the single
# character `{`, which no JSON parser accepts.
[ -n "${BG_INPUTS_JSON:-}" ] || BG_INPUTS_JSON='{}'
: "${RELAY_ROLE_PATH:=}"
_bgd_presets="${BG_PRESETS_PATH:-$_bgd_root/bindings/presets.yaml}"
_bgd_launcher="${BG_LAUNCH_OVERRIDE:-$_bgd_root/scripts/bg-launch.sh}"

[ -d "$WORKTREE" ] || _bgd_err "WORKTREE '$WORKTREE' is not a directory"
[ -f "$_bgd_presets" ] || _bgd_err "presets file not found: $_bgd_presets"
[ -f "$_bgd_launcher" ] || _bgd_err "bg-launch.sh not found: $_bgd_launcher"

# --- Depth cap: a bg child must not dispatch a further bg child (spec §3.4). ---
# Runs before any directory or file is created, so a denied dispatch leaves no trace.
_bgd_depth_msg="nested bg dispatch is capped at depth 1 — this session is already a background child, and a bg child must not dispatch a further bg child. Run the work in this session, or run a nested Workflow with in-session leaves."
# Signal 1 — the exported depth marker (primary). Refuse when set and non-zero.
if [ -n "${RELAY_BG_DEPTH:-}" ] && [ "${RELAY_BG_DEPTH:-0}" != "0" ]; then
  _bgd_err "$_bgd_depth_msg"
fi
# Signal 2 — the job-state backstop. CLAUDE_JOB_DIR is exported into every Bash tool
# call of a bg session, so this fires even when the depth marker fails to inherit.
if [ -n "${CLAUDE_JOB_DIR:-}" ] && [ -f "${CLAUDE_JOB_DIR}/state.json" ]; then
  _bgd_template="$(jq -r '.template // ""' "${CLAUDE_JOB_DIR}/state.json" 2>/dev/null || echo "")"
  if [ "$_bgd_template" = "bg" ]; then
    _bgd_err "$_bgd_depth_msg"
  fi
fi

# --- Step 1: resolve the role file. Same order as acpx-dispatch.sh (spec §5). ---
if [ -n "$RELAY_ROLE_PATH" ]; then
  _bgd_role_path="$RELAY_ROLE_PATH"
elif [ -f "$_bgd_root/roles/${BG_ROLE_SLUG}.md" ]; then
  _bgd_role_path="$_bgd_root/roles/${BG_ROLE_SLUG}.md"
elif [ -f "$_bgd_root/agents/${BG_ROLE_SLUG}.md" ]; then
  _bgd_role_path="$_bgd_root/agents/${BG_ROLE_SLUG}.md"
else
  _bgd_role_path=""
fi
if [ -z "$_bgd_role_path" ] || [ ! -f "$_bgd_role_path" ]; then
  if [ -n "$RELAY_ROLE_PATH" ]; then
    _bgd_err "ROLE_FILE_MISSING: ${BG_ROLE_SLUG} (RELAY_ROLE_PATH=$RELAY_ROLE_PATH not found)"
  else
    _bgd_err "ROLE_FILE_MISSING: ${BG_ROLE_SLUG} (checked roles/ then agents/)"
  fi
fi

# --- Step 2: resolve the binding. Same bindings/presets.yaml, no new field. ---
_bgd_binding_json="$(yq -o=json ".roles.\"${BG_ROLE_SLUG}\"" "$_bgd_presets" 2>/dev/null || echo "null")"
if [ "$_bgd_binding_json" = "null" ] || [ -z "$_bgd_binding_json" ]; then
  _bgd_err "binding preset not found: $BG_ROLE_SLUG"
fi
_bgd_delegate_eligible="$(printf '%s' "$_bgd_binding_json" | jq -r '.delegate_eligible // false')"
[ "$_bgd_delegate_eligible" = "true" ] || _bgd_err "role '$BG_ROLE_SLUG' has delegate_eligible=false — bg-sessions dispatch refused"
_bgd_model="$(printf '%s' "$_bgd_binding_json" | jq -r '.modalities.claude.model // ""')"
[ -n "$_bgd_model" ] || _bgd_err "role '$BG_ROLE_SLUG' has no modalities.claude.model"
# 4.46.0 — the two category overrides. A bg-session is always a Claude leg
# (`claude --bg`), so `--fixes-model` / `--verification-model` reach it exactly as
# they reach acpx-claude. Without this the flags would resolve, print, and change
# nothing under `--engine bg-sessions`.
_bgd_category="$(printf '%s' "$_bgd_binding_json" | jq -r '.category // ""')"
case "$_bgd_category" in
  fixes)        _bgd_override="${RELAY_FIXES_MODEL:-}" ;;
  verification) _bgd_override="${RELAY_VERIFICATION_MODEL:-}" ;;
  *)            _bgd_override="" ;;
esac
if [ -n "$_bgd_override" ]; then
  echo "[relay] bg-dispatch: ${_bgd_category}-model=$_bgd_override replaces modalities.claude.model=$_bgd_model for role $BG_ROLE_SLUG" >&2
  _bgd_model="$_bgd_override"
fi
_bgd_permissions="$(printf '%s' "$_bgd_binding_json" | jq -r '.permissions // ""')"
_bgd_max_turns="$(printf '%s' "$_bgd_binding_json" | jq -r '.max_turns // 10')"

# Permission-mode mapping (docs/bg-dispatch-contract.md, ### Permission-mode mapping):
# approve-all -> auto; approve-reads or absent -> plan. No binding value selects the
# raw blanket-grant mode any more — see the contract doc for the full table and the
# note on the raw --permission-mode argument still accepted by bg-launch.sh.
case "$_bgd_permissions" in
  approve-all) _bgd_mode="auto" ;;
  approve-reads|"") _bgd_mode="plan" ;;
  *) _bgd_err "role '$BG_ROLE_SLUG' has unmapped permissions '$_bgd_permissions' (expected approve-all, approve-reads, or absent)" ;;
esac

# --- Step 3: derive the runid (spec §1.2 — one rule, one source). ---
_bgd_runid_raw="$(printf '%s' "$BG_RUN_ID" | tr '[:upper:]' '[:lower:]' | sed -E 's/^wf_//' | tr -cd 'a-z0-9')"
_bgd_runid_len=${#_bgd_runid_raw}
if [ "$_bgd_runid_len" -gt 8 ]; then
  _bgd_runid="${_bgd_runid_raw: -8}"
else
  _bgd_runid="$_bgd_runid_raw"
fi
[ "${#_bgd_runid}" -ge 4 ] || _bgd_err "BG_RUN_ID '$BG_RUN_ID' yields a runid suffix shorter than 4 characters after cleanup ('$_bgd_runid')"

# --- Step 4: build and validate the name (spec §1.2 — goal is always omitted). ---
_bgd_product="$(basename "$WORKTREE" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
[ -n "$_bgd_product" ] || _bgd_err "could not derive a product slug from WORKTREE '$WORKTREE'"
_bgd_name="${_bgd_product}-${BG_ROLE_SLUG}-${_bgd_runid}"
if ! _bgd_check_out="$(bash "$_bgd_launcher" --check-name "$_bgd_name" 2>&1)"; then
  _bgd_err "invalid session name '$_bgd_name': $_bgd_check_out"
fi

# --- Step 5: create the two directories BEFORE launch. ---
_bgd_bg_root="${HOME}/.claude/relay/bg/${_bgd_runid}"
_bgd_handoff_dir="${WORKTREE}/.relay-bg/${_bgd_runid}"
mkdir -p "$_bgd_bg_root" || _bgd_err "could not create $_bgd_bg_root"
mkdir -p "$_bgd_handoff_dir" || _bgd_err "could not create $_bgd_handoff_dir"
_bgd_handoff="${_bgd_handoff_dir}/${BG_ROLE_SLUG}.envelope"
_bgd_sidecar="${_bgd_bg_root}/${BG_ROLE_SLUG}.env"
: > "$_bgd_handoff"

# --- Step 6: write the sidecar BEFORE launch (RELAY_BG_SHORT_ID filled in after). ---
{
  printf 'RELAY_BG_NAME=%s\n' "$_bgd_name"
  printf 'RELAY_BG_SHORT_ID=\n'
  printf 'RELAY_BG_HANDOFF=%s\n' "$_bgd_handoff"
  printf 'RELAY_BG_MODEL=%s\n' "$_bgd_model"
  printf 'RELAY_BG_PERMISSION_MODE=%s\n' "$_bgd_mode"
  printf 'RELAY_BG_MAX_TURNS=%s\n' "$_bgd_max_turns"
} > "$_bgd_sidecar"

# --- Step 7: materialize the prompt — preamble (§1.4, bg-sessions variant) + role
# body, {{SLOT_*}} substitution for inputs, {{NAME}}/{{HANDOFF_FILE}}/{{TURN}} for the
# preamble's own placeholders. TURN starts at 1 (the launch prompt).
_bgd_preamble="$_bgd_here/preamble.md"
[ -f "$_bgd_preamble" ] || _bgd_err "preamble.md missing next to bg-dispatch.sh"
_bgd_prompt_file="${_bgd_handoff_dir}/${BG_ROLE_SLUG}.prompt"
# The handoff path carries the caller-supplied WORKTREE, so it can hold a sed
# metachar (| & \). Escape every replacement string before it reaches sed, or a
# path like /home/a&b/wt injects the match back and the child writes its envelope
# to a mangled path the watcher never reads — the same metachar class the slot
# pass below moved off sed for.
_bgd_sed_repl() { printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'; }
{
  sed -e "s|{{NAME}}|$(_bgd_sed_repl "$_bgd_name")|g" \
      -e "s|{{HANDOFF_FILE}}|$(_bgd_sed_repl "$_bgd_handoff")|g" \
      -e "s|{{TURN}}|1|g" \
      "$_bgd_preamble"
  printf '\n'
  cat "$_bgd_role_path"
} > "$_bgd_prompt_file"
# {{SLOT_*}} substitution for BG_INPUTS_JSON. ONE jq pass, no shell loop and no sed.
# jq's one-argument split() matches a literal string, so a value may hold any of | & \ /
# or a newline and still lands verbatim.
#
# The shell loop this replaces could not do that. It delimited its s/// with | while
# escaping only & / \, so a value holding a pipe made sed exit 1 and leave the
# placeholder in the prompt, and `IFS='=' read` cut a multi-line value at its first
# newline and read the rest as phantom keys. Neither failure stopped the dispatch.
# acpx runs the equivalent single pass in python (acpx-dispatch.sh, "Single-pass python
# substitution OUTSIDE the loop").
_bgd_subst="${_bgd_prompt_file}.subst"
if ! jq -rn --rawfile tpl "$_bgd_prompt_file" --argjson inputs "$BG_INPUTS_JSON" \
     'reduce ($inputs|to_entries[]) as $e ($tpl; split("{{SLOT_" + $e.key + "}}") | join($e.value|tostring))' \
     > "$_bgd_subst" 2>/dev/null; then
  rm -f "$_bgd_subst"
  _bgd_err "slot substitution failed: BG_INPUTS_JSON must be a JSON object of slot name -> value"
fi
mv "$_bgd_subst" "$_bgd_prompt_file"

# Every key in BG_INPUTS_JSON is now substituted, so a surviving {{SLOT_*}} means the
# caller never supplied that input. Stop here. A child launched with a literal
# {{SLOT_task}} has no task: it spends its budget and its permission mode on nothing,
# and the watcher reads whatever envelope it returns as a real answer. Nothing has been
# spawned yet, so a typed failure now costs one dispatch and no worker.
# acpx leaves such a placeholder in place; this leg deliberately does not.
if grep -q '{{SLOT_' "$_bgd_prompt_file" 2>/dev/null; then
  _bgd_err "slot substitution left $(grep -o '{{SLOT_[A-Za-z0-9_]*}}' "$_bgd_prompt_file" | sort -u | tr '\n' ' ')unfilled in the prompt — supply it in BG_INPUTS_JSON, with an empty string if the role treats it as optional"
fi

# --- Step 8: launch, one retry on LAUNCH_DENIED (spec §Failure behavior). ---
# Export the depth marker so the spawned child refuses further dispatch (Signal 1).
export RELAY_BG_DEPTH=1
_bgd_attempt=0
_bgd_short_id=""
_bgd_denied=0
while [ "$_bgd_attempt" -lt 2 ]; do
  _bgd_attempt=$((_bgd_attempt + 1))
  _bgd_out="$(cd "$WORKTREE" && bash "$_bgd_launcher" \
    --name "$_bgd_name" --model "$_bgd_model" --permission-mode "$_bgd_mode" \
    --prompt-file "$_bgd_prompt_file")"
  _bgd_rc=$?
  if [ "$_bgd_rc" -eq 0 ]; then
    _bgd_short_id="$(printf '%s\n' "$_bgd_out" | sed -nE 's/^RELAY_BG_SHORT_ID=(.*)$/\1/p')"
    _bgd_denied=0
    break
  fi
  _bgd_denied=1
done

if [ "$_bgd_denied" -eq 1 ]; then
  printf 'RELAY_BG_SIDECAR=%s\n' "$_bgd_sidecar"
  printf 'RELAY_BG_HANDOFF=%s\n' "$_bgd_handoff"
  printf 'RELAY_BG_NAME=%s\n' "$_bgd_name"
  printf 'RELAY_BG_DISPATCH=LAUNCH_DENIED\n'
  exit 1
fi

# --- Step 9: complete the sidecar with the short id, now that launch succeeded. ---
sed -i.bak "s/^RELAY_BG_SHORT_ID=.*/RELAY_BG_SHORT_ID=${_bgd_short_id}/" "$_bgd_sidecar"
rm -f "$_bgd_sidecar.bak"

printf 'RELAY_BG_SIDECAR=%s\n' "$_bgd_sidecar"
printf 'RELAY_BG_HANDOFF=%s\n' "$_bgd_handoff"
printf 'RELAY_BG_NAME=%s\n' "$_bgd_name"
printf 'RELAY_BG_SHORT_ID=%s\n' "$_bgd_short_id"
printf 'RELAY_BG_DISPATCH=OK\n'
exit 0
