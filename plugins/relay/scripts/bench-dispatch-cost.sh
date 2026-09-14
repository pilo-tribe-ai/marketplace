#!/usr/bin/env bash
# relay: bench-dispatch-cost.sh — dispatch-cost measurement harness (relay 4.12.0, spec §3).
# Benches the SAME task twice headless via `claude -p --output-format json`:
#   variant A: <command> --engine in-session <task>
#   variant B: <command> --engine acpx --agent codex <task>
# Records Claude-side dollars + per-model usage (modelUsage), codex-side tokens
# from $CODEX_HOME/sessions JSONL (mtime window via marker files; aggregation:
# last cumulative token_count per file, summed across files), and wall-clock;
# writes a markdown comparison report.
# DEV TOOL ONLY: nothing at relay runtime sources or invokes this script.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bench-dispatch-cost.sh [options] "<task prompt>"

Runs the same relay task twice headless and writes a markdown cost report:
  variant A: <command> --engine in-session <task prompt>
  variant B: <command> --engine acpx --agent codex <task prompt>

Options:
  --command <slash>    relay command to bench (default: /relay:implement)
  --out <file>         markdown report path (default: ./bench-dispatch-cost-<UTC timestamp>.md)
  --skip-variant a|b   run only the other variant (partial report)
  --claude-bin <path>  claude binary (default: claude)
  --claude-args "<s>"  extra args appended to both claude invocations verbatim
  --codex-home <dir>   codex home (default: $CODEX_HOME, else ~/.codex)
  --help               this help

Prerequisites: jq; the claude CLI (or --claude-bin); a git checkout with a CLEAN
worktree (the harness refuses to start dirty and hard-resets between variants);
for variant B, acpx >= 0.13.2 and a configured codex CLI (/relay:setup checks).

Recommendation:
  Run inside a disposable git worktree with a permission configuration that allows headless
  edits (e.g. --claude-args "--permission-mode acceptEdits", or a pre-configured
  settings.local.json allowlist). Both variants EDIT FILES; never point the harness at a
  checkout you care about.

Keep other codex work quiet during a bench run: variant B's codex sessions are
selected by an mtime window under <codex-home>/sessions, so a concurrent
unrelated codex session contaminates the numbers (the report lists the selected
file count and window so this is diagnosable).

Caveats (also emitted in every report):
  1. Codex tokens bill to a different plan than Claude tokens. The decision metric is
     Claude-side dollars saved minus supervision overhead, plus wall-clock and main-context
     preservation — NOT total token count.
  2. Prompt-cache asymmetry: in-session leaves read a warm cache at ~0.1x input price, while
     fresh acpx children pay full input price on their whole context. Naive token counts
     therefore overstate delegation savings.
EOF
}

die_usage() { usage >&2; exit 2; }

command_slash="/relay:implement"
out=""
skip_variant=""
claude_bin="claude"
claude_args=""
codex_home="${CODEX_HOME:-$HOME/.codex}"
prompt=""

while [ $# -gt 0 ]; do
  case "$1" in
    --command)      command_slash="${2:?--command needs a value}"; shift 2 ;;
    --out)          out="${2:?--out needs a value}"; shift 2 ;;
    --skip-variant) skip_variant="${2:?--skip-variant needs a value}"; shift 2 ;;
    --claude-bin)   claude_bin="${2:?--claude-bin needs a value}"; shift 2 ;;
    --claude-args)  claude_args="${2:?--claude-args needs a value}"; shift 2 ;;
    --codex-home)   codex_home="${2:?--codex-home needs a value}"; shift 2 ;;
    --help|-h)      usage; exit 0 ;;
    --*)            echo "[bench] error: unknown option: $1" >&2; die_usage ;;
    *)
      if [ -n "$prompt" ]; then
        echo "[bench] error: exactly one positional (the task prompt) is required" >&2
        die_usage
      fi
      prompt="$1"; shift ;;
  esac
done
[ -n "$prompt" ] || die_usage
case "$skip_variant" in ""|a|b) ;; *)
  echo "[bench] error: --skip-variant must be 'a' or 'b'" >&2; die_usage ;;
esac
command -v jq >/dev/null 2>&1 || { echo "[bench] error: jq is required" >&2; exit 2; }

# Per-variant clean workspace (comparability guarantee): refuse dirty, record
# pre-run HEAD, hard-reset between (and after) variants. Outside git: abort.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[bench] error: must run inside a git checkout (per-variant reset contract)" >&2
  die_usage
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "[bench] error: workspace not clean — the harness hard-resets between variants" >&2
  exit 2
fi
pre_head="$(git rev-parse HEAD)"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
[ -n "$out" ] || out="./bench-dispatch-cost-${stamp}.md"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

extra_args=()
if [ -n "$claude_args" ]; then
  read -r -a extra_args <<< "$claude_args"
fi

restore() {
  git reset --hard "$pre_head" >/dev/null
  git clean -fd >/dev/null
}

run_variant() { # $1 = a|b, $2 = composed prompt
  local v="$1" composed="$2" t0 t1 rc=0
  t0="$(date +%s)"
  set +e
  "$claude_bin" -p "$composed" --output-format json "${extra_args[@]+"${extra_args[@]}"}" \
    > "$tmp/variant-$v.json" 2> "$tmp/variant-$v.stderr"
  rc=$?
  set -e
  t1="$(date +%s)"
  echo "$rc" > "$tmp/$v.rc"
  echo "$((t1 - t0))" > "$tmp/$v.secs"
}

a_status="skipped"; b_status="skipped"
b_start_ts="n/a"; b_end_ts="n/a"

if [ "$skip_variant" != "a" ]; then
  echo "[bench] running variant A (in-session)…"
  run_variant a "$command_slash --engine in-session $prompt"
  if [ "$(cat "$tmp/a.rc")" = "0" ]; then a_status="ok"; else a_status="FAILED"; fi
  restore
fi
if [ "$skip_variant" != "b" ]; then
  echo "[bench] running variant B (acpx+codex)…"
  touch "$tmp/b_start"; b_start_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  run_variant b "$command_slash --engine acpx --agent codex $prompt"
  touch "$tmp/b_end"; b_end_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "$(cat "$tmp/b.rc")" = "0" ]; then b_status="ok"; else b_status="FAILED"; fi
  restore
fi

jqv() { # $1 = variant, $2 = jq filter — "n/a" fallback everywhere
  local f="$tmp/variant-$1.json"
  if [ -f "$f" ]; then
    jq -r "$2 // \"n/a\"" "$f" 2>/dev/null || echo "n/a"
  else
    echo "n/a"
  fi
}

model_usage_table() { # per-model Claude usage from .modelUsage // {}
  local f="$tmp/variant-$1.json"
  if [ ! -f "$f" ]; then echo "_variant skipped or produced no result json_"; return 0; fi
  jq -r '
    (.modelUsage // {}) | to_entries
    | if length == 0 then "_no per-model usage in result_"
      else
        (["| model | input | output | cache-read | cache-creation | cost |",
          "|---|---|---|---|---|---|"]
         + [ .[] | "| \(.key) | \(.value.inputTokens // .value.input_tokens // "n/a") | \(.value.outputTokens // .value.output_tokens // "n/a") | \(.value.cacheReadInputTokens // .value.cache_read_input_tokens // "n/a") | \(.value.cacheCreationInputTokens // .value.cache_creation_input_tokens // "n/a") | \(.value.costUSD // .value.cost_usd // "n/a") |" ])
        | .[]
      end' "$f" 2>/dev/null || echo "_unparseable result json_"
}

codex_section() {
  # variant B only; mtime-window selection via marker files (portable on BSD find —
  # @epoch args to -newermt are not). Per file take the LAST cumulative token_count
  # event, then sum across files (token_count payloads are cumulative totals;
  # summing every event would multiply-count).
  local sess="$codex_home/sessions"
  if [ "$skip_variant" = "b" ]; then echo "_variant B skipped_"; return 0; fi
  if [ ! -d "$sess" ]; then echo "no codex sessions found in window"; return 0; fi
  local files f last n=0 in_t=0 cached=0 out_t=0 total=0
  files="$(find "$sess" -type f -name '*.jsonl' -newer "$tmp/b_start" ! -newer "$tmp/b_end" 2>/dev/null || true)"
  if [ -z "$files" ]; then echo "no codex sessions found in window"; return 0; fi
  while IFS= read -r f; do
    last="$(jq -s '[.[] | select(.payload.type? == "token_count") | .payload.info.total_token_usage] | last // empty' "$f" 2>/dev/null || true)"
    if [ -z "$last" ] || [ "$last" = "null" ]; then continue; fi
    n=$((n + 1))
    in_t=$((in_t + $(printf '%s' "$last" | jq -r '.input_tokens // 0')))
    cached=$((cached + $(printf '%s' "$last" | jq -r '.cached_input_tokens // 0')))
    out_t=$((out_t + $(printf '%s' "$last" | jq -r '.output_tokens // 0')))
    total=$((total + $(printf '%s' "$last" | jq -r '.total_tokens // 0')))
  done <<< "$files"
  echo "input $in_t / cached-input $cached / output $out_t / total $total tokens; $n session files in window [$b_start_ts .. $b_end_ts]"
  echo "(aggregation: last cumulative token_count per file, summed across files)"
}

secs_of() { if [ -f "$tmp/$1.secs" ]; then cat "$tmp/$1.secs"; else echo "n/a"; fi; }

{
  echo "# Dispatch cost benchmark — $stamp"
  echo
  echo "Task prompt: $prompt"
  echo "Command: $command_slash   Claude bin: $claude_bin   Extra args: ${claude_args:-none}"
  echo "Pre-run HEAD: $pre_head"
  echo
  echo "| metric                  | A: in-session | B: acpx+codex |"
  echo "|-------------------------|---------------|----------------|"
  echo "| status                  | $a_status | $b_status |"
  echo "| wall-clock (s)          | $(secs_of a) | $(secs_of b) |"
  echo "| claude total_cost_usd*  | $(jqv a '.total_cost_usd') | $(jqv b '.total_cost_usd') |"
  echo "| claude num_turns        | $(jqv a '.num_turns') | $(jqv b '.num_turns') |"
  echo "| claude duration_ms      | $(jqv a '.duration_ms') | $(jqv b '.duration_ms') |"
  echo "| claude duration_api_ms  | $(jqv a '.duration_api_ms') | $(jqv b '.duration_api_ms') |"
  echo
  echo "## Per-model Claude usage"
  echo
  echo "### Variant A (in-session)"
  echo
  model_usage_table a
  echo
  echo "### Variant B (acpx+codex)"
  echo
  model_usage_table b
  echo
  echo "## Codex usage (variant B)"
  echo
  codex_section
  echo
  echo "## How to read this"
  echo
  echo "1. Codex tokens bill to a different plan than Claude tokens. The decision metric is"
  echo "   Claude-side dollars saved minus supervision overhead, plus wall-clock and main-context"
  echo "   preservation — NOT total token count."
  echo "2. Prompt-cache asymmetry: in-session leaves read a warm cache at ~0.1x input price, while"
  echo "   fresh acpx children pay full input price on their whole context. Naive token counts"
  echo "   therefore overstate delegation savings."
  echo
  echo "* total_cost_usd is a client-side estimate reported by claude -p; subagent usage rolls up"
  echo "  into it. It is not a bill."
} > "$out"

echo "[bench] report written: $out"
