#!/usr/bin/env bash
# relay: superpowers presence check. DUAL-MODE.
#  - SOURCED (default; command bodies do `source check-deps.sh || exit 1`): SILENT to stdout,
#    sets the return code only (return 0|1). The probe SET is derived from the RELAY_AGENT env
#    var (exported by parse-engine-agent.sh); $@ is IGNORED so a sourced script never consumes
#    the caller's positionals. [inferred]
#  - EXECUTED with --format json (`bash check-deps.sh --agent <claude|codex|hybrid|opencode>
#    --format json`): prints a per-set matrix {"<set>":{"<skill>":"ok"|"missing"}} and exits.
# Probe SET (the actual skill-set selector — NOT the in-session/acpx engine):
#   CLAUDE set probed when RELAY_AGENT ∈ {claude, hybrid, opencode}; CODEX set
#   (~/.codex/skills/) probed when RELAY_AGENT ∈ {codex, hybrid}. hybrid probes BOTH.
# Uses `return` (not bare `exit 1`) in the sourced path so a failure aborts the parent via ||.
_relay_probe="skills/brainstorming/SKILL.md"
_relay_manifest="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/upstream-superpowers-skills.txt"

# Locate the claude-side superpowers install; echo its root, or empty if absent.
_relay_find_claude() {
  local probe="$1" hit=""
  if test -f "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/plugins/superpowers/${probe}"; then
    hit="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/plugins/superpowers"
  elif test -f "$HOME/.claude/plugins/superpowers/${probe}"; then
    hit="$HOME/.claude/plugins/superpowers"
  else
    # marketplace cache: accept flat (<hit>/skills/...) AND versioned
    # (<hit>/<version>/skills/...) layouts; prefer highest version. -maxdepth 6 reaches
    # cache/<marketplace>/superpowers.
    local _relay_cache _relay_ver _relay_vdir
    while IFS= read -r _relay_cache; do
      [ -z "$_relay_cache" ] && continue
      if test -f "$_relay_cache/${probe}"; then hit="$_relay_cache"; break; fi
      _relay_ver="$(ls -d "$_relay_cache"/*/ 2>/dev/null | sort -V | tac 2>/dev/null \
                    || ls -d "$_relay_cache"/*/ 2>/dev/null | sort -rV)"
      while IFS= read -r _relay_vdir; do
        [ -z "$_relay_vdir" ] && continue
        if test -f "${_relay_vdir%/}/${probe}"; then hit="${_relay_vdir%/}"; break; fi
      done <<< "$_relay_ver"
      [ -n "$hit" ] && break
    done <<< "$(find "$HOME/.claude/plugins" -maxdepth 6 -type d -name superpowers 2>/dev/null)"
  fi
  printf '%s' "$hit"
}

# Codex skill present? ~/.codex/skills/<name>/SKILL.md
_relay_codex_has() { test -f "$HOME/.codex/skills/$1/SKILL.md"; }

# Iterate manifest skill names (col 1), skipping comments/blanks.
_relay_manifest_skills() {
  while IFS= read -r _line; do
    _line="${_line%%#*}"
    set -- $_line
    [ -n "${1:-}" ] && printf '%s\n' "$1"
  done < "$_relay_manifest"
}

# Map an agent token to the two probe-set flags: "<need_claude> <need_codex>".
_relay_probe_set_for() {
  case "$1" in
    codex)            printf 'no yes' ;;
    hybrid)           printf 'yes yes' ;;
    claude|opencode)  printf 'yes no' ;;
    *)                printf 'yes no' ;;
  esac
}

# ===== EXECUTED MODE (only when run directly, never when sourced) =====
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _agent="claude"; _format="text"
  while [ $# -gt 0 ]; do
    case "$1" in
      --agent)    _agent="${2:-claude}"; shift 2 ;;
      --agent=*)  _agent="${1#--agent=}"; shift ;;
      --engine)   _agent="${2:-claude}"; shift 2 ;;   # legacy spelling, same RELAY_AGENT domain
      --engine=*) _agent="${1#--engine=}"; shift ;;
      --format)   _format="${2:-text}"; shift 2 ;;
      --format=*) _format="${1#--format=}"; shift ;;
      *) shift ;;
    esac
  done
  read -r _need_claude _need_codex <<< "$(_relay_probe_set_for "$_agent")"
  _rc=0
  if [ "$_format" = "json" ]; then
    _first=1
    printf '{'
    if [ "$_need_claude" = "yes" ]; then
      _hit="$(_relay_find_claude "$_relay_probe")"
      [ $_first -eq 1 ] && _first=0 || printf ','
      if [ -n "$_hit" ]; then printf '"claude":{"superpowers":"ok"}'
      else printf '"claude":{"superpowers":"missing"}'; _rc=1; fi
    fi
    if [ "$_need_codex" = "yes" ]; then
      [ $_first -eq 1 ] && _first=0 || printf ','
      printf '"codex":{'
      _cfirst=1
      while IFS= read -r _skill; do
        [ $_cfirst -eq 1 ] && _cfirst=0 || printf ','
        if _relay_codex_has "$_skill"; then printf '"%s":"ok"' "$_skill"
        else printf '"%s":"missing"' "$_skill"; _rc=1; fi
      done < <(_relay_manifest_skills)
      printf '}'
    fi
    printf '}\n'
  else
    # human-readable text fallback
    if [ "$_need_claude" = "yes" ]; then
      _hit="$(_relay_find_claude "$_relay_probe")"
      if [ -n "$_hit" ]; then echo "claude: superpowers ok"; else echo "claude: superpowers MISSING"; _rc=1; fi
    fi
    if [ "$_need_codex" = "yes" ]; then
      while IFS= read -r _skill; do
        if _relay_codex_has "$_skill"; then echo "codex: $_skill ok"; else echo "codex: $_skill MISSING"; _rc=1; fi
      done < <(_relay_manifest_skills)
    fi
  fi
  exit "$_rc"
fi

# ===== SOURCED MODE (silent; probe set from RELAY_AGENT env; $@ ignored) =====
read -r _need_claude _need_codex <<< "$(_relay_probe_set_for "${RELAY_AGENT:-claude}")"
_relay_ok=1
if [ "$_need_claude" = "yes" ]; then
  if [ -z "$(_relay_find_claude "$_relay_probe")" ]; then
    cat >&2 <<'EOF'
[relay] BLOCKING: the 'superpowers' plugin is required but was not found.
        Install with:
          /plugin marketplace add obra/superpowers-marketplace
          /plugin install superpowers
        Then re-run this command.
EOF
    _relay_ok=0
  elif command -v claude >/dev/null 2>&1; then
    if ! claude plugin list 2>/dev/null | grep -q '^superpowers\b'; then
      echo "[relay] note: superpowers found on disk but not confirmed via 'claude plugin list'" >&2
    fi
  fi
fi
if [ "$_need_codex" = "yes" ]; then
  while IFS= read -r _skill; do
    if ! _relay_codex_has "$_skill"; then
      echo "[relay] BLOCKING: codex skill '$_skill' missing under ~/.codex/skills/ — run /relay:setup" >&2
      _relay_ok=0
    fi
  done < <(_relay_manifest_skills)
fi
if [ "$_relay_ok" != "1" ]; then return 1; fi
return 0
