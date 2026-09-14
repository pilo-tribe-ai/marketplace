#!/usr/bin/env bash
# relay: shared positional-arg validator + layered axis resolver. SOURCED by every
# command body passing ALL positionals so the extras-rejection check can actually
# see a stray arg:
#   source "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh" "$@"
# (NOT "$1" "$2" — that would make the $3/$4 extras checks dead code, since the
# sourced script's $3/$4 would never be populated.) [inferred]
# 4.12.0: per-axis resolution is flag > .claude/relay.json pin > default (spec §1.1).
# Pins pass the SAME lowercasing, enum validation, and cross-arg invariants as flags;
# an invalid pin fails loudly here at Step 0. Exports RELAY_ENGINE + RELAY_AGENT +
# RELAY_AXIS_SOURCE (flags|relay.json|default, or "<a>+<b>" when the axes differ) +
# RELAY_IN_SESSION_TIERS (0/1, default 1 as of 4.14.0 — an explicit
# `"in_session_tiers": false` is the opt-out). Returns 1 (not exit) on invalid input.
# 4.46.0: two more axes, resolved the same way — RELAY_FIXES_MODEL and
# RELAY_VERIFICATION_MODEL (flag env var > .claude/relay.json `fixes_model` /
# `verification_model` > empty, which means "keep the per-role pin"), plus
# RELAY_MODEL_SOURCE for the echo line. Both are exported even when empty.
# 4.47.0: the "default" layer is per command, not global. A caller may export
# RELAY_DEFAULT_ENGINE / RELAY_DEFAULT_AGENT before sourcing to move its own default off
# `in-session`; /relay:implement and /relay:verify export `acpx` + `claude`. Flags and
# pins still beat it, and RELAY_AXIS_SOURCE still reports `default`.
# Callers that accept a 3rd positional (only /relay:implement) set
# RELAY_ALLOW_SPEC_PATH=1 before sourcing; the three refine commands leave it unset.
_re_lc() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
# 1. lowercase flags
_relay_engine="$(_re_lc "${1:-}")"
_relay_agent="$(_re_lc "${2:-}")"
# 1b. per-axis source tracking (flags | relay.json | default)
_engine_src=""
_agent_src=""
[ -n "$_relay_engine" ] && _engine_src="flags"
[ -n "$_relay_agent" ] && _agent_src="flags"
# 1b-ii. the two model axes. These arrive as environment variables, not positionals:
# the positional list is already `engine agent [spec-path]`, and a fourth and fifth
# positional would make the extras check at step 5 unable to see a stray argument.
# A command body reads `--fixes-model` / `--verification-model` out of $ARGUMENTS and
# exports RELAY_FIXES_MODEL_FLAG / RELAY_VERIFICATION_MODEL_FLAG before it sources
# this file. Both are cleared below, so a value cannot leak into the next command.
_relay_fixes_model="$(_re_lc "${RELAY_FIXES_MODEL_FLAG:-}")"
_relay_verification_model="$(_re_lc "${RELAY_VERIFICATION_MODEL_FLAG:-}")"
_fixes_src=""
_verification_src=""
[ -n "$_relay_fixes_model" ] && _fixes_src="flags"
[ -n "$_relay_verification_model" ] && _verification_src="flags"
unset RELAY_FIXES_MODEL_FLAG RELAY_VERIFICATION_MODEL_FLAG
# 1b-iii. the per-command default axis. A command body may export RELAY_DEFAULT_ENGINE
# and RELAY_DEFAULT_AGENT before it sources this file, to change what "no flag and no
# pin" resolves to for that command. /relay:implement and /relay:verify set `acpx` +
# `claude`; every other caller leaves them unset and keeps `in-session`. Both are read
# once and cleared here, so a value cannot leak into the next command in the same shell.
_relay_def_engine="$(_re_lc "${RELAY_DEFAULT_ENGINE:-}")"
_relay_def_agent="$(_re_lc "${RELAY_DEFAULT_AGENT:-}")"
unset RELAY_DEFAULT_ENGINE RELAY_DEFAULT_AGENT
# 1c. pin fill-in from .claude/relay.json — the config belongs to the PRIMARY
# checkout, so its path is derived from git-common-dir (the worktree-preflight.sh
# idiom): relay.json is untracked per-checkout config that a fresh worktree does not
# carry, and this step may run inside one. --show-toplevel/$PWD fallback outside
# git, so behavioral tests run in a bare temp dir. resolve-tier.sh applies the same
# derivation — the two readers must land on the same file.
# One file open, one validation site, one failure contract for all three keys the
# axis layer consumes (engine, agent, in_session_tiers).
_relay_common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "$_relay_common" ]; then
  _relay_cfg="$(dirname "$_relay_common")/.claude/relay.json"
else
  _relay_cfg="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/relay.json"
fi
# 4.14.0: in-session tiers default ON. Only an explicit `"in_session_tiers": false`
# turns them off, so a repo with no .claude/relay.json gets per-role tiers.
_relay_tiers="1"
if [ -f "$_relay_cfg" ]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "[relay] error: jq is required to read .claude/relay.json" >&2; return 1
  fi
  # `jq empty` is pure syntax validation — `jq -e .` would misreport a valid
  # top-level null/false document as malformed JSON.
  if ! jq empty "$_relay_cfg" >/dev/null 2>&1; then
    # byte-identical to worktree-preflight.sh so users see one contract
    echo "[relay] error: .claude/relay.json is not valid JSON" >&2; return 1
  fi
  # Non-object roots would otherwise surface as a misleading in_session_tiers
  # type error (plus raw jq stderr from the pin reads below).
  if ! jq -e 'type == "object"' "$_relay_cfg" >/dev/null 2>&1; then
    echo "[relay] error: .claude/relay.json must be a JSON object" >&2; return 1
  fi
  if [ -z "$_relay_engine" ]; then
    _relay_pin="$(jq -r '.engine // ""' "$_relay_cfg")"
    if [ -n "$_relay_pin" ]; then
      _relay_engine="$(_re_lc "$_relay_pin")"; _engine_src="relay.json"
    fi
  fi
  if [ -z "$_relay_agent" ]; then
    _relay_pin="$(jq -r '.agent // ""' "$_relay_cfg")"
    if [ -n "$_relay_pin" ]; then
      _relay_agent="$(_re_lc "$_relay_pin")"; _agent_src="relay.json"
    fi
  fi
  # Component-2 gate: strictly boolean, default true (spec §2.3). The presence check
  # is explicit rather than `// true` because the alternative operator cannot tell an
  # absent key from a literal `false` — both take the right-hand branch — which would
  # silently ignore the opt-out.
  if ! jq -e 'if has("in_session_tiers") then (.in_session_tiers | type == "boolean") else true end' "$_relay_cfg" >/dev/null 2>&1; then
    echo "[relay] error: in_session_tiers must be a boolean in .claude/relay.json" >&2; return 1
  fi
  [ "$(jq -r '.in_session_tiers' "$_relay_cfg")" = "false" ] && _relay_tiers="0"
  if [ -z "$_relay_fixes_model" ]; then
    _relay_pin="$(jq -r '.fixes_model // ""' "$_relay_cfg")"
    if [ -n "$_relay_pin" ]; then
      _relay_fixes_model="$(_re_lc "$_relay_pin")"; _fixes_src="relay.json"
    fi
  fi
  if [ -z "$_relay_verification_model" ]; then
    _relay_pin="$(jq -r '.verification_model // ""' "$_relay_cfg")"
    if [ -n "$_relay_pin" ]; then
      _relay_verification_model="$(_re_lc "$_relay_pin")"; _verification_src="relay.json"
    fi
  fi
fi
# 1e. validate the two model axes. An empty value is not a failure: it means "no
# override", and every categorized role keeps the default pinned beside it in
# bindings/presets.yaml. A NON-EMPTY value must name one of three models, so a typo
# fails here at Step 0 rather than reaching a dispatch as an unknown model id.
#
# The enum is NARROWER than the flat per-role ladder, and that is deliberate. `haiku`
# is not offered: neither category holds a mechanical role, and a critic or a fixer on
# haiku is a downgrade nobody asks for on purpose. `inherit` is not offered either: it
# is a per-role property meaning "this role must track the session model", so a flag
# that set it would erase the property rather than choose a model. `fable` is offered
# here although no role pins it, because a flag is a per-run choice that a person makes
# and can undo — the staleness argument that keeps a frontier name out of the static
# pins does not reach it.
_re_check_model() { # $1 = value, $2 = axis name, $3 = source
  [ -z "$1" ] && return 0
  case "$1" in
    sonnet | opus | fable) return 0 ;;
  esac
  echo "[relay] error: invalid $2 '$1' (expected: sonnet | opus | fable)$(_re_sfx "$3")" >&2
  return 1
}
# 2. defaults — a DERIVED agent default inherits the source of the engine that
# derived it (spec §1.3), so a lone `"engine": "acpx"` pin yields agent=hybrid
# with _agent_src=relay.json.
[ -z "$_relay_engine" ] && { _relay_engine="${_relay_def_engine:-in-session}"; _engine_src="default"; }
if [ -z "$_relay_agent" ]; then
  # A command default agent applies ONLY when the engine also came from the default.
  # An explicit `--engine smart-routing` must still derive its own agent from the
  # table below, or /relay:implement would hand it agent=claude and fail the
  # smart-routing invariant on a flag the user typed correctly.
  if [ "$_engine_src" = "default" ] && [ -n "$_relay_def_agent" ]; then
    _relay_agent="$_relay_def_agent"
  else
    case "$_relay_engine" in
      # acpx defaults to `hybrid` — the per-role engine pick from
      # bindings/presets.yaml (reasoning roles -> claude, coding roles -> codex).
      # `claude`/`codex` are explicit uniform-engine overrides.
      acpx) _relay_agent="hybrid" ;;
      # smart-routing uses its own router logic; default agent matches the engine name.
      smart-routing) _relay_agent="smart-routing" ;;
      *)    _relay_agent="claude" ;;
    esac
  fi
  _agent_src="$_engine_src"
fi
# 3. validate enums — a pin-sourced failure names its origin (the enum IS the
# type check for wrong-typed pin values)
_re_sfx() {
  [ "$1" = "relay.json" ] && { printf '%s' " (from .claude/relay.json pin)"; return 0; }
  # A command that exports a typo'd RELAY_DEFAULT_* must not read as a user typo.
  [ "$1" = "default" ] && [ -n "$_relay_def_engine$_relay_def_agent" ] && \
    printf '%s' " (from this command's built-in default)"
  return 0
}
case "$_relay_engine" in in-session|acpx|smart-routing|bg-sessions|session-tree) ;; *)
  echo "[relay] error: invalid engine '$_relay_engine' (expected: in-session | acpx | smart-routing | bg-sessions | session-tree)$(_re_sfx "$_engine_src")" >&2; return 1 ;;
esac
case "$_relay_agent" in claude|codex|hybrid|opencode|smart-routing) ;; *)
  echo "[relay] error: invalid agent '$_relay_agent' (expected: claude | codex | hybrid | opencode | smart-routing)$(_re_sfx "$_agent_src")" >&2; return 1 ;;
esac
_re_check_model "$_relay_fixes_model" "fixes-model" "$_fixes_src" || return 1
_re_check_model "$_relay_verification_model" "verification-model" "$_verification_src" || return 1
# 4. cross-arg invariants — clashes across sources fail loudly, never silently
# demote; one hint line per pinned participating axis (spec §1.2). [inferred]
_re_pin_hints() { # $1 = suggested --engine value, $2 = suggested --agent value
  [ "$_engine_src" = "relay.json" ] && \
    echo "[relay] hint: engine came from .claude/relay.json — pass --engine $1 or change the pin" >&2
  [ "$_agent_src" = "relay.json" ] && \
    echo "[relay] hint: agent came from .claude/relay.json — pass --agent $2 or change the pin" >&2
  return 0
}
# in-session requires agent=claude (no external delegation)
if [ "$_relay_engine" = "in-session" ] && [ "$_relay_agent" != "claude" ]; then
  echo "[relay] error: engine=in-session requires agent=claude (got '$_relay_agent')" >&2
  _re_pin_hints "acpx" "claude"
  return 1
fi
# bg-sessions requires agent=claude (no codex leg) — spec §Deliverable 2, Axis
if [ "$_relay_engine" = "bg-sessions" ] && [ "$_relay_agent" != "claude" ]; then
  echo "[relay] error: engine=bg-sessions requires agent=claude (got '$_relay_agent')" >&2
  _re_pin_hints "acpx" "claude"
  return 1
fi
# session-tree requires agent=claude (no codex leg) — spec §Deliverable 3, Doctrine
if [ "$_relay_engine" = "session-tree" ] && [ "$_relay_agent" != "claude" ]; then
  echo "[relay] error: engine=session-tree requires agent=claude (got '$_relay_agent')" >&2
  _re_pin_hints "acpx" "claude"
  return 1
fi
# smart-routing engine cannot be combined with explicit worker agents (claude/codex/opencode);
# hybrid is allowed (it overrides dynamic routing with the static per-role presets.yaml split);
# agent=smart-routing is the default when engine=smart-routing.
if [ "$_relay_engine" = "smart-routing" ] && \
   [ "$_relay_agent" != "smart-routing" ] && [ "$_relay_agent" != "hybrid" ]; then
  echo "[relay] error: engine=smart-routing cannot combine with agent='$_relay_agent' (use agent=smart-routing, agent=hybrid, or omit)" >&2
  _re_pin_hints "acpx" "smart-routing"
  return 1
fi
# 5. reject extras
if [ "${RELAY_ALLOW_SPEC_PATH:-0}" = "1" ]; then
  [ -n "${4:-}" ] && { echo "[relay] error: too many arguments (expected at most engine agent spec-path)" >&2; return 1; }
else
  [ -n "${3:-}" ] && { echo "[relay] error: too many arguments (expected at most engine agent)" >&2; return 1; }
fi
export RELAY_ENGINE="$_relay_engine"
export RELAY_AGENT="$_relay_agent"
if [ "$_engine_src" = "$_agent_src" ]; then
  export RELAY_AXIS_SOURCE="$_engine_src"
else
  export RELAY_AXIS_SOURCE="${_engine_src}+${_agent_src}"
fi
export RELAY_IN_SESSION_TIERS="$_relay_tiers"
# The two model axes are exported ALWAYS, empty included. resolve-tier.sh and
# acpx-dispatch.sh read "set but empty" as "the caller decided there is no override",
# which stops them from re-reading .claude/relay.json and reaching a different answer
# than the command body already printed.
export RELAY_FIXES_MODEL="$_relay_fixes_model"
export RELAY_VERIFICATION_MODEL="$_relay_verification_model"
_re_src_word() { [ -n "$1" ] && printf '%s' "$2" || printf '%s' "presets"; }
export RELAY_MODEL_SOURCE="fixes=$(_re_src_word "$_relay_fixes_model" "$_fixes_src") verification=$(_re_src_word "$_relay_verification_model" "$_verification_src")"
return 0
