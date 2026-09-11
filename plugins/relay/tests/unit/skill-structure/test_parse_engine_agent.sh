#!/usr/bin/env bash
# Behavioral suite for scripts/parse-engine-agent.sh. Sources the script with ALL
# positionals via "$@" — matching the real command call sites — so the extras-rejection
# checks ($3/$4) are LIVE, not dead code. Exits non-zero on any failed expectation.
#
# Hermeticity (4.12.0, tightened 4.14.0): the script reads .claude/relay.json from
# the primary checkout via git-common-dir (or $PWD outside git). Every check therefore
# runs in an explicit cwd that is its OWN scratch git repo — without `git init`, a
# TMPDIR that happens to sit inside some checkout would make every case silently read
# THAT repo's .claude/relay.json. _check uses a guaranteed-pinless scratch repo;
# _check_in / _check_err take an explicit cwd for the pin cases.
set -u
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$_here/../../../scripts/parse-engine-agent.sh"
_fail=0
_scratch="$(mktemp -d)"
trap 'rm -rf "$_scratch"' EXIT
_pinless="$_scratch/pinless"
mkdir -p "$_pinless"
git init -q "$_pinless" >/dev/null 2>&1

# helper: run a sourcing in a clean subshell at an explicit cwd with the given env +
# positionals; capture rc, RELAY_ENGINE, RELAY_AGENT, RELAY_AXIS_SOURCE,
# RELAY_IN_SESSION_TIERS and compare. Pass "" for exp_src/exp_tiers to skip that check.
_check_in() {
  local cwd="$1"; shift
  local desc="$1"; shift
  local exp_rc="$1"; shift
  local exp_eng="$1"; shift
  local exp_agent="$1"; shift
  local exp_src="$1"; shift
  local exp_tiers="$1"; shift
  local env_prefix="$1"; shift
  local out rc eng agent src tiers
  out="$(env -i HOME="$HOME" PATH="$PATH" bash -c "
    cd '$cwd'
    ${env_prefix}
    unset RELAY_ENGINE RELAY_AGENT RELAY_AXIS_SOURCE RELAY_IN_SESSION_TIERS
    source '$SCRIPT' \"\$@\" >/dev/null 2>&1
    rc=\$?
    printf '%s|%s|%s|%s|%s' \"\$rc\" \"\${RELAY_ENGINE:-}\" \"\${RELAY_AGENT:-}\" \"\${RELAY_AXIS_SOURCE:-}\" \"\${RELAY_IN_SESSION_TIERS:-}\"
  " _ "$@")"
  rc="${out%%|*}"; out="${out#*|}"
  eng="${out%%|*}"; out="${out#*|}"
  agent="${out%%|*}"; out="${out#*|}"
  src="${out%%|*}"; tiers="${out#*|}"
  if [ "$rc" != "$exp_rc" ]; then
    echo "FAIL: $desc — rc=$rc expected $exp_rc"; _fail=1; return
  fi
  if [ "$exp_rc" = "0" ]; then
    if [ "$eng" != "$exp_eng" ] || [ "$agent" != "$exp_agent" ]; then
      echo "FAIL: $desc — got $eng/$agent expected $exp_eng/$exp_agent"; _fail=1; return
    fi
    if [ -n "$exp_src" ] && [ "$src" != "$exp_src" ]; then
      echo "FAIL: $desc — source=$src expected $exp_src"; _fail=1; return
    fi
    if [ -n "$exp_tiers" ] && [ "$tiers" != "$exp_tiers" ]; then
      echo "FAIL: $desc — tiers=$tiers expected $exp_tiers"; _fail=1; return
    fi
  fi
  echo "ok: $desc"
}

# default: hermetic pinless non-git cwd
_check() { _check_in "$_pinless" "$@"; }

# helper: assert rc + a stderr needle (error/hint contract checks)
_check_err() {
  local cwd="$1"; shift
  local desc="$1"; shift
  local exp_rc="$1"; shift
  local needle="$1"; shift
  local out rc
  out="$(env -i HOME="$HOME" PATH="$PATH" bash -c "
    cd '$cwd'
    source '$SCRIPT' \"\$@\" 2>&1 >/dev/null
  " _ "$@")"
  rc=$?
  if [ "$rc" != "$exp_rc" ]; then
    echo "FAIL: $desc — rc=$rc expected $exp_rc"; _fail=1; return
  fi
  case "$out" in
    *"$needle"*) echo "ok: $desc" ;;
    *) echo "FAIL: $desc — stderr missing '$needle' (got: $out)"; _fail=1 ;;
  esac
}

# helper: make a scratch git repo carrying a .claude/relay.json with the given body
_pin_dir() {
  local name="$1" json="$2" d
  d="$_scratch/$name"
  mkdir -p "$d/.claude"
  git init -q "$d" >/dev/null 2>&1
  printf '%s' "$json" > "$d/.claude/relay.json"
  printf '%s' "$d"
}

# ---- pre-4.12.0 assertions (unchanged expectations; sources now asserted too) ----
_check "no args defaults" 0 in-session claude default 1 ""
_check "acpx defaults agent hybrid" 0 acpx hybrid flags 1 "" acpx
_check "acpx claude ok" 0 acpx claude flags 1 "" acpx claude
_check "acpx codex ok" 0 acpx codex flags 1 "" acpx codex
_check "acpx hybrid ok" 0 acpx hybrid flags 1 "" acpx hybrid
_check "in-session codex rejected" 1 "" "" "" "" "" in-session codex
_check "in-session hybrid rejected" 1 "" "" "" "" "" in-session hybrid
_check "bogus engine rejected" 1 "" "" "" "" "" bogus
_check "bogus agent rejected" 1 "" "" "" "" "" acpx bogus
_check "acpx opencode ok" 0 acpx opencode flags 1 "" acpx opencode
_check "smart-routing defaults agent smart-routing" 0 smart-routing smart-routing flags 1 "" smart-routing
_check "smart-routing agent explicit ok" 0 smart-routing smart-routing flags 1 "" smart-routing smart-routing
_check "smart-routing claude rejected" 1 "" "" "" "" "" smart-routing claude
_check "smart-routing codex rejected" 1 "" "" "" "" "" smart-routing codex
_check "smart-routing opencode rejected" 1 "" "" "" "" "" smart-routing opencode
_check "smart-routing hybrid ok" 0 smart-routing hybrid flags 1 "" smart-routing hybrid
_check "acpx smart-routing agent ok" 0 acpx smart-routing flags 1 "" acpx smart-routing
_check "in-session smart-routing agent rejected" 1 "" "" "" "" "" in-session smart-routing
_check "extra 3rd positional rejected" 1 "" "" "" "" "" in-session claude extra
_check "spec-path allowed" 0 in-session claude flags 1 "export RELAY_ALLOW_SPEC_PATH=1;" in-session claude /tmp/spec.md
_check "4th positional rejected" 1 "" "" "" "" "export RELAY_ALLOW_SPEC_PATH=1;" in-session claude /tmp/spec.md extra

# ---- 4.12.0: pin fill-in + provenance (spec §1.1–§1.3, §8.2) ----
# pin resolves when flags empty; derived agent inherits the engine's pin source
_d="$(_pin_dir pin-engine '{"engine": "acpx"}')"
_check_in "$_d" "engine pin resolves, source relay.json" 0 acpx hybrid relay.json 1 ""
# flag beats pin
_d="$(_pin_dir flag-beats-pin '{"engine": "acpx"}')"
_check_in "$_d" "flag beats pin" 0 in-session claude flags 1 "" in-session claude
# mixed flags+relay.json (engine flag, agent pin)
_d="$(_pin_dir mixed-fp '{"agent": "codex"}')"
_check_in "$_d" "mixed flags+relay.json" 0 acpx codex flags+relay.json 1 "" acpx
# mixed relay.json+flags (engine pin, agent flag)
_d="$(_pin_dir mixed-pf '{"engine": "acpx"}')"
_check_in "$_d" "mixed relay.json+flags" 0 acpx codex relay.json+flags 1 "" "" codex
# both pinned
_d="$(_pin_dir pin-both '{"engine": "acpx", "agent": "codex"}')"
_check_in "$_d" "both axes pinned" 0 acpx codex relay.json 1 ""
# no flag, no pin -> default (hermetic dir; also asserted in the legacy block)
_check "no flag no pin source default" 0 in-session claude default 1 ""
# --agent claude alone, no pins -> default+flags [inferred]
_check "agent claude alone default+flags" 0 in-session claude default+flags 1 "" "" claude
# absent file -> defaults, tiers ON (4.14.0: only an explicit false opts out)
_check "absent relay.json defaults tiers on" 0 in-session claude default 1 ""
# invalid pin enum -> rc 1, stderr names the pin origin
_d="$(_pin_dir pin-bogus '{"engine": "bogus"}')"
_check_err "$_d" "invalid pin enum names relay.json" 1 "(from .claude/relay.json pin)"
# invalid JSON -> rc 1 with the exact worktree-preflight-aligned message
_d="$_scratch/bad-json"; mkdir -p "$_d/.claude"; git init -q "$_d" >/dev/null 2>&1
printf '{engine' > "$_d/.claude/relay.json"
_check_err "$_d" "invalid JSON exact message" 1 "[relay] error: .claude/relay.json is not valid JSON"
# non-object roots get their own diagnosis, and a top-level null/false document is
# valid JSON (jq empty), not a syntax error — 4.14.0 regression guards.
_d="$(_pin_dir array-root '[]')"
_check_err "$_d" "array root names the shape" 1 ".claude/relay.json must be a JSON object"
_d="$(_pin_dir null-root 'null')"
_check_err "$_d" "null root names the shape" 1 ".claude/relay.json must be a JSON object"
# non-boolean in_session_tiers -> rc 1
_d="$(_pin_dir tiers-string '{"in_session_tiers": "yes"}')"
_check_err "$_d" "non-boolean in_session_tiers rejected" 1 "in_session_tiers must be a boolean"
# explicit null is present-and-non-boolean (has() semantics) — rejected loudly,
# unlike 4.13.0's `// false` read which silently treated it as OFF.
_d="$(_pin_dir tiers-null '{"in_session_tiers": null}')"
_check_err "$_d" "null in_session_tiers rejected" 1 "in_session_tiers must be a boolean"
# in_session_tiers: true -> RELAY_IN_SESSION_TIERS=1
_d="$(_pin_dir tiers-on '{"in_session_tiers": true}')"
_check_in "$_d" "tiers pin exports 1" 0 in-session claude default 1 ""
# in_session_tiers: false -> RELAY_IN_SESSION_TIERS=0. Regression guard: `// true`
# cannot distinguish an absent key from a literal false, so a `//`-based read would
# silently ignore this opt-out.
_d="$(_pin_dir tiers-off '{"in_session_tiers": false}')"
_check_in "$_d" "explicit false opts out" 0 in-session claude default 0 ""
# an unrelated pin must not disturb the tiers default (engine in-session so this
# case is not a duplicate of "engine pin resolves" above — distinct expectation tuple)
_d="$(_pin_dir tiers-absent '{"engine": "in-session"}')"
_check_in "$_d" "unrelated pin keeps tiers on" 0 in-session claude relay.json 1 ""
# lone non-claude agent pin -> invariant fails loudly with the pin-origin hint
_d="$(_pin_dir lone-agent '{"agent": "hybrid"}')"
_check_err "$_d" "lone agent pin invariant hint" 1 "agent came from .claude/relay.json"
# pinned engine in-session + flag agent codex -> hint names the ENGINE pin [inferred]
_d="$(_pin_dir pin-eng-clash '{"engine": "in-session"}')"
_check_err "$_d" "engine pin clash hints engine" 1 "engine came from .claude/relay.json" "" codex
# smart-routing flag + pinned worker agent -> rejection carries the agent hint [inferred]
_d="$(_pin_dir sr-agent-pin '{"agent": "codex"}')"
_check_err "$_d" "smart-routing + agent pin hint" 1 "agent came from .claude/relay.json" smart-routing

# ---- 4.30.0: bg-sessions engine (spec §Deliverable 2, Axis) ----
_check "bg-sessions with no agent" 0 bg-sessions claude flags 1 "" bg-sessions
_check "bg-sessions claude ok" 0 bg-sessions claude flags 1 "" bg-sessions claude
_check_err "$_pinless" "bg-sessions codex rejected" 1 "engine=bg-sessions requires agent=claude" bg-sessions codex
_check "bg-sessions hybrid rejected" 1 "" "" "" "" "" bg-sessions hybrid
_check "BG-SESSIONS uppercased is lowercased first" 0 bg-sessions claude flags 1 "" BG-SESSIONS
_d="$(_pin_dir pin-bg-sessions '{"engine": "bg-sessions"}')"
_check_in "$_d" "bg-sessions pin resolves, source relay.json" 0 bg-sessions claude relay.json 1 ""
_d="$(_pin_dir pin-bg-sessions-codex '{"engine": "bg-sessions", "agent": "codex"}')"
_check_err "$_d" "bg-sessions+codex pin names both pin hints" 1 "engine came from .claude/relay.json"
_check_err "$_d" "bg-sessions+codex pin names agent pin hint too" 1 "agent came from .claude/relay.json"
_check_err "$_pinless" "invalid engine names bg-sessions in the expected list" 1 "bg-sessions" bogus
_check "bg-sessions claude extra rejected" 1 "" "" "" "" "" bg-sessions claude extra

# ---- 4.30.0: session-tree engine (spec §Deliverable 3, Doctrine) ----
_check "session-tree with no agent" 0 session-tree claude flags 1 "" session-tree
_check "session-tree claude ok" 0 session-tree claude flags 1 "" session-tree claude
_check_err "$_pinless" "session-tree codex rejected" 1 "engine=session-tree requires agent=claude" session-tree codex
_check "session-tree hybrid rejected" 1 "" "" "" "" "" session-tree hybrid
_check "SESSION-TREE uppercased is lowercased first" 0 session-tree claude flags 1 "" SESSION-TREE
_d="$(_pin_dir pin-session-tree '{"engine": "session-tree"}')"
_check_in "$_d" "session-tree pin resolves, source relay.json" 0 session-tree claude relay.json 1 ""
_d="$(_pin_dir pin-session-tree-codex '{"engine": "session-tree", "agent": "codex"}')"
_check_err "$_d" "session-tree+codex pin names both pin hints" 1 "engine came from .claude/relay.json"
_check_err "$_d" "session-tree+codex pin names agent pin hint too" 1 "agent came from .claude/relay.json"
_check_err "$_pinless" "invalid engine names session-tree in the expected list" 1 "session-tree" bogus
_check "session-tree claude extra rejected" 1 "" "" "" "" "" session-tree claude extra

# ---- 4.46.0: the two model axes (--fixes-model / --verification-model) ----
# These ride environment variables, not positionals, so they need their own reader.
_check_models() { # cwd, desc, exp_rc, exp_fixes, exp_verification, exp_src, env_prefix, positionals...
  local cwd="$1"; shift
  local desc="$1"; shift
  local exp_rc="$1"; shift
  local exp_fx="$1"; shift
  local exp_vf="$1"; shift
  local exp_src="$1"; shift
  local env_prefix="$1"; shift
  local out rc fx vf src
  out="$(env -i HOME="$HOME" PATH="$PATH" bash -c "
    cd '$cwd'
    ${env_prefix}
    unset RELAY_FIXES_MODEL RELAY_VERIFICATION_MODEL RELAY_MODEL_SOURCE
    source '$SCRIPT' \"\$@\" >/dev/null 2>&1
    rc=\$?
    printf '%s|%s|%s|%s' \"\$rc\" \"\${RELAY_FIXES_MODEL-UNSET}\" \"\${RELAY_VERIFICATION_MODEL-UNSET}\" \"\${RELAY_MODEL_SOURCE:-}\"
  " _ "$@")"
  rc="${out%%|*}"; out="${out#*|}"
  fx="${out%%|*}"; out="${out#*|}"
  vf="${out%%|*}"; src="${out#*|}"
  if [ "$rc" != "$exp_rc" ]; then
    echo "FAIL: $desc — rc=$rc expected $exp_rc"; _fail=1; return
  fi
  if [ "$exp_rc" = "0" ]; then
    if [ "$fx" != "$exp_fx" ] || [ "$vf" != "$exp_vf" ]; then
      echo "FAIL: $desc — got fixes='$fx' verification='$vf' expected '$exp_fx'/'$exp_vf'"; _fail=1; return
    fi
    if [ -n "$exp_src" ] && [ "$src" != "$exp_src" ]; then
      echo "FAIL: $desc — source='$src' expected '$exp_src'"; _fail=1; return
    fi
  fi
  echo "ok: $desc"
}

# Both variables are exported ALWAYS, empty included: a downstream reader must be able
# to tell "the caller decided there is no override" from "the caller never ran".
_check_models "$_pinless" "no flags exports both axes empty" 0 "" "" \
  "fixes=presets verification=presets" ""
_check_models "$_pinless" "fixes flag alone" 0 "sonnet" "" \
  "fixes=flags verification=presets" "export RELAY_FIXES_MODEL_FLAG=sonnet"
_check_models "$_pinless" "verification flag alone" 0 "" "opus" \
  "fixes=presets verification=flags" "export RELAY_VERIFICATION_MODEL_FLAG=opus"
_check_models "$_pinless" "both flags" 0 "sonnet" "fable" \
  "fixes=flags verification=flags" \
  "export RELAY_FIXES_MODEL_FLAG=sonnet RELAY_VERIFICATION_MODEL_FLAG=fable"
_check_models "$_pinless" "flags are lowercased" 0 "opus" "fable" "" \
  "export RELAY_FIXES_MODEL_FLAG=OPUS RELAY_VERIFICATION_MODEL_FLAG=Fable"
# The enum is sonnet | opus | fable. haiku and inherit are refused, not ignored.
_check_models "$_pinless" "haiku is refused" 1 "" "" "" "export RELAY_FIXES_MODEL_FLAG=haiku"
_check_models "$_pinless" "inherit is refused" 1 "" "" "" "export RELAY_VERIFICATION_MODEL_FLAG=inherit"
_check_models "$_pinless" "garbage is refused" 1 "" "" "" "export RELAY_FIXES_MODEL_FLAG=gpt"
# A flag value must not leak into the next command through the environment: the parser
# clears both input variables once it has read them.
_leaked="$(env -i HOME="$HOME" PATH="$PATH" bash -c "
  cd '$_pinless'
  export RELAY_FIXES_MODEL_FLAG=opus RELAY_VERIFICATION_MODEL_FLAG=fable
  source '$SCRIPT' '' '' >/dev/null 2>&1
  printf '%s/%s' \"\${RELAY_FIXES_MODEL_FLAG-UNSET}\" \"\${RELAY_VERIFICATION_MODEL_FLAG-UNSET}\"
")"
if [ "$_leaked" = "UNSET/UNSET" ]; then
  echo "ok: both flag variables are unset after the parse"
else
  echo "FAIL: flag variables leaked ($_leaked)"; _fail=1
fi
# .claude/relay.json pins fill in, and a flag beats a pin.
_d="$(_pin_dir pin-models '{"fixes_model": "fable", "verification_model": "sonnet"}')"
_check_models "$_d" "pins resolve" 0 "fable" "sonnet" \
  "fixes=relay.json verification=relay.json" ""
_check_models "$_d" "flag beats pin" 0 "opus" "sonnet" \
  "fixes=flags verification=relay.json" "export RELAY_FIXES_MODEL_FLAG=opus"
_d="$(_pin_dir pin-models-bad '{"fixes_model": "haiku"}')"
_check_models "$_d" "invalid pin is refused" 1 "" "" "" ""
_check_err "$_d" "invalid pin names its origin" 1 "from .claude/relay.json pin"
# The two readers must agree on the enum, so resolve-tier.sh refuses the same values.
_d="$(_pin_dir pin-models-ok '{"fixes_model": "fable"}')"
_check_models "$_d" "a valid pin passes" 0 "fable" "" "fixes=relay.json verification=presets" ""

# ---- 4.47.0: the per-command default layer -----------------------------------
# A command body exports RELAY_DEFAULT_ENGINE / RELAY_DEFAULT_AGENT before it sources
# the script. Both move only the DEFAULT layer: a flag and a pin still beat them.
_D='export RELAY_DEFAULT_ENGINE=acpx RELAY_DEFAULT_AGENT=claude;'
_check "command default resolves acpx/claude" 0 acpx claude default 1 "$_D"
_check "a flag beats the command default" 0 in-session claude flags 1 "$_D" in-session
# The default AGENT applies only when the engine also came from the default. Without
# that gate, `--engine smart-routing` would inherit agent=claude and fail an invariant
# on a flag the user typed correctly.
_check "explicit engine still derives its own agent" 0 smart-routing smart-routing flags 1 "$_D" smart-routing
_check "an agent flag beats the command default agent" 0 acpx hybrid default+flags 1 "$_D" "" hybrid
# A command may move the engine alone; the derivation table then supplies the agent.
_check "command default engine alone derives hybrid" 0 acpx hybrid default 1 \
  'export RELAY_DEFAULT_ENGINE=acpx;'
_check "command default is lowercased like a flag" 0 acpx claude default 1 \
  'export RELAY_DEFAULT_ENGINE=ACPX RELAY_DEFAULT_AGENT=Claude;'
# The cross-arg invariants outrank the command default — never coerced, never silent.
_check "command default agent still meets the invariants" 1 "" "" "" "" \
  'export RELAY_DEFAULT_AGENT=hybrid;'
# An invalid command default is a plugin bug, and the error must say so rather than
# read as a user typo.
_bad="$(env -i HOME="$HOME" PATH="$PATH" bash -c "
  cd '$_pinless'
  export RELAY_DEFAULT_ENGINE=acpz
  source '$SCRIPT' '' '' 2>&1 >/dev/null
")"
case "$_bad" in
  *"from this command's built-in default"*) echo "ok: an invalid command default names its origin" ;;
  *) echo "FAIL: invalid command default did not name its origin (got: $_bad)"; _fail=1 ;;
esac
# Both variables are cleared, so one command's default cannot reach the next command.
_leaked="$(env -i HOME="$HOME" PATH="$PATH" bash -c "
  cd '$_pinless'
  export RELAY_DEFAULT_ENGINE=acpx RELAY_DEFAULT_AGENT=claude
  source '$SCRIPT' '' '' >/dev/null 2>&1
  source '$SCRIPT' '' '' >/dev/null 2>&1
  printf '%s/%s/%s/%s' \"\${RELAY_DEFAULT_ENGINE-UNSET}\" \"\${RELAY_DEFAULT_AGENT-UNSET}\" \"\$RELAY_ENGINE\" \"\$RELAY_AGENT\"
")"
if [ "$_leaked" = "UNSET/UNSET/in-session/claude" ]; then
  echo "ok: a command default is cleared and does not reach the next parse"
else
  echo "FAIL: command default leaked ($_leaked)"; _fail=1
fi
# A .claude/relay.json pin outranks the command default on both axes.
_d="$(_pin_dir pin-over-cmd-default '{"engine": "in-session"}')"
_check_in "$_d" "a pin beats the command default" 0 in-session claude relay.json 1 "$_D"

if [ "$_fail" -ne 0 ]; then
  echo "BEHAVIORAL SUITE FAILED"
  exit 1
fi
echo "BEHAVIORAL SUITE PASSED"
exit 0
