#!/usr/bin/env bash
# relay: the single resolution site for in-session leaf tiers (spec §2.3, as
# amended for 4.14.0).
#
# Reads the flat per-role `model:`/`effort:` pair from bindings/presets.yaml and
# prints the (model, effort) each in-session `agent()` node must be generated with.
# EXECUTED, not sourced — the coordinator runs it and transcribes the output into
# the Workflow script it generates. Before 4.14.0 this table was hand-derived from a
# prose paragraph in each command body, which made drift invisible; there is now one
# site, and it reads the bindings file directly.
#
# Usage:
#   resolve-tier.sh --all            # table for every role (the normal call)
#   resolve-tier.sh <role-slug>      # one role
#   resolve-tier.sh watcher          # the delegate-and-watch outer-node pin
#
# Honors RELAY_IN_SESSION_TIERS (exported by parse-engine-agent.sh; must be 0 or 1 —
# any other value fails loudly rather than silently enabling tiers). When the
# variable is UNSET, the gate is read straight from the PRIMARY checkout's
# .claude/relay.json using the same rule parse-engine-agent.sh applies (default ON;
# only an explicit `"in_session_tiers": false` opts out), so this script is correct
# standalone — which /relay:diagnose relies on, having no Step 0 axis resolution of
# its own — and correct after Step 0.5 has entered a worktree: relay.json is
# untracked per-checkout config that a fresh worktree does not carry, so the path is
# derived from git-common-dir, never from the current worktree's own toplevel.
# tests/unit/skill-structure/test_resolve_tier.sh pins the two readers to agree.
#
# 4.46.0: two category overrides ride the same resolution. A role may carry
# `category: fixes` or `category: verification` in bindings/presets.yaml.
# RELAY_FIXES_MODEL and RELAY_VERIFICATION_MODEL (exported by parse-engine-agent.sh
# from `--fixes-model` / `--verification-model`, empty when the caller passed
# neither) replace the flat `model:` of every role of that category. When NEITHER
# variable is set, the pins `fixes_model` and `verification_model` in
# `.claude/relay.json` are read instead, so a standalone call is correct too. An
# override never changes `effort`, and the tiers gate still wins: with tiers OFF
# every row prints `inherit` and the header says the overrides reached nothing.
#
# `model=inherit` means: OMIT `opts.model` so the node inherits the session model.
# `opts.effort` is still applied on an inherit row — the two axes are independent,
# and the never-downshift roles want pinned-high effort on whatever model they run.
# When tiers are OFF, every row (the watcher line included) prints `inherit` and
# the caller sets neither opt.
#
# `watcher` is a NODE-KIND constant, not a role: the delegate-and-watch outer
# `agent()` node does the same job whatever role it delegates, so it takes one
# pinned pair instead of 24 presets.yaml rows. Rationale lives in
# skills/delegate-and-watch/SKILL.md § Watcher tier. Same gate as every role row.
#
# Exit codes: 0 ok (including -h/--help, answered before any config or bindings
# I/O) | 1 usage/unknown role | 2 bindings or .claude/relay.json
# unreadable/invalid, or an invalid RELAY_IN_SESSION_TIERS value.
set -uo pipefail

# Argument triage FIRST: help and usage errors must not depend on config state —
# `resolve-tier.sh --help` has to keep working precisely when relay.json is broken.
_rt_usage="usage: resolve-tier.sh --all | resolve-tier.sh <role-slug> | resolve-tier.sh watcher"
case "${1:-}" in
  "")
    echo "$_rt_usage" >&2; exit 1
    ;;
  -h | --help)
    echo "$_rt_usage"; exit 0
    ;;
  --all | watcher)
    : ;;
  -*)
    echo "[relay] error: unknown flag '$1' (expected --all or a role slug)" >&2; exit 1
    ;;
esac

_rt_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
_rt_presets="$_rt_root/bindings/presets.yaml"

if [ ! -r "$_rt_presets" ]; then
  echo "[relay] error: cannot read $_rt_presets" >&2; exit 2
fi

# delegate-and-watch outer-node pin (node-kind constant — see header comment).
_rt_watcher_model="sonnet"
_rt_watcher_effort="low"

# Config path, resolved ONCE for every axis below. It belongs to the PRIMARY
# checkout: derive it from git-common-dir (the worktree-preflight.sh idiom) so a Step
# 0.5 worktree entry cannot silently drop a pin that lives untracked in the launch
# repo. --show-toplevel/$PWD fallback outside git. Before 4.46.0 this sat inside the
# gate's else-branch, which left the path unset whenever RELAY_IN_SESSION_TIERS was
# exported — a second axis reading it there would have found no file and silently
# resolved to no override.
_rt_common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "$_rt_common" ]; then
  _rt_cfg="$(dirname "$_rt_common")/.claude/relay.json"
else
  _rt_cfg="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/relay.json"
fi
# One validation site for the file, shared by every axis. Runs only when some axis
# must actually read the file, so a broken relay.json still cannot break a run whose
# every axis was already decided by an exported variable.
_rt_cfg_checked=0
_rt_need_cfg() { # rc 0 = the file exists and is valid; rc 1 = there is no file
  [ -f "$_rt_cfg" ] || return 1
  [ "$_rt_cfg_checked" = "1" ] && return 0
  if ! command -v jq >/dev/null 2>&1; then
    echo "[relay] error: jq is required to read .claude/relay.json" >&2; exit 2
  fi
  # `jq empty` is pure syntax validation — `jq -e .` would misreport a valid
  # top-level null/false document as malformed JSON.
  if ! jq empty "$_rt_cfg" >/dev/null 2>&1; then
    echo "[relay] error: .claude/relay.json is not valid JSON" >&2; exit 2
  fi
  if ! jq -e 'type == "object"' "$_rt_cfg" >/dev/null 2>&1; then
    echo "[relay] error: .claude/relay.json must be a JSON object" >&2; exit 2
  fi
  _rt_cfg_checked=1
  return 0
}

_rt_gate_src=""
if [ -n "${RELAY_IN_SESSION_TIERS:-}" ]; then
  case "$RELAY_IN_SESSION_TIERS" in
    0 | 1) _rt_tiers="$RELAY_IN_SESSION_TIERS" ;;
    *)
      # `false`/`off`/garbage must not silently mean ON — the JSON key is strictly
      # validated, and the env channel gets the same fail-loud contract.
      echo "[relay] error: RELAY_IN_SESSION_TIERS must be 0 or 1 (got '$RELAY_IN_SESSION_TIERS')" >&2; exit 2
      ;;
  esac
  _rt_gate_src="RELAY_IN_SESSION_TIERS=0 in the environment"
else
  # Standalone fallback — same rule as parse-engine-agent.sh step 1c.
  _rt_tiers="1"
  if _rt_need_cfg; then
    if ! jq -e 'if has("in_session_tiers") then (.in_session_tiers | type == "boolean") else true end' "$_rt_cfg" >/dev/null 2>&1; then
      echo "[relay] error: in_session_tiers must be a boolean in .claude/relay.json" >&2; exit 2
    fi
    [ "$(jq -r '.in_session_tiers' "$_rt_cfg")" = "false" ] && _rt_tiers="0"
  fi
  _rt_gate_src="in_session_tiers: false in .claude/relay.json"
fi

# The two category overrides. A role in bindings/presets.yaml may carry
# `category: fixes` or `category: verification`; an override replaces the flat
# `model:` of every role of that category, and touches no other role and no effort.
# Same layering as the gate above: the exported variable wins when it is SET (empty
# included, which means the caller decided there is no override), and the config is
# read only when the variable is unset, so a standalone call is still correct.
_rt_fixes=""
_rt_verification=""
_rt_cat_src="flag"
if [ "${RELAY_FIXES_MODEL+set}" = "set" ] || [ "${RELAY_VERIFICATION_MODEL+set}" = "set" ]; then
  _rt_fixes="${RELAY_FIXES_MODEL:-}"
  _rt_verification="${RELAY_VERIFICATION_MODEL:-}"
else
  _rt_cat_src=".claude/relay.json"
  if _rt_need_cfg; then
    # tostring before downcasing: a non-string pin (a number, true, an object) must
    # reach the enum check as text and be named there, not abort jq with a type error.
    _rt_fixes="$(jq -r '(.fixes_model // "") | tostring | ascii_downcase' "$_rt_cfg")"
    _rt_verification="$(jq -r '(.verification_model // "") | tostring | ascii_downcase' "$_rt_cfg")"
  fi
fi
# A non-empty value must name one of the three models the two flags offer. The enum is
# narrower than the per-role ladder on purpose — see parse-engine-agent.sh step 1e for
# why `haiku` and `inherit` are absent. The two readers must agree, so the list here is
# the same list. An unknown value is rejected, never ignored: silently keeping the pin
# would report a model the run did not use.
for _rt_pair in "fixes:$_rt_fixes" "verification:$_rt_verification"; do
  _rt_axis="${_rt_pair%%:*}"; _rt_val="${_rt_pair#*:}"
  [ -z "$_rt_val" ] && continue
  case "$_rt_val" in
    sonnet | opus | fable) ;;
    *)
      echo "[relay] error: invalid ${_rt_axis}-model '$_rt_val' from $_rt_cat_src (expected: sonnet | opus | fable)" >&2; exit 2
      ;;
  esac
done

# Rewrite the model column of every row whose category carries an override. Rows
# arrive as `slug model effort category`; the category column is dropped here, so
# every downstream consumer keeps reading three fields.
_rt_categorized() {
  awk -v fx="$_rt_fixes" -v vf="$_rt_verification" '
    { m = $2
      if ($4 == "fixes"        && fx != "") m = fx
      if ($4 == "verification" && vf != "") m = vf
      print $1, m, $3 }'
}

# Header source word for a category axis: a set value came from _rt_cat_src (a flag
# or the .claude/relay.json pin); an empty value fell back to the per-role presets.
# Mirrors parse-engine-agent.sh:_re_src_word, minus the per-call source argument.
_rt_src_word() { [ -n "$1" ] && printf '%s' "$_rt_cat_src" || printf '%s' presets; }

# One OFF-mode mapping for every output path: the watcher pair degrades to
# inherit/- and table rows are rewritten by _rt_effective. (The pinned constants
# above stay literal so the source of truth remains greppable.)
if [ "$_rt_tiers" = "0" ]; then
  _rt_watcher_model="inherit"
  _rt_watcher_effort="-"
fi
_rt_effective() {
  if [ "$_rt_tiers" = "0" ]; then awk '{ print $1, "inherit", "-" }'; else cat; fi
}

# Extract the flat (slug, model, effort) triples. awk rather than yq/PyYAML because
# this script runs in-session in arbitrary user repos, where relay's only hard deps
# are POSIX tools (+ jq when a config exists) — yq is required only on the acpx path.
# The awk is scoped to the `roles:` section (a new top-level map cannot inject rows)
# and anchored on indentation: flat fields sit at exactly four spaces under a
# two-space role key; the per-engine `modalities` entries sit deeper. A role whose
# key line is malformed (trailing comment, bad slug charset) or that misses either
# flat field is DROPPED — never attributed to a neighboring role — and the
# behavioral suite pins `--all` against a real YAML parse of every role, so a drop
# cannot land silently.
_rt_table() {
  awk '
    BEGIN                      { c = "-" }
    /^roles:[[:space:]]*$/     { inroles = 1; next }
    /^[a-z][a-z0-9_-]*:/       { inroles = 0; next }
    !inroles                   { next }
    /^  [a-z][a-z0-9-]*:[[:space:]]*$/ {
      if (cur != "" && m != "" && e != "") printf "%s %s %s %s\n", cur, m, e, c
      cur = $1; sub(/:$/, "", cur); m = ""; e = ""; c = "-"; next
    }
    /^  [^ #]/ {
      # Two-space-indented but not a clean role key: flush the completed previous
      # role and stop capturing, so this entry
      # cannot overwrite its neighbor with misattributed model/effort lines.
      if (cur != "" && m != "" && e != "") printf "%s %s %s %s\n", cur, m, e, c
      cur = ""; m = ""; e = ""; c = "-"; next
    }
    cur != "" && /^    model:[[:space:]]/    { m = $2; next }
    cur != "" && /^    effort:[[:space:]]/   { e = $2; next }
    cur != "" && /^    category:[[:space:]]/ { c = $2; next }
    END { if (cur != "" && m != "" && e != "") printf "%s %s %s %s\n", cur, m, e, c }
  ' "$_rt_presets"
}

_rt_emit_header() {
  if [ "$_rt_tiers" = "0" ]; then
    echo "[relay] in-session tiers: OFF ($_rt_gate_src)"
    echo "[relay] every in-session agent() node inherits the session model — set no opts.model and no opts.effort."
  else
    echo "[relay] in-session tiers: ON"
    echo "[relay] set opts.model/opts.effort per the rows below; model=inherit means OMIT opts.model (keep opts.effort)."
  fi
  echo "[relay] watcher (delegate-and-watch outer node): model=$_rt_watcher_model effort=$_rt_watcher_effort — the inner worker's model still comes from modalities.* at acpx dispatch time."
  # State both category axes on every run, override or not. A flag that reached no
  # row must be visible in the same block that shows the rows it did not change.
  # A set value names its source; an empty value fell back to the per-role presets.
  echo "[relay] fixes-model: ${_rt_fixes:-<per-role pin>} (source: $(_rt_src_word "$_rt_fixes")) — roles with category: fixes"
  echo "[relay] verification-model: ${_rt_verification:-<per-role pin>} (source: $(_rt_src_word "$_rt_verification")) — roles with category: verification"
  if [ "$_rt_tiers" = "0" ] && { [ -n "$_rt_fixes" ] || [ -n "$_rt_verification" ]; }; then
    echo "[relay] warning: in-session tiers are OFF, so both model overrides above reach no in-session row. Remove \"in_session_tiers\": false to apply them."
  fi
}

case "$1" in
  --all)
    _rt_emit_header
    printf '\n%-28s %-8s %s\n' "role" "model" "effort"
    _rt_table | _rt_categorized | _rt_effective | while read -r slug model effort; do
      printf '%-28s %-8s %s\n' "$slug" "$model" "$effort"
    done
    ;;
  watcher)
    echo "model=$_rt_watcher_model effort=$_rt_watcher_effort"
    ;;
  *)
    _rt_row="$(_rt_table | awk -v want="$1" '$1 == want { print; exit }')"
    if [ -z "$_rt_row" ]; then
      echo "[relay] error: unknown role '$1' (no flat model/effort row under roles: in bindings/presets.yaml)" >&2; exit 1
    fi
    echo "$_rt_row" | _rt_categorized | _rt_effective | awk '{ printf "model=%s effort=%s\n", $2, $3 }'
    ;;
esac
