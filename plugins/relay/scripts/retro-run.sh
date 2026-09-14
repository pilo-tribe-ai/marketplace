#!/usr/bin/env bash
# relay: post-run retro (spec §3). EXECUTED, never sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/retro-run.sh" [<runId>|last]
#
# Diagnoses one finished Workflow run against its own declared intent. Strictly
# READ-ONLY and ADVISORY: it writes no file (a retro must not dirty the branch it is
# auditing), it never re-runs a node, and only the always-on completeness gate may
# change run behavior. The caller reports the findings; it does not fail the command
# on them.
#
# EXIT CODES — these three and no others:
#   0  CLEAN         the retro ran and found no deviation.
#   1  DEVIATIONS    the retro ran and found at least one deviation.
#   2  UNAVAILABLE   too little evidence survives to retro this run at all.
# Unlike the gate, exit 1 is a REPORT, not a failure — nothing downstream is blocked
# by it. Exit 2 is reserved for "the run records are gone", not for a degraded read:
# a partial read still exits 0/1 and names what it could not check.
#
# THE FIVE COMPARISONS (spec §3.3). Each degrades independently — a comparison that
# cannot run prints `?` and says why, and never silently counts as a pass:
#   C1 SPINE   recorded intended_spine vs actual agent labels, minus gate-suppressed
#              roles. REQUIRES the intent record; without one it degrades to unknown.
#   C2 PHASE   phases[].title vs the {phaseTitle} set over agent records. A declared
#              phase with zero agent records was never reached. Needs no intent record.
#              phases[] is a STATIC PRE-SCAN of phase() literals, not an execution log —
#              which is exactly why it is declared intent that survives its run's death.
#   C3 SILENT  the §0 soft-failure predicate, delegated to verify-run-completeness.sh
#              so there is ONE implementation of the predicate and the in-run and
#              post-hoc definitions cannot drift. Corroborated against logs[].
#   C4 AXIS    the script's ENGINE/AGENT consts vs the recorded axis, plus any node
#              whose fallbackModel differs from its model (unexpected fallback).
#   C5 COST    status, top-level error, any attempt > 1, agentCount vs the actual agent
#              record count, and duration/token/tool-call outliers.
#
# C3 IS THE AUDITOR OF THE GATE, NOT A DUPLICATE OF IT (spec §3.8). If the gate is
# working, C3 comes back empty. A non-empty C3 in which every dead node shows
# attempt == 1 means THE GATE DID NOT FIRE — the single highest-value finding a retro
# can produce. The retro does not re-litigate individual node retries; it reports the
# aggregate.
#
# DEGRADATION LADDER (spec §3.5) — each rung still produces value:
#   1. No intent record (any pre-4.17 run): fall back to script-derived intent. C2, C3
#      and C5 run fully, C4 partially, C1 degrades to unknown. This is the common case
#      and it is strong.
#   2. Stale scriptPath / session_dir: NEVER read wf.scriptPath as the resolution path.
#      Resolve by key, then glob by runId. A recorded scriptPath under a different
#      session dir is REPORTED AS A FINDING — a moved slug means the run crossed a
#      worktree boundary mid-session.
#   3. Missing scripts/*.js: read the inline wf.script copy instead. The double-persist
#      is a feature, not waste — it is precisely what makes a stale scriptPath non-fatal.
#   4. Missing wf_*.json: journal-only degraded mode. Thin — the journal key is
#      v2:<sha256>, not a label, so nodes cannot be named. Reported as such.
#   5. Everything aged out: report the run age and that the evidence is gone (exit 2).
#
# RESOLUTION (identical rules to verify-run-completeness.sh, spec §2.3):
#   NEVER derive the project slug from $PWD. The slug is fixed at session launch and
#   EnterWorktree does not update it, so a pwd-derived slug looks in a directory that
#   does not exist. Every source-modifying relay command enters a worktree at Step 0.5,
#   so that trap is the normal case, not the edge.
#
# `set -e` is deliberately NOT set: an incidental non-zero (a grep miss) would abort
# with ITS status, and status 1 means DEVIATIONS here. Every exit is explicit.
set -uo pipefail

_retro_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_retro_usage='usage: retro-run.sh [<runId>|last]   (exit 0 CLEAN, 1 DEVIATIONS, 2 UNAVAILABLE)'

# Single UNAVAILABLE exit. $1 = machine reason token, $2 = human sentence.
_retro_unavailable() {
  printf 'RELAY_RETRO=UNAVAILABLE\n'
  printf 'RELAY_RETRO_REASON=%s\n' "$1"
  printf '[relay] retro unavailable: %s\n' "$2"
  printf '[relay] A retro is advisory — report that this run could not be retroed and continue.\n'
  exit 2
}

_retro_run_id=""
case "${1:-}" in
  -h|--help)
    printf '%s\n' "$_retro_usage"
    exit 0
    ;;
  -*)
    _retro_unavailable usage "unknown flag '$1'. $_retro_usage"
    ;;
  last|"")
    _retro_run_id=""
    ;;
  *)
    _retro_run_id="$1"
    ;;
esac
if [ "$#" -gt 1 ]; then
  _retro_unavailable usage "expected at most one argument. $_retro_usage"
fi

# --- prerequisites ---------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  _retro_unavailable python3_missing "python3 is required to parse the run record (stdlib json only; jq is not a relay dependency)"
fi
if [ -z "${HOME:-}" ]; then
  _retro_unavailable no_home "\$HOME is unset, so the projects root cannot be resolved"
fi
_retro_projects="$HOME/.claude/projects"
if [ ! -d "$_retro_projects" ]; then
  _retro_unavailable no_projects_root "no projects root at $_retro_projects"
fi

# Normalize the runId: accept `wf_x`, `wf_x.json`, or a path. Reject any path separator
# so a caller-supplied id cannot escape the projects root.
if [ -n "$_retro_run_id" ]; then
  _retro_run_id="${_retro_run_id##*/}"
  _retro_run_id="${_retro_run_id%.json}"
  case "$_retro_run_id" in
    ''|*[!A-Za-z0-9._-]*)
      _retro_unavailable bad_run_id "runId '$1' is not a bare run identifier"
      ;;
  esac
fi

# --- session dir (never from $PWD) -----------------------------------------------
_retro_session_id="${CLAUDE_CODE_SESSION_ID:-}"
_retro_session_dir=""
if [ -n "$_retro_session_id" ]; then
  _retro_session_dir="$(find "$_retro_projects" -mindepth 2 -maxdepth 2 -type d -name "$_retro_session_id" 2>/dev/null | head -n 1)"
fi
if [ -z "$_retro_run_id" ] && [ -z "$_retro_session_dir" ]; then
  _retro_unavailable no_session_id "no runId was given and CLAUDE_CODE_SESSION_ID resolves to no session directory, so 'last' has nothing to resolve against"
fi

# --- run file --------------------------------------------------------------------
_retro_run_file=""
_retro_resolved_by=""
if [ -n "$_retro_session_dir" ]; then
  if [ -n "$_retro_run_id" ]; then
    if [ -f "$_retro_session_dir/workflows/$_retro_run_id.json" ]; then
      _retro_run_file="$_retro_session_dir/workflows/$_retro_run_id.json"
    elif [ -f "$_retro_session_dir/workflows/wf_$_retro_run_id.json" ]; then
      _retro_run_file="$_retro_session_dir/workflows/wf_$_retro_run_id.json"
    fi
  else
    _retro_run_file="$(ls -1t "$_retro_session_dir"/workflows/wf_*.json 2>/dev/null | head -n 1)"
  fi
  [ -n "$_retro_run_file" ] && _retro_resolved_by="session-id"
fi
if [ -z "$_retro_run_file" ] && [ -n "$_retro_run_id" ]; then
  for _retro_cand in "$_retro_projects"/*/*/workflows/"$_retro_run_id".json \
                     "$_retro_projects"/*/*/workflows/"wf_$_retro_run_id".json; do
    if [ -f "$_retro_cand" ]; then
      _retro_run_file="$_retro_cand"
      _retro_resolved_by="runid-glob"
      break
    fi
  done
fi

# --- rung 4/5: no run file -------------------------------------------------------
# Journal-only degraded mode needs a session dir AND a concrete runId; without the run
# file the journal keys are v2:<sha256>, not labels, so nodes cannot be named.
if [ -z "$_retro_run_file" ]; then
  if [ -n "$_retro_run_id" ] && [ -n "$_retro_session_dir" ] &&
     [ -f "$_retro_session_dir/subagents/workflows/$_retro_run_id/journal.jsonl" ]; then
    _retro_journal="$_retro_session_dir/subagents/workflows/$_retro_run_id/journal.jsonl"
    printf 'RELAY_RETRO=DEGRADED\n'
    printf 'RELAY_RETRO_MODE=journal-only\n'
    printf 'RELAY_RETRO_RUN_ID=%s\n' "$_retro_run_id"
    printf 'RELAY_RETRO_JOURNAL=%s\n' "$_retro_journal"
    printf '[relay] degraded: journal-only. No wf_%s.json survives, so nodes cannot be\n' "$_retro_run_id"
    printf '[relay] named (the journal key is v2:<sha256>, not a label) and no declared\n'
    printf '[relay] phase list, axis, or cost record exists to compare against.\n'
    # Parse the journal, never grep it: the records are JSON and their key spacing is
    # not a contract, so a literal '"type":"started"' pattern silently counts zero on a
    # pretty-printed writer — and a zero count here reads as "nothing was lost".
    # Distinct agentIds, matching the gate, so superseded retry attempts cannot inflate
    # either side.
    _retro_counts="$(python3 - "$_retro_journal" <<'PYCOUNT'
import json
import sys

started, resulted = set(), set()
try:
    with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            agent_id = record.get("agentId")
            if not agent_id:
                continue
            if record.get("type") == "started":
                started.add(agent_id)
            elif record.get("type") == "result":
                resulted.add(agent_id)
except OSError:
    pass
print("%d %d" % (len(started), len(resulted)))
PYCOUNT
)"
    _retro_started="${_retro_counts%% *}"
    _retro_results="${_retro_counts##* }"
    printf 'RELAY_RETRO_JOURNAL_STARTED=%s\n' "$_retro_started"
    printf 'RELAY_RETRO_JOURNAL_RESULTS=%s\n' "$_retro_results"
    if [ "$_retro_started" -gt "$_retro_results" ] 2>/dev/null; then
      printf '[relay] SILENT ? %s started vs %s result records — unnameable but non-zero.\n' \
        "$_retro_started" "$_retro_results"
      exit 1
    fi
    exit 0
  fi
  if [ -n "$_retro_run_id" ]; then
    _retro_unavailable run_file_not_found "no run record for '$_retro_run_id' under $_retro_projects, and no journal survives either — the evidence for this run has aged out"
  fi
  _retro_unavailable no_run_id "no wf_*.json exists under $_retro_session_dir/workflows"
fi

if [ ! -r "$_retro_run_file" ]; then
  _retro_unavailable run_file_unreadable "cannot read $_retro_run_file"
fi

# The run file's grandparent is the authoritative session dir — the script lives beside the
# run file, not beside a possibly-stale session id. The journal is not re-derived here: on
# this path the §0 predicate is the gate's job, and the gate resolves its own journal.
_retro_run_id="$(basename "$_retro_run_file" .json)"
_retro_session_dir="$(dirname "$(dirname "$_retro_run_file")")"

printf 'RELAY_RETRO_RUN_ID=%s\n' "$_retro_run_id"
printf 'RELAY_RETRO_RUN_FILE=%s\n' "$_retro_run_file"
printf 'RELAY_RETRO_RESOLVED_BY=%s\n' "$_retro_resolved_by"

# --- C3: delegate the §0 predicate to the gate -----------------------------------
# ONE implementation of the predicate, so the in-run and post-hoc definitions cannot
# drift. The gate resolves by session id first and only falls back to the runId glob
# when that id matches no directory; when this session has no id, hand it a sentinel
# that deliberately matches nothing so it takes the glob path against the runId we
# already resolved. runIds are unique, so the file it finds is the file we read.
_retro_gate_out="$(
  CLAUDE_CODE_SESSION_ID="${CLAUDE_CODE_SESSION_ID:-relay-retro-no-session}" \
  bash "$_retro_here/verify-run-completeness.sh" "$_retro_run_id" 2>&1
)"
_retro_gate_rc=$?

# --- intent record (rung 1) ------------------------------------------------------
_retro_intent="$HOME/.claude/relay/runs.jsonl"
[ -f "$_retro_intent" ] || _retro_intent=""

# --- script text (rungs 2 + 3) ---------------------------------------------------
# Resolve by KEY, never by the recorded wf.scriptPath. A recorded path under a
# different session dir is a finding, not a resolution route.
_retro_script=""
for _retro_cand in "$_retro_session_dir"/workflows/scripts/*"$_retro_run_id".js; do
  if [ -f "$_retro_cand" ]; then
    _retro_script="$_retro_cand"
    break
  fi
done

RELAY_GATE_OUT="$_retro_gate_out" \
python3 - "$_retro_run_file" "$_retro_run_id" \
          "$_retro_gate_rc" "$_retro_script" "$_retro_intent" "$_retro_session_dir" <<'PY'
import json
import os
import re
import sys
import time

(RUN_FILE, RUN_ID, GATE_RC,
 SCRIPT_PATH, INTENT_FILE, SESSION_DIR) = sys.argv[1:7]
GATE_RC = int(GATE_RC)


def norm_run_id(value):
    """`wf_abc` and `abc` name the same run.

    The run file is `wf_<runId>.json`, so RUN_ID here always carries the prefix, while the
    caller of record-run-intent.sh writes whatever the Workflow tool result gave it. An
    unnormalized comparison silently never joins, which degrades C1 to `?` on every run
    and makes the whole intent record inert.
    """
    text = str(value or "")
    return text[3:] if text.startswith("wf_") else text


deviations = []   # human sentences, one per finding
lines = []        # the rendered report body


def emit(label, mark, text):
    """mark is one of ✓ (checked, clean), ✗ (deviation), ? (could not check)."""
    lines.append("  %-9s %s %s" % (label, mark, text))
    if mark == "✗":
        deviations.append("%s: %s" % (label, text))


def cell(value):
    if value is None or value == "":
        return "-"
    return str(value).replace("\n", " ")


def human_ms(ms):
    try:
        total = int(ms) // 1000
    except (TypeError, ValueError):
        return "-"
    if total >= 3600:
        return "%dh%02dm%02ds" % (total // 3600, (total % 3600) // 60, total % 60)
    if total >= 60:
        return "%dm%02ds" % (total // 60, total % 60)
    return "%ds" % total


try:
    with open(RUN_FILE, "r", encoding="utf-8", errors="replace") as handle:
        run = json.load(handle)
except (OSError, ValueError) as exc:
    print("RELAY_RETRO=UNAVAILABLE")
    print("RELAY_RETRO_REASON=run_file_unparseable")
    print("[relay] retro unavailable: %s is not readable JSON (%s)" % (RUN_FILE, exc))
    sys.exit(2)

if not isinstance(run, dict):
    print("RELAY_RETRO=UNAVAILABLE")
    print("RELAY_RETRO_REASON=run_file_schema")
    print("[relay] retro unavailable: %s is not a JSON object" % RUN_FILE)
    sys.exit(2)

progress = run.get("workflowProgress")
if not isinstance(progress, list):
    print("RELAY_RETRO=UNAVAILABLE")
    print("RELAY_RETRO_REASON=run_file_schema")
    print("[relay] retro unavailable: %s has no workflowProgress[] array — the "
          "run-file format has changed" % RUN_FILE)
    sys.exit(2)

# workflowProgress[] is HETEROGENEOUS — [{type:"workflow_phase"} x N] ++
# [{type:"workflow_agent"} x M], with no `agentType` field. Phase entries carry no
# agentId and must be skipped when iterating agents.
agent_entries = [e for e in progress
                 if isinstance(e, dict) and e.get("type") == "workflow_agent"]

# --- script text: rung 3 falls back to the inline copy ---------------------------
script_text, script_source = "", "none"
if SCRIPT_PATH and os.path.isfile(SCRIPT_PATH):
    try:
        with open(SCRIPT_PATH, "r", encoding="utf-8", errors="replace") as handle:
            script_text = handle.read()
        script_source = "file"
    except OSError:
        script_text = ""
if not script_text:
    inline = run.get("script")
    if isinstance(inline, str) and inline:
        script_text, script_source = inline, "inline"


def script_const(name):
    """Read `const NAME = '<value>'` out of the persisted script text."""
    match = re.search(r"const\s+%s\s*=\s*['\"]([^'\"]*)['\"]" % name, script_text)
    return match.group(1) if match else None


# --- intent record: rung 1 -------------------------------------------------------
intent = None
if INTENT_FILE and os.path.isfile(INTENT_FILE):
    try:
        with open(INTENT_FILE, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if (isinstance(record, dict)
                        and norm_run_id(record.get("run_id")) == norm_run_id(RUN_ID)):
                    intent = record   # last write wins
    except OSError:
        intent = None

command = (intent or {}).get("relay_command") or run.get("workflowName") or "-"
kind = (intent or {}).get("kind") or "-"

# --- header ----------------------------------------------------------------------
status = run.get("status", "-")
node_ms = sum(int(e.get("durationMs") or 0) for e in agent_entries)
node_tokens = sum(int(e.get("tokens") or 0) for e in agent_entries)
node_calls = sum(int(e.get("toolCalls") or 0) for e in agent_entries)
run_ms = run.get("durationMs") or run.get("elapsedMs") or node_ms

# The axis VALUES are durable in the script (const ENGINE / const AGENT) and are
# therefore deliberately not duplicated into the intent record — a second source of
# truth could disagree with the script. Only the PROVENANCE of the axis (flag, pin,
# prompt, default) is unrecoverable from any artifact, so that is what the record
# carries.
engine = script_const("ENGINE") or "-"
agent_axis = script_const("AGENT") or "-"
axis_source = (intent or {}).get("axis_source") or "script-derived"

# --- C1 SPINE: needs the intent record -------------------------------------------
actual_labels = [str(e.get("label") or "") for e in agent_entries]
if intent is None:
    emit("SPINE", "?", "spine coverage unknown — no intent record for this run "
                       "(pre-4.17 run, or the run was launched without Step 3.5). "
                       "C2/C3/C5 below are unaffected.")
else:
    intended = [str(s) for s in (intent.get("intended_spine") or [])]
    gates = {str(k): v for k, v in (intent.get("gates") or {}).items()}
    suppressed = [role for role in intended if gates.get(role) is False]
    expected = [role for role in intended if role not in suppressed]
    joined = " ".join(actual_labels).lower()
    missing = [role for role in expected if role.lower() not in joined]
    if not intended:
        emit("SPINE", "✓", "no hard spine declared for %s — %d agent node(s) ran "
                           "(coverage is descriptive here, not a deviation)"
                           % (command, len(agent_entries)))
    elif missing:
        emit("SPINE", "✗", "%d of %d intended spine role(s) produced no agent node: %s%s"
                           % (len(missing), len(expected), ", ".join(missing),
                              (" (gate-suppressed and excluded: %s)" % ", ".join(suppressed))
                              if suppressed else ""))
    else:
        emit("SPINE", "✓", "all %d intended spine role(s) ran%s"
                           % (len(expected),
                              (", %d gate-suppressed" % len(suppressed)) if suppressed else ""))

# --- C2 PHASE: declared phases vs phases actually reached ------------------------
declared = []
for item in (run.get("phases") or []):
    if isinstance(item, dict) and item.get("title"):
        declared.append(str(item["title"]))
    elif isinstance(item, str):
        declared.append(item)
reached = {str(e.get("phaseTitle")) for e in agent_entries if e.get("phaseTitle")}
if not declared:
    emit("PHASE", "?", "the run record declares no phases[] — nothing to compare "
                       "reach against (the script may omit meta.phases)")
else:
    unreached = [title for title in declared if title not in reached]
    if unreached:
        emit("PHASE", "✗", "%d of %d declared phases never reached: %s"
                           % (len(unreached), len(declared), ", ".join(unreached)))
    else:
        emit("PHASE", "✓", "all %d declared phases reached" % len(declared))
    extra = sorted(title for title in reached if title not in declared)
    if extra:
        lines.append("  %-9s   %s" % ("", "note: %d phase(s) ran that meta.phases never "
                                          "declared: %s" % (len(extra), ", ".join(extra))))

# --- C3 SILENT: the §0 predicate, via the gate -----------------------------------
# The gate's stdout crosses into this parser through the environment rather than a temp
# file: it is a few KB at most, and a temp file would leak if the retro were killed
# between mktemp and rm.
gate_out = os.environ.get("RELAY_GATE_OUT", "")
dead_lines = [ln[len("RELAY_DEAD_NODE="):].strip()
              for ln in gate_out.splitlines() if ln.startswith("RELAY_DEAD_NODE=")]
log_lines = [ln[len("RELAY_LOG_SIGNAL="):].strip()
             for ln in gate_out.splitlines() if ln.startswith("RELAY_LOG_SIGNAL=")]

# Joined on agentId, NOT on label. `label` is optional (the gate renders an absent one as
# `-`) and is not unique (a retried node reuses its role's label), so a label join misses
# exactly the entries whose `attempt` decides the §3.8 audit below — and a miss defaults to
# attempt 1, which is the trigger for the audit. The gate prints `agentId=` on every
# RELAY_DEAD_NODE line for this reason.
by_agent_id = {}
for entry in agent_entries:
    entry_id = entry.get("agentId")
    if entry_id:
        by_agent_id.setdefault(str(entry_id), entry)

silent_unchecked = False
if GATE_RC == 2:
    reason = "unknown"
    for ln in gate_out.splitlines():
        if ln.startswith("RELAY_COMPLETENESS_REASON="):
            reason = ln.split("=", 1)[1].strip()
    # SILENT is the one check this whole design exists for. When it cannot run, the
    # retro must NOT come back CLEAN — that would be the same fail-to-pass shape the
    # gate refuses. A `?` on any other row is benign (C1 is `?` on every pre-4.17 run,
    # which is the common case); a `?` here is not.
    silent_unchecked = True
    emit("SILENT", "?", "the completeness gate returned INDETERMINATE (%s) — soft "
                        "failures could not be checked for this run. Not a pass." % reason)
elif GATE_RC == 1:
    # One pass: the RELAY_DEAD_NODE line shape ("<label> | key=value | ...") is parsed
    # here and nowhere else, so a change to the gate's output format cannot leave the
    # §3.8 attempt lookup silently matching nothing while the ✗ rows still render.
    attempts = []
    for text in dead_lines:
        label = text.split("|", 1)[0].strip()
        last_tool = "-"
        agent_id = ""
        for part in text.split("|"):
            part = part.strip()
            if part.startswith("lastTool="):
                last_tool = part.split("=", 1)[1].strip()
            elif part.startswith("agentId="):
                agent_id = part.split("=", 1)[1].strip()
        suffix = ("  [log: \"%s\"]" % log_lines[0][:80]) if log_lines else ""
        emit("SILENT", "✗", "%s — started, no result, last tool %s%s"
                            % (label, last_tool, suffix))
        entry = by_agent_id.get(agent_id)
        # An unjoinable line is NOT evidence of attempt 1 — it is no evidence at all, and
        # feeding it in as 1 would manufacture the §3.8 audit finding.
        attempts.append(int(entry.get("attempt") or 1) if entry is not None else None)
    # §3.8 — the single highest-value finding a retro can produce. Only assert it when
    # every dead node actually joined; an unjoined node makes the claim unprovable.
    known = [value for value in attempts if value is not None]
    if attempts and len(known) == len(attempts) and all(value == 1 for value in known):
        lines.append("  %-9s   %s" % ("", "AUDIT: every dead node shows attempt == 1 — "
                                          "the always-on completeness gate did not fire "
                                          "on this run."))
        deviations.append("SILENT: the completeness gate did not fire (all dead nodes "
                          "at attempt == 1)")
elif GATE_RC == 0:
    emit("SILENT", "✓", "every scoped agent node returned a result")
else:
    # The gate normalizes its own verdicts to 0/1/2, so anything else means the gate did
    # not run at all (missing, unreadable, killed). Same rule as GATE_RC == 2: SILENT is
    # the check this design exists for, and a check that could not run is never a pass.
    silent_unchecked = True
    emit("SILENT", "?", "the completeness gate could not be executed (exit %d) — soft "
                        "failures could not be checked for this run. Not a pass." % GATE_RC)

# --- C4 AXIS ---------------------------------------------------------------------
axis_notes = []
if script_source == "none":
    emit("AXIS", "?", "neither a persisted script file nor an inline script copy "
                      "survives, so the run's resolved axis cannot be read back")
else:
    # "Asked for acpx, silently ran in-session." A run that resolved a delegating
    # engine but whose script wires no delegation step never left this session, no
    # matter what the axis line printed.
    if engine in ("acpx", "smart-routing") and "delegate-and-watch" not in script_text:
        axis_notes.append("resolved engine=%s but the %s script references no "
                          "delegate-and-watch step — every leaf ran in-session"
                          % (engine, script_source))
    fallbacks = []
    for entry in agent_entries:
        model = entry.get("model")
        fallback = entry.get("fallbackModel")
        if fallback and model and fallback != model:
            fallbacks.append("%s (%s -> %s)"
                             % (cell(entry.get("label")), model, fallback))
    if fallbacks:
        axis_notes.append("unexpected model fallback on %d node(s): %s"
                          % (len(fallbacks), ", ".join(fallbacks[:5])))
    if axis_notes:
        emit("AXIS", "✗", "; ".join(axis_notes))
    elif engine == "-" and agent_axis == "-":
        emit("AXIS", "?", "the %s script declares no ENGINE/AGENT consts — this run "
                          "predates axis persistence" % script_source)
    else:
        emit("AXIS", "✓", "%s/%s as resolved (%s, read from the %s script)"
                          % (engine, agent_axis, axis_source, script_source))

# rung 2 — a recorded scriptPath under a different session dir is a finding.
recorded_path = run.get("scriptPath")
if isinstance(recorded_path, str) and recorded_path:
    recorded_session = os.path.dirname(os.path.dirname(os.path.dirname(recorded_path)))
    if recorded_session and os.path.normpath(recorded_session) != os.path.normpath(SESSION_DIR):
        emit("SLUG", "✗", "the recorded scriptPath resolves under %s but the run "
                          "record lives under %s — this run crossed a worktree "
                          "boundary mid-session (EnterWorktree moved cwd; the project "
                          "slug is fixed at session launch and does not follow)"
                          % (recorded_session, SESSION_DIR))

# --- C5 COST ---------------------------------------------------------------------
cost_notes = []
if status not in ("completed", "-", None):
    cost_notes.append("status: %s" % status)
error = run.get("error")
if error:
    cost_notes.append("error: %s" % str(error).replace("\n", " ")[:160])
retried = [cell(e.get("label")) for e in agent_entries
           if int(e.get("attempt") or 1) > 1]
if retried:
    cost_notes.append("%d node(s) retried: %s" % (len(retried), ", ".join(retried[:5])))
declared_count = run.get("agentCount")
if isinstance(declared_count, int) and declared_count != len(agent_entries):
    cost_notes.append("agentCount says %d but %d agent record(s) exist"
                      % (declared_count, len(agent_entries)))
for text in log_lines:
    cost_notes.append("run log: %s" % text[:160])

# Outliers: 3x the median, and only where enough nodes carry the field to have a
# meaningful median. Reported, never a verdict on its own.
def outliers(key, unit):
    values = [(cell(e.get("label")), int(e.get(key) or 0)) for e in agent_entries
              if e.get(key)]
    if len(values) < 3:
        return []
    ordered = sorted(v for _, v in values)
    median = ordered[len(ordered) // 2]
    if median <= 0:
        return []
    return ["%s %s%s (%dx median)" % (label, value, unit, value // median)
            for label, value in values if value >= 3 * median]

for key, unit in (("durationMs", "ms"), ("tokens", " tok"), ("toolCalls", " calls")):
    found = outliers(key, unit)
    if found:
        cost_notes.append("outlier %s: %s" % (key, "; ".join(found[:3])))

if cost_notes:
    emit("COST", "✗", "; ".join(cost_notes))
else:
    emit("COST", "✓", "status %s, no retries, no outliers, %d agent node(s)"
                      % (status, len(agent_entries)))

# --- render ----------------------------------------------------------------------
age = ""
try:
    age_days = (time.time() - os.path.getmtime(RUN_FILE)) / 86400.0
    age = " · %.0fd old" % age_days if age_days >= 1 else " · today"
except OSError:
    age = ""

verdict = "DEVIATIONS" if deviations else ("DEGRADED" if silent_unchecked else "CLEAN")
print("RELAY_RETRO=%s" % verdict)
print("RELAY_RETRO_DEVIATIONS=%d" % len(deviations))
print("RELAY_RETRO_COMMAND=%s" % command)
print("RELAY_RETRO_KIND=%s" % kind)
print("RELAY_RETRO_INTENT=%s" % ("present" if intent else "absent"))
print("RELAY_RETRO_SCRIPT_SOURCE=%s" % script_source)
print("")
print("RETRO %s — %s (%s) — %d deviation%s"
      % (RUN_ID, command, kind, len(deviations), "" if len(deviations) == 1 else "s"))
print("  status: %s · %s · %d tok · %d tool calls · axis %s/%s (%s)%s"
      % (status, human_ms(run_ms), node_tokens, node_calls, engine, agent_axis,
         axis_source, age))
for line in lines:
    print(line)

if deviations:
    print("  %-9s %s" % ("NEXT", "%d deviation%s above. The retro is advisory and "
                                 "read-only — it re-ran nothing and changed nothing. "
                                 "Report these; act on them deliberately."
                                 % (len(deviations),
                                    "" if len(deviations) == 1 else "s")))
    sys.exit(1)
if silent_unchecked:
    print("  %-9s %s" % ("NEXT", "no deviations found, but the soft-failure check could "
                                 "not run — this run is UNAUDITED for the exact failure "
                                 "class the check exists to catch. Do not read it as "
                                 "clean."))
    sys.exit(1)
print("  %-9s %s" % ("NEXT", "no deviations. Note a clean retro means the checks that "
                             "could run found nothing — any `?` line above was not "
                             "checked and is not a pass."))
sys.exit(0)
PY

_retro_rc=$?
case "$_retro_rc" in
  0|1) exit "$_retro_rc" ;;
  2)   exit 2 ;;
  *)   _retro_unavailable parser_aborted "the retro parser exited with status $_retro_rc" ;;
esac
