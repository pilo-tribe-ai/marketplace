#!/usr/bin/env bash
# Behavioral suite for scripts/resolve-tier.sh — the single in-session tier resolution
# site. Run directly: bash tests/unit/skill-structure/test_resolve_tier.sh
#
# Hermeticity: every case runs in a scratch git repo (git init below — the resolver
# resolves the config path via git, so without a repo of its own a scratch dir under a
# TMPDIR that sits inside some checkout would silently read THAT repo's
# .claude/relay.json) and under `env -i` (same rule as test_parse_engine_agent.sh), so
# ambient RELAY_IN_SESSION_TIERS / GIT_DIR / GIT_WORK_TREE cannot invert assertions.
set -uo pipefail

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$_here/../../.." && pwd)"
SCRIPT="$PLUGIN_ROOT/scripts/resolve-tier.sh"
PARSER="$PLUGIN_ROOT/scripts/parse-engine-agent.sh"
_fail=0
_scratch="$(mktemp -d)"
trap 'rm -rf "$_scratch"' EXIT

_repo() { # $1 = name, $2 = relay.json body ("" for none)
  local d="$_scratch/$1"
  mkdir -p "$d/.claude"
  git init -q "$d" >/dev/null 2>&1
  [ -n "$2" ] && printf '%s' "$2" > "$d/.claude/relay.json"
  printf '%s' "$d"
}

_eq() { # $1 = label, $2 = expected, $3 = actual
  if [ "$2" = "$3" ]; then echo "ok: $1"; else
    echo "FAIL: $1"; echo "  expected: $2"; echo "  actual:   $3"; _fail=1
  fi
}

_run() { # $1 = cwd, rest = args ; echoes stdout, discards stderr
  local d="$1"; shift
  ( cd "$d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" "$@" 2>/dev/null )
}

_rc() { # $1 = cwd, rest = args ; echoes exit code
  local d="$1"; shift
  ( cd "$d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" "$@" >/dev/null 2>&1; echo $? )
}

_err() { # $1 = cwd, rest = args ; echoes stderr
  local d="$1"; shift
  ( cd "$d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" "$@" 2>&1 >/dev/null )
}

# --- tier lookups reflect presets.yaml ---
_d="$(_repo plain '')"
_eq "sonnet role resolves"  "model=sonnet effort=high"   "$(_run "$_d" implementer)"
_eq "opus role resolves"    "model=opus effort=medium"   "$(_run "$_d" code-reviewer)"
_eq "haiku role resolves"   "model=haiku effort=low"     "$(_run "$_d" server-runner)"
_eq "inherit keeps effort"  "model=inherit effort=xhigh" "$(_run "$_d" plan-writer)"

# --- the gate ---
_eq "no relay.json => tiers on" "model=sonnet effort=high" "$(_run "$_d" implementer)"
_d="$(_repo off '{"in_session_tiers": false}')"
_eq "explicit false => inherit" "model=inherit effort=-"  "$(_run "$_d" implementer)"
_d="$(_repo on '{"in_session_tiers": true}')"
_eq "explicit true => tiers on" "model=sonnet effort=high" "$(_run "$_d" implementer)"
_d="$(_repo other '{"engine": "acpx"}')"
_eq "unrelated key => tiers on" "model=sonnet effort=high" "$(_run "$_d" implementer)"

# --- worktree entry keeps the PRIMARY checkout's opt-out (4.14.0 regression) ---
# relay.json is untracked per-checkout config; a fresh worktree does not carry it, so
# the resolver must derive the config path from git-common-dir, not the worktree root.
_d="$(_repo wtprimary '{"in_session_tiers": false}')"
( cd "$_d" && git -c user.email=relay@test -c user.name=relay commit -q --allow-empty -m init \
    && git worktree add -q "$_d/wt" >/dev/null 2>&1 )
_eq "worktree keeps primary opt-out" "model=inherit effort=-" "$(_run "$_d/wt" implementer)"

# --- the watcher pin (delegate-and-watch outer node — node-kind constant, gated) ---
_d="$(_repo watcher '')"
_eq "watcher pin resolves"        "model=sonnet effort=low" "$(_run "$_d" watcher)"
_eq "--all header carries watcher line" "1" \
  "$(_run "$_d" --all | grep -c '^\[relay\] watcher (delegate-and-watch outer node): model=sonnet effort=low')"
_d="$(_repo watcheroff '{"in_session_tiers": false}')"
_eq "watcher honors the gate"     "model=inherit effort=-"  "$(_run "$_d" watcher)"
# OFF-mode --all still prints per-role rows (the command notes promise "every row
# prints as inherit") AND the watcher header line, now degraded to inherit.
_eq "--all off row is inherit" "inherit -" \
  "$(_run "$_d" --all | awk '$1 == "implementer" { print $2, $3 }')"
_eq "--all off header carries watcher inherit line" "1" \
  "$(_run "$_d" --all | grep -c '^\[relay\] watcher (delegate-and-watch outer node): model=inherit effort=-')"
# OFF-header provenance names the real gate source.
_eq "off header cites the config" "1" \
  "$(_run "$_d" --all | grep -c 'OFF (in_session_tiers: false in .claude/relay.json)')"
_d="$(_repo envsrc '')"
_eq "off header cites the env var" "1" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" RELAY_IN_SESSION_TIERS=0 CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" --all 2>/dev/null | grep -c 'OFF (RELAY_IN_SESSION_TIERS=0 in the environment)' )"
# (that `watcher` is not a presets.yaml role is asserted structurally in
# test_plugin.py::TestVersion4140::test_watcher_pin_is_not_a_presets_role)

# --- env var wins over the file (parse-engine-agent.sh already decided) ---
_d="$(_repo envwin '{"in_session_tiers": false}')"
_eq "env var overrides file" "model=sonnet effort=high" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" RELAY_IN_SESSION_TIERS=1 CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" implementer 2>/dev/null )"
# ...but only the documented 0/1 values: `false`/`off`/garbage must fail loudly, not
# silently enable tiers (4.14.0 regression — the inverse of the user's plain reading).
_eq "env garbage rc" "2" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" RELAY_IN_SESSION_TIERS=false CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" implementer >/dev/null 2>&1; echo $? )"

# --- the two readers of in_session_tiers must agree ---
_i=0
for body in '' '{"in_session_tiers": true}' '{"in_session_tiers": false}' '{"engine": "in-session"}'; do
  _i=$((_i + 1))
  _d="$(_repo "agree$_i" "$body")"
  _parsed="$( cd "$_d" && unset RELAY_IN_SESSION_TIERS; source "$PARSER" "" "" >/dev/null 2>&1; echo "${RELAY_IN_SESSION_TIERS:-}" )"
  _resolved="$( cd "$_d" && unset RELAY_IN_SESSION_TIERS && "$SCRIPT" implementer 2>/dev/null )"
  # tiers=1 <=> the resolver emits a concrete model; tiers=0 <=> it emits inherit
  case "$_parsed:$_resolved" in
    "1:model=sonnet effort=high"|"0:model=inherit effort=-") echo "ok: readers agree for ${body:-<no file>}" ;;
    *) echo "FAIL: readers disagree for ${body:-<no file>} (parser=$_parsed resolver=$_resolved)"; _fail=1 ;;
  esac
done

# --- the two category overrides (4.46.0) ---
# A run must be able to move every fixes role or every verification role in one flag,
# without touching a role of neither category and without touching any effort.
_cat_run() { # $1 = cwd, $2 = fixes, $3 = verification, rest = args
  local d="$1" fx="$2" vf="$3"; shift 3
  ( cd "$d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
      RELAY_FIXES_MODEL="$fx" RELAY_VERIFICATION_MODEL="$vf" "$SCRIPT" "$@" 2>/dev/null )
}
_cat_rc() { # $1 = cwd, $2 = fixes, $3 = verification, rest = args
  local d="$1" fx="$2" vf="$3"; shift 3
  ( cd "$d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
      RELAY_FIXES_MODEL="$fx" RELAY_VERIFICATION_MODEL="$vf" "$SCRIPT" "$@" >/dev/null 2>&1; echo $? )
}
_d="$(_repo cats '')"
# defaults with no override: the two categories carry the documented pins
_eq "fixes default is sonnet"        "model=sonnet effort=medium" "$(_run "$_d" fix-coder)"
_eq "fix-planner default is sonnet"  "model=sonnet effort=high"   "$(_run "$_d" fix-planner)"
_eq "verification default is opus"   "model=opus effort=medium"   "$(_run "$_d" code-reviewer)"
_eq "ui evaluator default is opus"   "model=opus effort=low"      "$(_run "$_d" ui-visual-evaluator)"
# one flag moves every role of its category, and keeps every effort
_eq "fixes override moves fix-coder"    "model=fable effort=medium" "$(_cat_run "$_d" fable "" fix-coder)"
_eq "fixes override moves spec-fixer"   "model=fable effort=medium" "$(_cat_run "$_d" fable "" spec-fixer)"
_eq "fixes override moves plan-fixer"   "model=fable effort=medium" "$(_cat_run "$_d" fable "" plan-fixer)"
_eq "fixes override keeps fix-planner effort" "model=fable effort=high" "$(_cat_run "$_d" fable "" fix-planner)"
_eq "verification override moves code-reviewer" "model=sonnet effort=medium" "$(_cat_run "$_d" "" sonnet code-reviewer)"
_eq "verification override moves doc-reference-reviewer" "model=sonnet effort=low" "$(_cat_run "$_d" "" sonnet doc-reference-reviewer)"
_eq "verification override moves ui-code-evaluator" "model=sonnet effort=medium" "$(_cat_run "$_d" "" sonnet ui-code-evaluator)"
# an uncategorized role is never touched by either flag
_eq "implementer ignores both flags" "model=sonnet effort=high"   "$(_cat_run "$_d" fable fable implementer)"
_eq "navigator ignores both flags"   "model=haiku effort=low"     "$(_cat_run "$_d" fable fable navigator)"
_eq "plan-writer keeps inherit"      "model=inherit effort=xhigh" "$(_cat_run "$_d" fable fable plan-writer)"
# the two flags are independent
_eq "both flags apply at once (fixes)"        "model=opus effort=medium"   "$(_cat_run "$_d" opus sonnet fix-coder)"
_eq "both flags apply at once (verification)" "model=sonnet effort=medium" "$(_cat_run "$_d" opus sonnet code-reviewer)"
# --all reports the axes in its header, override or not
_eq "--all header names an override" "1" \
  "$(_cat_run "$_d" fable "" --all | grep -c '^\[relay\] fixes-model: fable (source: flag)')"
_eq "--all header names the default" "1" \
  "$(_cat_run "$_d" "" "" --all | grep -c '^\[relay\] verification-model: <per-role pin> (source: presets)')"
_eq "--all row carries the override" "fable medium" \
  "$(_cat_run "$_d" fable "" --all | awk '$1 == "fix-coder" { print $2, $3 }')"
# the enum is sonnet | opus | fable — haiku and inherit are refused, not ignored
_eq "haiku is refused on fixes"          "2" "$(_cat_rc "$_d" haiku "" fix-coder)"
_eq "inherit is refused on verification" "2" "$(_cat_rc "$_d" "" inherit code-reviewer)"
_eq "garbage is refused"                 "2" "$(_cat_rc "$_d" not-a-model "" fix-coder)"
_eq "refusal names the enum" "1" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
       RELAY_FIXES_MODEL=haiku "$SCRIPT" fix-coder 2>&1 >/dev/null | grep -c 'expected: sonnet | opus | fable' )"
# the tiers gate still wins, and the header says the override reached nothing
_d="$(_repo catsoff '{"in_session_tiers": false}')"
_eq "gate off beats the override" "model=inherit effort=-" "$(_cat_run "$_d" fable "" fix-coder)"
_eq "gate off warns the override reached nothing" "1" \
  "$(_cat_run "$_d" fable "" --all | grep -c 'reach no in-session row')"
# the .claude/relay.json pins are read when NEITHER variable is set — including when
# RELAY_IN_SESSION_TIERS is exported, which used to leave the config path unresolved
_d="$(_repo catpin '{"fixes_model": "fable", "verification_model": "sonnet"}')"
_eq "pin moves a fixes role"        "model=fable effort=medium"  "$(_run "$_d" fix-coder)"
_eq "pin moves a verification role" "model=sonnet effort=medium" "$(_run "$_d" code-reviewer)"
_eq "pin survives an exported gate" "model=fable effort=medium" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" RELAY_IN_SESSION_TIERS=1 CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$SCRIPT" fix-coder 2>/dev/null )"
_eq "pin header names its source" "1" \
  "$(_run "$_d" --all | grep -c '^\[relay\] fixes-model: fable (source: .claude/relay.json)')"
# an EMPTY exported variable is a decision ("no override"), so the pin is not re-read
_eq "empty variable beats the pin" "model=sonnet effort=medium" "$(_cat_run "$_d" "" "" fix-coder)"
# an invalid pin fails loudly, exactly as an invalid flag does
_d="$(_repo catpinbad '{"fixes_model": "haiku"}')"
_eq "invalid pin rc" "2" "$(_rc "$_d" fix-coder)"
_d="$(_repo catpintype '{"fixes_model": 7}')"
_eq "non-string pin rc" "2" "$(_rc "$_d" fix-coder)"

# --- error contract ---
_d="$(_repo errs '')"
_eq "unknown role rc"   "1" "$(_rc "$_d" definitely-not-a-role)"
_eq "no args rc"        "1" "$(_rc "$_d")"
_eq "unknown flag rc"   "1" "$(_rc "$_d" --bogus)"
_eq "--all rc"          "0" "$(_rc "$_d" --all)"
_eq "help rc"           "0" "$(_rc "$_d" --help)"
_d="$(_repo badjson '{nope')"
_eq "invalid JSON rc"   "2" "$(_rc "$_d" implementer)"
# help and usage answer before any config I/O — they must work exactly when the
# config is broken (4.14.0 regression).
_eq "help works with broken config" "0" "$(_rc "$_d" --help)"
_eq "no args rc with broken config" "1" "$(_rc "$_d")"
_d="$(_repo badtype '{"in_session_tiers": "yes"}')"
_eq "non-boolean rc"    "2" "$(_rc "$_d" implementer)"
# an explicit null is present-and-non-boolean (has() semantics): rejected loudly,
# unlike 4.13.0's `// false` read which silently treated it as OFF.
_d="$(_repo nullval '{"in_session_tiers": null}')"
_eq "null value rc"     "2" "$(_rc "$_d" implementer)"
# non-object roots get their own diagnosis — not the misleading boolean message,
# and a top-level null/false document is valid JSON, not a syntax error.
_d="$(_repo arrayroot '[]')"
_eq "array root rc"     "2" "$(_rc "$_d" implementer)"
_eq "array root names the shape" "1" \
  "$(_err "$_d" implementer | grep -c 'must be a JSON object')"
_d="$(_repo nullroot 'null')"
_eq "null root names the shape" "1" \
  "$(_err "$_d" implementer | grep -c 'must be a JSON object')"

# --- --all covers every role in presets.yaml, exactly once ---
_d="$(_repo alltbl '')"
# filter by shape, not line number, so the header can grow without breaking this
_rows="$(_run "$_d" --all | awk '!/^\[relay\]/ && NF==3 && $1 != "role" {print $1}' | sort)"
_roles="$(python3 -c "
import yaml
print('\n'.join(sorted(yaml.safe_load(open('$PLUGIN_ROOT/bindings/presets.yaml'))['roles'])))
")"
_eq "--all lists every role" "$_roles" "$_rows"

# --- malformed presets entries are dropped, never misattributed (4.14.0 regression) ---
# A key line the strict role regex rejects (trailing comment) must not let its
# model/effort lines overwrite the PREVIOUS role's captured pair.
_fx="$_scratch/fixture-root"
mkdir -p "$_fx/bindings"
printf '%s\n' \
  'roles:' \
  '  good-role:' \
  '    model: sonnet' \
  '    effort: high' \
  '  bad-role:  # trailing comment breaks the key regex' \
  '    model: opus' \
  '    effort: low' > "$_fx/bindings/presets.yaml"
_d="$(_repo fixturecase '')"
_eq "malformed neighbor cannot corrupt a role" "model=sonnet effort=high" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$_fx" "$SCRIPT" good-role 2>/dev/null )"
_eq "malformed entry is dropped" "1" \
  "$( cd "$_d" && env -i HOME="$HOME" PATH="$PATH" CLAUDE_PLUGIN_ROOT="$_fx" "$SCRIPT" bad-role >/dev/null 2>&1; echo $? )"

if [ "$_fail" -ne 0 ]; then echo "RESOLVE-TIER SUITE FAILED"; exit 1; fi
echo "RESOLVE-TIER SUITE PASSED"
