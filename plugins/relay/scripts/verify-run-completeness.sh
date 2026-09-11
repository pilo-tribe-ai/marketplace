#!/usr/bin/env bash
# relay: post-Workflow completeness gate (spec §2.3, predicate §0). EXECUTED, never
# sourced:
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/verify-run-completeness.sh" [<runId>]
#
# Answers exactly one question: did every agent node the harness started also return a
# result? The harness derives `status` from whether the generated script threw, not from
# whether its nodes produced output, so a script that catches a node failure and returns
# null reports `completed` over dead nodes. This gate is the backstop against that.
#
# EXIT CODES — these three and no others:
#   0  COMPLETE       every scoped agent node returned a result.
#   1  INCOMPLETE     at least one scoped agent node started and never returned.
#   2  INDETERMINATE  the run record could not be located, read, or trusted.
# FAIL TO INDETERMINATE, NEVER TO A PASS. A missing, unreadable, or unrecognized input
# always exits 2. This is the honest counter to reading a private harness artifact whose
# format may change: a format change degrades to "I could not verify", never to a silent
# success. There is deliberately no code path where absent input yields 0.
#
# PREDICATE (spec §0, validated 35 PASS / 3 FAIL / 0 INDETERMINATE over 38 runs, zero
# false positives across 426 nodes):
#   A node soft-failed if it has a `started` record in the run's journal.jsonl and no
#   `result` record for the same agentId.
# Scope restriction, MANDATORY: consider only agentIds that also appear in
# wf_<runId>.json -> workflowProgress[] with type == "workflow_agent". The journal also
# carries superseded retry attempts whose agentId never reaches the progress list;
# without this restriction you get one false positive per affected run (4 of 38).
# Two shapes that bite anyone reading these files:
#   - workflowProgress[] is HETEROGENEOUS — [{type:"workflow_phase"} x N] ++
#     [{type:"workflow_agent"} x M], with no `agentType` field. Phase entries carry no
#     agentId and are skipped.
#   - The per-node reporting fields (durationMs, toolCalls, tokens, lastToolName) are
#     OPTIONAL. Older run files carry none of them. They are printed as `-` when absent
#     and never gate the verdict — a strict read would turn a real detection into
#     "could not verify".
# Rejected predicates, for the next reader: `lastToolName != "StructuredOutput"` (9 false
# positives — schema-less nodes legitimately never call it), and `state != "done"`
# (`state` is "done" on 426/426 nodes including every dead one).
#
# RESOLUTION ORDER (spec §2.3):
#   1. runId    — $1; when absent, the newest wf_*.json under the session dir.
#   2. session  — find "$HOME"/.claude/projects -maxdepth 2 -type d -name
#                 "$CLAUDE_CODE_SESSION_ID". NEVER derive the project slug from $PWD:
#                 the slug is fixed at session launch and EnterWorktree does not update
#                 it, so a pwd-derived slug looks in a directory that does not exist and
#                 the check silently no-ops. Every source-modifying relay command enters
#                 a worktree at Step 0.5, so that trap is the normal case, not the edge.
#   3. fallback — glob "$HOME"/.claude/projects/*/*/workflows/<runId>.json when the
#                 session id resolves to no directory. runIds are unique.
#   4. journal  — <sessionDir>/subagents/workflows/<runId>/journal.jsonl.
# All four steps resolve through $HOME so the gate is runnable against a fixture tree.
#
# OUTPUT — a KEY=value block on stdout (state crosses the Bash->Claude boundary as
# printed stdout, same convention as check-deps.sh / worktree-preflight.sh), plus plain
# prose lines prefixed `[relay]`. Every failure reason is printed to stdout, not stderr
# only, so it is greppable by the caller.
#
# `set -e` is deliberately NOT set. Under -e an incidental non-zero command (a grep miss,
# say) would abort the script with ITS exit status — and status 1 means INCOMPLETE here.
# Every exit is therefore explicit.
set -uo pipefail

_vrc_usage='usage: verify-run-completeness.sh [<runId>]   (exit 0 COMPLETE, 1 INCOMPLETE, 2 INDETERMINATE)'

# Single INDETERMINATE exit. $1 = machine reason token, $2 = human sentence.
_vrc_indeterminate() {
  printf 'RELAY_COMPLETENESS=INDETERMINATE\n'
  printf 'RELAY_COMPLETENESS_REASON=%s\n' "$1"
  printf '[relay] completeness could not be verified: %s\n' "$2"
  printf '[relay] Do not treat INDETERMINATE as a pass — report that completeness could not be verified.\n'
  exit 2
}

_vrc_run_id=""
case "${1:-}" in
  -h|--help)
    printf '%s\n' "$_vrc_usage"
    exit 0
    ;;
  -*)
    _vrc_indeterminate usage "unknown flag '$1'. $_vrc_usage"
    ;;
  *)
    _vrc_run_id="${1:-}"
    ;;
esac
if [ "$#" -gt 1 ]; then
  _vrc_indeterminate usage "expected at most one argument. $_vrc_usage"
fi

# --- step 0: prerequisites -------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  _vrc_indeterminate python3_missing "python3 is required to parse the run record (stdlib json only; jq is not a relay dependency)"
fi
if [ -z "${HOME:-}" ]; then
  _vrc_indeterminate no_home "\$HOME is unset, so the projects root cannot be resolved"
fi
_vrc_projects="$HOME/.claude/projects"
if [ ! -d "$_vrc_projects" ]; then
  _vrc_indeterminate no_projects_root "no projects root at $_vrc_projects"
fi

# Normalize the runId: accept `wf_x`, `wf_x.json`, or a path to the run file. Reject any
# path separator so a caller-supplied id cannot escape the projects root.
if [ -n "$_vrc_run_id" ]; then
  _vrc_run_id="${_vrc_run_id##*/}"
  _vrc_run_id="${_vrc_run_id%.json}"
  case "$_vrc_run_id" in
    ''|*[!A-Za-z0-9._-]*)
      _vrc_indeterminate bad_run_id "runId '$1' is not a bare run identifier"
      ;;
  esac
fi

# --- step 2: session dir (never from $PWD) ---------------------------------------
_vrc_session_id="${CLAUDE_CODE_SESSION_ID:-}"
if [ -z "$_vrc_session_id" ]; then
  _vrc_indeterminate no_session_id "CLAUDE_CODE_SESSION_ID is unset or empty; the session directory cannot be resolved (it is never derived from \$PWD)"
fi
_vrc_session_dir="$(find "$_vrc_projects" -mindepth 2 -maxdepth 2 -type d -name "$_vrc_session_id" 2>/dev/null | head -n 1)"

# --- steps 1 + 3: run file -------------------------------------------------------
_vrc_run_file=""
_vrc_resolved_by=""
if [ -n "$_vrc_session_dir" ]; then
  if [ -n "$_vrc_run_id" ]; then
    if [ -f "$_vrc_session_dir/workflows/$_vrc_run_id.json" ]; then
      _vrc_run_file="$_vrc_session_dir/workflows/$_vrc_run_id.json"
    elif [ -f "$_vrc_session_dir/workflows/wf_$_vrc_run_id.json" ]; then
      _vrc_run_file="$_vrc_session_dir/workflows/wf_$_vrc_run_id.json"
    fi
  else
    # newest wf_*.json under the session dir
    _vrc_run_file="$(ls -1t "$_vrc_session_dir"/workflows/wf_*.json 2>/dev/null | head -n 1)"
  fi
  [ -n "$_vrc_run_file" ] && _vrc_resolved_by="session-id"
fi
if [ -z "$_vrc_run_file" ] && [ -n "$_vrc_run_id" ]; then
  # step 3 fallback — the session id matched no directory, or the run predates it.
  for _vrc_cand in "$_vrc_projects"/*/*/workflows/"$_vrc_run_id".json \
                   "$_vrc_projects"/*/*/workflows/"wf_$_vrc_run_id".json; do
    if [ -f "$_vrc_cand" ]; then
      _vrc_run_file="$_vrc_cand"
      _vrc_resolved_by="runid-glob"
      break
    fi
  done
fi
if [ -z "$_vrc_run_file" ]; then
  if [ -z "$_vrc_session_dir" ]; then
    _vrc_indeterminate session_dir_not_found "no session directory named '$_vrc_session_id' under $_vrc_projects, and no run file matched the glob fallback"
  fi
  if [ -n "$_vrc_run_id" ]; then
    _vrc_indeterminate run_file_not_found "no run file for '$_vrc_run_id' under $_vrc_session_dir/workflows nor anywhere under $_vrc_projects"
  fi
  _vrc_indeterminate no_run_id "no runId was passed and no wf_*.json exists under $_vrc_session_dir/workflows"
fi

# When the fallback located the file, the session dir is its grandparent — the journal
# lives beside the run file, not beside the (possibly stale) session id.
_vrc_run_id="$(basename "$_vrc_run_file" .json)"
_vrc_session_dir="$(dirname "$(dirname "$_vrc_run_file")")"

# --- step 4: journal -------------------------------------------------------------
_vrc_journal="$_vrc_session_dir/subagents/workflows/$_vrc_run_id/journal.jsonl"
if [ ! -f "$_vrc_journal" ]; then
  _vrc_indeterminate journal_not_found "no journal at $_vrc_journal"
fi
if [ ! -r "$_vrc_run_file" ]; then
  _vrc_indeterminate run_file_unreadable "cannot read $_vrc_run_file"
fi
if [ ! -r "$_vrc_journal" ]; then
  _vrc_indeterminate journal_unreadable "cannot read $_vrc_journal"
fi

printf 'RELAY_COMPLETENESS_RUN_ID=%s\n' "$_vrc_run_id"
printf 'RELAY_COMPLETENESS_RUN_FILE=%s\n' "$_vrc_run_file"
printf 'RELAY_COMPLETENESS_JOURNAL=%s\n' "$_vrc_journal"
printf 'RELAY_COMPLETENESS_RESOLVED_BY=%s\n' "$_vrc_resolved_by"

# --- predicate -------------------------------------------------------------------
# stdlib json only, matching the repo's Python convention (doc_reference_scan.py,
# validate_*.py). The run file runs to hundreds of KB with embedded script text.
python3 - "$_vrc_run_file" "$_vrc_journal" "$_vrc_run_id" <<'PY'
import json
import sys

RUN_FILE, JOURNAL, RUN_ID = sys.argv[1], sys.argv[2], sys.argv[3]
SIGNAL = "subagent completed without calling StructuredOutput"


def indeterminate(reason, sentence):
    print("RELAY_COMPLETENESS=INDETERMINATE")
    print("RELAY_COMPLETENESS_REASON=%s" % reason)
    print("[relay] completeness could not be verified: %s" % sentence)
    print("[relay] Do not treat INDETERMINATE as a pass — report that completeness "
          "could not be verified.")
    sys.exit(2)


def cell(entry, key):
    """Reporting fields are optional — older run files carry none of them."""
    value = entry.get(key)
    if value is None or value == "":
        return "-"
    return str(value).replace("\n", " ").replace("|", "/")


# --- run file: the scoped agent set ------------------------------------------
try:
    with open(RUN_FILE, "r", encoding="utf-8", errors="replace") as handle:
        run = json.load(handle)
except (OSError, ValueError) as exc:
    indeterminate("run_file_unparseable", "%s is not readable JSON (%s)" % (RUN_FILE, exc))

if not isinstance(run, dict):
    indeterminate("run_file_schema", "%s is not a JSON object" % RUN_FILE)

progress = run.get("workflowProgress")
if not isinstance(progress, list):
    indeterminate("run_file_schema",
                  "%s has no workflowProgress[] array — the run-file format has changed"
                  % RUN_FILE)

# workflowProgress[] is heterogeneous: workflow_phase entries carry no agentId.
agents = {}
for entry in progress:
    if not isinstance(entry, dict) or entry.get("type") != "workflow_agent":
        continue
    agent_id = entry.get("agentId")
    if agent_id:
        agents.setdefault(agent_id, entry)

# --- journal: started without result -----------------------------------------
started, resulted = set(), set()
try:
    with open(JOURNAL, "r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                indeterminate("journal_unparseable",
                              "%s line %d is not valid JSON" % (JOURNAL, number))
            if not isinstance(record, dict):
                indeterminate("journal_unparseable",
                              "%s line %d is not a JSON object" % (JOURNAL, number))
            agent_id = record.get("agentId")
            if not agent_id:
                continue
            if record.get("type") == "started":
                started.add(agent_id)
            elif record.get("type") == "result":
                resulted.add(agent_id)
except OSError as exc:
    indeterminate("journal_unreadable", "%s could not be read (%s)" % (JOURNAL, exc))

# Drift guards, in both directions. The scoped agent set is an INTERSECTION of two files,
# so drift in either one silently empties it — and an empty set has no dead nodes, which
# would exit 0 over a journal that plainly shows a started-with-no-result node. That is
# fail-to-pass, the one thing this script may never do. Each direction gets its own guard.
if agents and not started:
    indeterminate("journal_empty",
                  "%s records no started agents while the run file lists %d agent node(s)"
                  % (JOURNAL, len(agents)))

# Mirror of the above: the run file's discriminator (type == "workflow_agent") or its
# agentId field was renamed, so nothing scoped in even though the journal has agents.
if started and not agents:
    indeterminate("run_file_schema",
                  "%s lists no type=\"workflow_agent\" entries while the journal records "
                  "%d started agent(s) — the run-file discriminator or agentId field has "
                  "changed" % (RUN_FILE, len(started)))

# Neither file names a single agent. `dead` would be empty and this would exit 0 over a run
# that has no node evidence at all — "absent input yields a pass", the one shape this script
# may never produce. A run whose progress list is empty died before its first node started.
if not agents and not started:
    indeterminate("no_agent_nodes",
                  "%s lists no type=\"workflow_agent\" entries and %s records no started "
                  "agents — this run left no node evidence, so completeness cannot be "
                  "confirmed (an empty progress list means it died before its first node)"
                  % (RUN_FILE, JOURNAL))

# Both files have agents but they name none in common: the two id namespaces have
# diverged. In a healthy run every scoped agent has a started record, so an empty
# intersection is drift, never a clean run.
if agents and started and not (set(agents) & started):
    indeterminate("agent_id_mismatch",
                  "%s and %s share no agentId (%d scoped node(s) vs %d started) — the "
                  "identifier namespaces have diverged"
                  % (RUN_FILE, JOURNAL, len(agents), len(started)))

dead = [agent_id for agent_id in started - resulted if agent_id in agents]
dead.sort(key=lambda agent_id: agents[agent_id].get("index", 0))

# --- corroborating signal (report, never decide on) ---------------------------
# Capped at SIGNAL_CAP lines. The signal is corroboration, never the test, so the 21st copy
# of the same harness error adds nothing — and retro-run.sh hands this whole block to its
# parser through the environment, where an uncapped run (400 bytes x an unbounded log) can
# exceed the per-string exec limit and abort the retro outright.
SIGNAL_CAP = 20
logs = run.get("logs")
signal_lines = []
signal_total = 0
if isinstance(logs, list):
    for item in logs:
        text = item if isinstance(item, str) else json.dumps(item)
        if SIGNAL in text:
            signal_total += 1
            if len(signal_lines) < SIGNAL_CAP:
                signal_lines.append(text.replace("\n", " ").strip())

status = run.get("status", "-")
print("RELAY_COMPLETENESS_AGENT_NODES=%d" % len(agents))
print("RELAY_COMPLETENESS_DEAD_NODES=%d" % len(dead))
print("RELAY_COMPLETENESS_HARNESS_STATUS=%s" % status)
print("RELAY_COMPLETENESS_LOG_SIGNAL=%s" % ("present" if signal_lines else "absent"))
if signal_total > len(signal_lines):
    print("RELAY_COMPLETENESS_LOG_SIGNAL_TRUNCATED=%d" % signal_total)

if not dead:
    print("RELAY_COMPLETENESS=COMPLETE")
    print("[relay] All %d agent node(s) returned a result. Proceed." % len(agents))
    if signal_lines:
        for text in signal_lines:
            print("RELAY_LOG_SIGNAL=%s" % text[:400])
        print("[relay] Note: the run log carries the harness's StructuredOutput error, "
              "but every scoped node still returned a result — the predicate, not the "
              "log line, decides.")
    sys.exit(0)

print("RELAY_COMPLETENESS=INCOMPLETE")
for agent_id in dead:
    entry = agents[agent_id]
    print("RELAY_DEAD_NODE=%s | phase=%s | duration=%s | toolCalls=%s | tokens=%s "
          "| lastTool=%s | agentId=%s"
          % (cell(entry, "label"), cell(entry, "phaseTitle"), cell(entry, "durationMs"),
             cell(entry, "toolCalls"), cell(entry, "tokens"), cell(entry, "lastToolName"),
             agent_id))
for text in signal_lines:
    print("RELAY_LOG_SIGNAL=%s" % text[:400])

states = sorted({str(agents[agent_id].get("state", "-")) for agent_id in dead})
print("[relay] %d of %d agent node(s) in %s started and never returned a result."
      % (len(dead), len(agents), RUN_ID))
if states == ["done"]:
    print("[relay] The harness reported status \"%s\" as-is, with every node reading "
          "state: \"done\" — neither field carries the signal." % status)
else:
    print("[relay] The harness reported status \"%s\" as-is; the dead nodes read "
          "state: %s." % (status, ", ".join('"%s"' % s for s in states)))
if signal_lines:
    print("[relay] Corroborating: the run log carries the harness error "
          "\"%s\". It is one cause, not the test." % SIGNAL)
print("[relay] Do not report success. Name each dead node above and the phase output it "
      "was to produce, then re-run those nodes or escalate.")
sys.exit(1)
PY

_vrc_rc=$?
# Normalize: this gate emits 0, 1 or 2 and nothing else. Anything unexpected out of the
# parser (a signal, an import failure) is "I could not verify", never a pass.
case "$_vrc_rc" in
  0|1) exit "$_vrc_rc" ;;
  2)   exit 2 ;;
  *)   _vrc_indeterminate parser_aborted "the run-record parser exited with status $_vrc_rc" ;;
esac
