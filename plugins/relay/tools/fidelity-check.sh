#!/usr/bin/env bash
#
# fidelity-check.sh — relay L2 fidelity harness (§11 / §8.5 Phase-2 deliverable)
#
# Proves the extract->diff cycle end-to-end over N=5 normalized run summaries.
#
# Usage:
#   fidelity-check.sh --smoke
#       Deterministic smoke mode. Reads 5 pre-canned normalized summaries from
#       the default smoke fixture dir (${SCRIPT_DIR}/fixtures/smoke) — no model
#       call. The --smoke flag ALWAYS wins and overrides any pre-existing
#       FIXTURE_DIR env value.
#
#   FIXTURE_DIR=<dir> fidelity-check.sh
#       Custom fixture directory (without --smoke). Reads run-1.json..run-5.json
#       from <dir>. If both --smoke and FIXTURE_DIR are supplied, --smoke takes
#       precedence.
#
#   fidelity-check.sh
#       Live mode is a Phase-2 stub: prints "live mode not implemented in
#       Phase 2" and exits non-zero (2). Live N=5 generation is wired up in
#       Phase 3 against the L3 commands (§8.5 Phase 3 gate). Phase 2 only proves
#       the extract->diff cycle.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SMOKE=0
for arg in "$@"; do
  case "$arg" in
    --smoke) SMOKE=1 ;;
  esac
done

# --- L3 static-structure mode (Phase 3) ---
# Runs AFTER the SMOKE scan and BEFORE the smoke selection so --smoke / bare-run
# paths stay untouched. --l3 <known-cmd> greps the command body for its required
# nodes (classifier + policy branch for non-execute) and rejects a --kind override
# surface (the kind is always auto-classified from context) → exit 0/1.
# --l3 <unknown> or --l3 with no arg → exit 2 (mirrors the non-implemented-mode tail).
L3_REQUESTED=0
L3_CMD=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--l3" ]; then L3_CMD="$arg"; fi
  if [ "$arg" = "--l3" ]; then L3_REQUESTED=1; fi
  prev="$arg"
done

if [ "$L3_REQUESTED" -eq 1 ]; then
  CMD_FILE="${SCRIPT_DIR}/../commands/${L3_CMD}.md"
  if [ -z "${L3_CMD}" ] || [ ! -f "${CMD_FILE}" ]; then
    echo "--l3: unknown command '${L3_CMD}'" >&2
    exit 2
  fi
  # Grep the file directly rather than piping a captured body. `grep -q` exits at its
  # FIRST match, which closes the pipe while `printf` is still writing; printf then dies
  # of SIGPIPE (141) and `pipefail` promotes that into the pipeline's status. The check
  # therefore reported "missing" for a token it had just found — a false FAIL on roughly
  # 6% of runs, whose rate rises with the file's size after the match. Reading the file
  # in-process has no pipe, so there is nothing to race.
  grep -q "classifying-task-kind" "${CMD_FILE}" || { echo "FAIL: ${L3_CMD} missing classifier" >&2; exit 1; }
  grep -q -- "--kind" "${CMD_FILE}" && { echo "FAIL: ${L3_CMD} exposes a --kind override (kind is auto-classified)" >&2; exit 1; }
  if [ "${L3_CMD}" != "execute" ]; then
    grep -qi "branch" "${CMD_FILE}" || { echo "FAIL: ${L3_CMD} missing policy branch" >&2; exit 1; }
  fi
  echo "PASS"
  exit 0
fi

# Precedence: --smoke always wins and pins FIXTURE_DIR to the default smoke dir,
# overriding any pre-existing FIXTURE_DIR env value.
if [ "$SMOKE" -eq 1 ]; then
  FIXTURE_DIR="${SCRIPT_DIR}/fixtures/smoke"
elif [ -n "${FIXTURE_DIR:-}" ]; then
  : # custom fixture dir selected via env (no --smoke)
else
  echo "live mode not implemented in Phase 2" >&2
  exit 2
fi

# Guard: jq is required to canonicalize/extract the normalized summaries.
if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found on PATH; required for fidelity extraction" >&2
  exit 3
fi

# Extract + diff all pairs: run-2..run-5 against run-1 (run-1 is the anchor).
# Explicit indexed loop so ordering never depends on glob/inode order.
for i in 2 3 4 5; do
  diff <(jq -S . "$FIXTURE_DIR/run-1.json") <(jq -S . "$FIXTURE_DIR/run-$i.json") || { echo "FAIL"; exit 1; }
done
echo "PASS"
exit 0
