#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE="${1:-$HERE/fixtures/hello-spec.md}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUNDIR="$HERE/runs/$TS"; mkdir -p "$RUNDIR"
LOG="$RUNDIR/output.log"; REPORT="$RUNDIR/report.md"
START=$(date +%s)
acpx claude exec "/relay:implement in-session claude $FIXTURE" >"$LOG" 2>&1
RC=$?
END=$(date +%s); DUR=$((END-START))
{
  echo "# Relay e2e eval — $TS"
  echo; echo "- fixture: \`$FIXTURE\`"
  echo "- exit code: $RC"
  echo "- wall-clock: ${DUR}s"
  echo; echo "## Phase markers"
  # Standardized on relay-owned markers [inferred]: relay:refining-specs (NOT superpowers:),
  # and the relay-owned simulator/fixer ROLE_DONE emissions. Spec §7's relay:refining-specs
  # grep is superseded — see Task 26 Phase 2. [inferred]
  for m in "relay:refining-specs" "spec-simulator" "spec-fixer" "ROLE_DONE" "superpowers:writing-plans" "/relay:implement" "implementer" "code-reviewer" "REVIEW=PASS"; do
    if grep -q "$m" "$LOG"; then echo "- [x] $m"; else echo "- [ ] $m  (MISSING)"; fi
  done
} >"$REPORT"
echo "report: $REPORT"
exit $RC
