#!/usr/bin/env bash
# parse_turn_protocol <role_file>
# Reads the YAML frontmatter to extract verify_artifact and terminal_token.
# Post-migration (PR3 §6): reads verify_artifact from role file top-level YAML
# frontmatter (role files carry `verify_artifact:` at the top level, NOT in a
# `relay:` sub-block). Also supports legacy native-agent files with `relay:` blocks
# for backward compatibility during the migration window.
# Applies defaults and substitutes {{SLOT_*}} from env.
# Exports TP_TERMINAL_TOKEN, TP_VERIFY_ARTIFACT.
# macOS bash 3.2 compatible.
#
# TP_MAX_TURNS and TP_NUDGE_PROMPT are REMOVED: multi-turn loop management
# is now the delegate-and-watch watcher's responsibility (L2 skill), not the
# thin session drivers'. The parser no longer exports those variables.
#
# Behavior:
#   - verify_artifact is read from top-level YAML frontmatter `verify_artifact:` key
#     (role files, PR3 migration); falls back to relay.verify_artifact for legacy
#     native-agent files during the migration window.
#   - The 4 roles that carry verify_artifact (implementer/test-writer/fix-coder/plan-writer)
#     get a non-empty freshness target; every other role keeps it empty (fast-path eligible).
#   - terminal_token is PINNED to the constant ROLE_DONE — it is NOT derived
#     positionally from output-tokens/envelope_tokens.
parse_turn_protocol() {
  local role_file="$1"

  # Extract the full frontmatter block (between first and second ---)
  local fm_block
  fm_block=$(awk '
    /^---[[:space:]]*$/ { fm_count++; next }
    fm_count == 1 { print }
    fm_count >= 2 { exit }
  ' "$role_file")

  get_top_level_field() {
    local key="$1" def="$2"
    local v
    # Match top-level key: `key: value` or `key: "value"` (no leading spaces = top-level)
    v=$(printf '%s\n' "$fm_block" | sed -nE "s/^${key}: *\"?([^\"]*)\"?$/\1/p" | head -1)
    [ -z "$v" ] && v="$def"
    printf '%s' "$v"
  }

  get_relay_field() {
    local key="$1" def="$2"
    local relay_block v
    relay_block=$(printf '%s\n' "$fm_block" | awk '
      /^relay:/ { in_relay = 1; next }
      in_relay && /^[^ ]/ { in_relay = 0 }
      in_relay { print }
    ')
    v=$(printf '%s\n' "$relay_block" | sed -nE "s/^  ${key}: *\"?([^\"]*)\"?$/\1/p" | head -1)
    if [ -z "$v" ]; then
      # Multi-line scalar support
      v=$(printf '%s\n' "$relay_block" | awk -v k="$key" '
        $0 ~ "^  "k": *[|>][+-]?[[:space:]]*$" { cap=1; indent=""; next }
        cap && indent == "" && /^[[:space:]]+[^[:space:]]/ {
          match($0, /^[[:space:]]+/); indent = substr($0, RSTART, RLENGTH)
        }
        cap && indent != "" && index($0, indent) == 1 {
          print substr($0, length(indent)+1); next
        }
        cap { exit }
      ')
    fi
    [ -z "$v" ] && v="$def"
    printf '%s' "$v"
  }

  # terminal_token is a pinned constant (ROLE_DONE), NOT read from frontmatter.
  local tt va
  tt="ROLE_DONE"

  # verify_artifact: try top-level frontmatter first (role files, PR3 §6),
  # then fall back to relay: block (legacy native-agent files).
  va=$(get_top_level_field verify_artifact "")
  if [ -z "$va" ]; then
    va=$(get_relay_field verify_artifact "")
  fi

  # Substitute {{NAME}} with $SLOT_<NAME>. Indirect expansion (no eval).
  substitute() {
    local s="$1" local_tt="${2-}" name varname val
    while [[ "$s" =~ \{\{([A-Z_][A-Z0-9_]*)\}\} ]]; do
      name="${BASH_REMATCH[1]}"
      if [ "$name" = "TERMINAL_TOKEN" ] && [ -n "$local_tt" ]; then
        val="$local_tt"
      else
        varname="SLOT_${name}"
        val="${!varname-}"
      fi
      s="${s//\{\{${name}\}\}/$val}"
    done
    printf '%s' "$s"
  }

  export TP_TERMINAL_TOKEN="$tt"
  export TP_VERIFY_ARTIFACT="$(substitute "$va" "$tt")"

  if [ -z "${TP_TERMINAL_TOKEN}" ]; then
    echo "parse-turn-protocol: TP_TERMINAL_TOKEN resolved to empty (pinned constant lost)" >&2
    return 2
  fi
}
