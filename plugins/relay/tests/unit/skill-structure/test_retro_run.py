"""Unit tests for scripts/retro-run.sh (spec §3, predicate §0, degradation §3.5).

Every fixture in this file is SYNTHETIC — hand-written minimal JSON exercising the
documented shape of `wf_<runId>.json`, `journal.jsonl`, the persisted script text, and
`~/.claude/relay/runs.jsonl`. No real session transcript, journal, run record, or
intent record from ~/.claude/ is copied, read, or derived from here.

The script is driven by pointing $HOME at a tmp_path tree, exactly as its own
resolution order allows:

    $HOME/.claude/projects/<slug>/<session>/workflows/wf_<runId>.json
    $HOME/.claude/projects/<slug>/<session>/workflows/scripts/<name>-wf_<runId>.js
    $HOME/.claude/projects/<slug>/<session>/subagents/workflows/wf_<runId>/journal.jsonl
    $HOME/.claude/relay/runs.jsonl
"""

import json
import os
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "retro-run.sh"

RUN_ID = "wf_retro-1"
SESSION = "sess"
SLUG = "-home-user-project"

LOG_SIGNAL = (
    "agent({schema}): subagent completed without calling StructuredOutput "
    "(after in-conversation nudge)"
)


# --- synthetic fixture builders --------------------------------------------------

def phase(index, title):
    """workflowProgress[] is HETEROGENEOUS — phase entries carry no agentId."""
    return {"type": "workflow_phase", "index": index, "phaseTitle": title,
            "state": "done"}


def agent(index, agent_id, label, phase_title="Implement", **extra):
    entry = {"type": "workflow_agent", "index": index, "agentId": agent_id,
             "label": label, "phaseTitle": phase_title, "state": "done"}
    entry.update(extra)
    return entry


def session_dir(home, slug=SLUG, session=SESSION):
    return home / ".claude" / "projects" / slug / session


def write_run(home, progress, status="completed", phases=None, logs=None,
              run_id=RUN_ID, session=SESSION, slug=SLUG, **extra):
    path = session_dir(home, slug, session) / "workflows" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    run = {"status": status, "workflowProgress": progress}
    if phases is not None:
        run["phases"] = phases
    if logs is not None:
        run["logs"] = logs
    run.update(extra)
    path.write_text(json.dumps(run))
    return path


def write_journal(home, started_ids, resulted_ids, run_id=RUN_ID, session=SESSION,
                  slug=SLUG):
    path = (session_dir(home, slug, session) / "subagents" / "workflows" / run_id
            / "journal.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{"type": "started", "agentId": a} for a in started_ids]
    records += [{"type": "result", "agentId": a} for a in resulted_ids]
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def write_script(home, text, run_id=RUN_ID, session=SESSION, slug=SLUG):
    path = session_dir(home, slug, session) / "workflows" / "scripts" / f"demo-{run_id}.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def write_intent(home, **fields):
    path = home / ".claude" / "relay" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"schema": "relay.run-intent/1", "run_id": RUN_ID,
              "relay_command": "implement", "kind": "feature",
              "intended_spine": [], "gates": {}, "axis_source": "default"}
    record.update(fields)
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")
    return path


def run_retro(home, run_id=RUN_ID, session=SESSION, unset_session=False):
    env = dict(os.environ)
    env["HOME"] = str(home)
    if unset_session:
        env.pop("CLAUDE_CODE_SESSION_ID", None)
    else:
        env["CLAUDE_CODE_SESSION_ID"] = session
    args = ["bash", str(SCRIPT)]
    if run_id is not None:
        args.append(run_id)
    return subprocess.run(args, capture_output=True, text=True, env=env)


def parse(stdout):
    out = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" in line and line.split("=", 1)[0].startswith("RELAY_"):
            key, value = line.split("=", 1)
            out[key] = value
    return out


def row(stdout, label):
    """Return the rendered report row for a comparison label, or ''."""
    for line in stdout.splitlines():
        if line.strip().startswith(label + " "):
            return line.strip()
    return ""


def healthy(home, **kw):
    """A three-node run where every node returned. The baseline for 'no deviation'."""
    write_run(home, [
        phase(0, "Plan"), phase(1, "Implement"),
        agent(2, "a-1", "plan-writer", "Plan"),
        agent(3, "a-2", "implementer", "Implement"),
        agent(4, "a-3", "verifier", "Implement"),
    ], phases=[{"title": "Plan"}, {"title": "Implement"}], **kw)
    write_journal(home, ["a-1", "a-2", "a-3"], ["a-1", "a-2", "a-3"])


# --- 1. the baseline -------------------------------------------------------------

class TestClean:
    def test_healthy_run_is_clean_and_exits_zero(self, tmp_path):
        healthy(tmp_path)
        result = run_retro(tmp_path)
        assert result.returncode == 0, result.stdout
        assert parse(result.stdout)["RELAY_RETRO"] == "CLEAN"
        assert parse(result.stdout)["RELAY_RETRO_DEVIATIONS"] == "0"
        assert "✓" in row(result.stdout, "SILENT")
        assert "✓" in row(result.stdout, "PHASE")

    def test_clean_report_says_a_question_mark_row_is_not_a_pass(self, tmp_path):
        """A retro that skipped a check must never read as having run it."""
        healthy(tmp_path)
        result = run_retro(tmp_path)
        assert "was not\n" in result.stdout or "was not " in result.stdout
        assert "is not a pass" in result.stdout


# --- 2. C3 SILENT — the §0 predicate, delegated to the gate -----------------------

class TestSilentFailures:
    def test_started_without_result_is_a_deviation(self, tmp_path):
        write_run(tmp_path, [
            agent(0, "a-1", "implementer"),
            agent(1, "a-2", "plan-simulator"),
        ], phases=[{"title": "Implement"}])
        write_journal(tmp_path, ["a-1", "a-2"], ["a-1"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert parse(result.stdout)["RELAY_RETRO"] == "DEVIATIONS"
        assert "plan-simulator" in row(result.stdout, "SILENT")
        assert "started, no result" in row(result.stdout, "SILENT")

    def test_dead_nodes_all_at_attempt_one_means_the_gate_did_not_fire(self, tmp_path):
        """Spec §3.8 — the single highest-value finding a retro can produce."""
        write_run(tmp_path, [
            agent(0, "a-1", "implementer", attempt=1),
            agent(1, "a-2", "code-review r1", attempt=1),
        ])
        write_journal(tmp_path, ["a-1", "a-2"], ["a-1"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "the always-on completeness gate did not fire" in result.stdout

    def test_a_retried_dead_node_does_not_accuse_the_gate(self, tmp_path):
        """attempt > 1 means the gate DID fire; the retro must not re-litigate retries."""
        write_run(tmp_path, [
            agent(0, "a-1", "implementer", attempt=1),
            agent(1, "a-2", "code-review r1", attempt=3),
        ])
        write_journal(tmp_path, ["a-1", "a-2"], ["a-1"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "gate did not fire" not in result.stdout

    def test_log_signal_is_quoted_beside_the_dead_node(self, tmp_path):
        write_run(tmp_path, [agent(0, "a-1", "spec-simulator")],
                  logs=["parallel[1] failed: " + LOG_SIGNAL])
        write_journal(tmp_path, ["a-1"], [])
        result = run_retro(tmp_path)
        assert "[log:" in row(result.stdout, "SILENT")


# --- 3. C2 PHASE — declared vs reached -------------------------------------------

class TestPhaseReach:
    def test_declared_phase_with_no_agent_records_never_ran(self, tmp_path):
        """The wf_429eef41-dff shape: phases[] is a static pre-scan of phase()
        literals, so it records phases the run never reached."""
        write_run(tmp_path, [
            agent(0, "a-1", "spec-writer", "Refine Spec"),
        ], phases=[{"title": "Refine Spec"}, {"title": "Refine Plan"},
                   {"title": "Implement"}, {"title": "Verify"}])
        write_journal(tmp_path, ["a-1"], ["a-1"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        line = row(result.stdout, "PHASE")
        assert "3 of 4 declared phases never reached" in line
        assert "Refine Plan" in line and "Implement" in line and "Verify" in line

    def test_all_phases_reached_is_clean(self, tmp_path):
        healthy(tmp_path)
        assert "✓" in row(run_retro(tmp_path).stdout, "PHASE")

    def test_absent_phases_array_degrades_to_unchecked(self, tmp_path):
        write_run(tmp_path, [agent(0, "a-1", "implementer")])
        write_journal(tmp_path, ["a-1"], ["a-1"])
        result = run_retro(tmp_path)
        assert "?" in row(result.stdout, "PHASE")
        assert "declares no phases[]" in row(result.stdout, "PHASE")

    def test_undeclared_phase_that_ran_is_noted_not_failed(self, tmp_path):
        write_run(tmp_path, [
            agent(0, "a-1", "implementer", "Implement"),
            agent(1, "a-2", "polisher", "Polish"),
        ], phases=[{"title": "Implement"}])
        write_journal(tmp_path, ["a-1", "a-2"], ["a-1", "a-2"])
        result = run_retro(tmp_path)
        assert result.returncode == 0
        assert "never declared" in result.stdout and "Polish" in result.stdout


# --- 4. C1 SPINE — requires the intent record ------------------------------------

class TestSpineCoverage:
    def test_without_an_intent_record_spine_is_unknown_not_clean(self, tmp_path):
        healthy(tmp_path)
        result = run_retro(tmp_path)
        assert parse(result.stdout)["RELAY_RETRO_INTENT"] == "absent"
        assert "?" in row(result.stdout, "SPINE")
        assert "unknown" in row(result.stdout, "SPINE")

    def test_a_missing_intent_record_still_leaves_the_run_clean(self, tmp_path):
        """Rung 1 of the degradation ladder is the COMMON case and must stay strong:
        C2/C3/C5 run fully, so a healthy run is still reported clean."""
        healthy(tmp_path)
        assert run_retro(tmp_path).returncode == 0

    def test_intent_record_covering_every_role_is_clean(self, tmp_path):
        healthy(tmp_path)
        write_intent(tmp_path, intended_spine=["plan-writer", "implementer", "verifier"])
        result = run_retro(tmp_path)
        assert result.returncode == 0
        assert "✓" in row(result.stdout, "SPINE")
        assert parse(result.stdout)["RELAY_RETRO_INTENT"] == "present"

    def test_a_spine_role_with_no_agent_node_is_a_deviation(self, tmp_path):
        healthy(tmp_path)
        write_intent(tmp_path,
                     intended_spine=["plan-writer", "implementer", "verifier",
                                     "polish-simplify"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "polish-simplify" in row(result.stdout, "SPINE")

    def test_a_gate_suppressed_role_is_excluded_not_reported_missing(self, tmp_path):
        """`gates` is what stops a legitimately-omitted node reading as a dropped one."""
        healthy(tmp_path)
        write_intent(tmp_path,
                     intended_spine=["plan-writer", "implementer", "verifier",
                                     "polish-simplify"],
                     gates={"polish-simplify": False})
        result = run_retro(tmp_path)
        assert result.returncode == 0, result.stdout
        assert "✓" in row(result.stdout, "SPINE")
        assert "gate-suppressed" in row(result.stdout, "SPINE")

    def test_empty_spine_is_descriptive_not_a_deviation(self, tmp_path):
        """execute/drive have no hard spine and record []; coverage is descriptive."""
        healthy(tmp_path)
        write_intent(tmp_path, relay_command="execute", intended_spine=[])
        result = run_retro(tmp_path)
        assert result.returncode == 0
        assert "no hard spine declared" in row(result.stdout, "SPINE")

    def test_command_and_kind_come_from_the_record_not_the_free_text_name(self, tmp_path):
        """workflowName is free text and identifies no command — that is exactly why
        relay_command and kind are the two fields worth recording."""
        healthy(tmp_path, workflowName="some-made-up-name")
        write_intent(tmp_path, relay_command="implement", kind="bugfix")
        out = parse(run_retro(tmp_path).stdout)
        assert out["RELAY_RETRO_COMMAND"] == "implement"
        assert out["RELAY_RETRO_KIND"] == "bugfix"

    def test_the_matching_run_id_selects_the_record(self, tmp_path):
        healthy(tmp_path)
        write_intent(tmp_path, run_id="wf_someone-else", relay_command="drive")
        write_intent(tmp_path, run_id=RUN_ID, relay_command="refine")
        assert parse(run_retro(tmp_path).stdout)["RELAY_RETRO_COMMAND"] == "refine"


# --- 5. C4 AXIS ------------------------------------------------------------------

class TestAxis:
    def test_axis_is_read_back_from_the_script_consts(self, tmp_path):
        healthy(tmp_path)
        write_script(tmp_path, "const ENGINE = 'acpx'\nconst AGENT = 'hybrid'\n"
                               "// delegate-and-watch\n")
        result = run_retro(tmp_path)
        assert "acpx/hybrid" in row(result.stdout, "AXIS")
        assert parse(result.stdout)["RELAY_RETRO_SCRIPT_SOURCE"] == "file"

    def test_delegating_engine_with_no_delegation_step_is_a_deviation(self, tmp_path):
        """'Asked for acpx, silently ran in-session.'"""
        healthy(tmp_path)
        write_script(tmp_path, "const ENGINE = 'acpx'\nconst AGENT = 'hybrid'\n")
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "every leaf ran in-session" in row(result.stdout, "AXIS")

    def test_unexpected_model_fallback_is_a_deviation(self, tmp_path):
        write_run(tmp_path, [
            agent(0, "a-1", "implementer", model="claude-opus-5",
                  fallbackModel="claude-fable-5"),
        ], phases=[{"title": "Implement"}])
        write_journal(tmp_path, ["a-1"], ["a-1"])
        write_script(tmp_path, "const ENGINE = 'in-session'\nconst AGENT = 'claude'\n")
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "unexpected model fallback" in row(result.stdout, "AXIS")

    def test_no_script_at_all_degrades_to_unchecked(self, tmp_path):
        healthy(tmp_path)
        result = run_retro(tmp_path)
        assert "?" in row(result.stdout, "AXIS")
        assert parse(result.stdout)["RELAY_RETRO_SCRIPT_SOURCE"] == "none"

    def test_missing_script_file_falls_back_to_the_inline_copy(self, tmp_path):
        """Rung 3: the double-persist is a feature — it is what makes a stale
        scriptPath non-fatal."""
        healthy(tmp_path, script="const ENGINE = 'in-session'\nconst AGENT = 'claude'\n")
        result = run_retro(tmp_path)
        assert parse(result.stdout)["RELAY_RETRO_SCRIPT_SOURCE"] == "inline"
        assert "in-session/claude" in row(result.stdout, "AXIS")

    def test_a_script_file_wins_over_the_inline_copy(self, tmp_path):
        healthy(tmp_path, script="const ENGINE = 'inline-wrong'\nconst AGENT = 'x'\n")
        write_script(tmp_path, "const ENGINE = 'in-session'\nconst AGENT = 'claude'\n")
        result = run_retro(tmp_path)
        assert parse(result.stdout)["RELAY_RETRO_SCRIPT_SOURCE"] == "file"
        assert "inline-wrong" not in result.stdout


# --- 6. rung 2 — a scriptPath that moved -----------------------------------------

class TestSlugDivergence:
    def test_recorded_script_path_under_another_session_is_reported(self, tmp_path):
        """EnterWorktree moves cwd mid-session but the project slug is fixed at launch,
        so the two can legitimately diverge — and that divergence is a finding."""
        healthy(tmp_path)
        path = session_dir(tmp_path) / "workflows" / f"{RUN_ID}.json"
        run = json.loads(path.read_text())
        run["scriptPath"] = str(tmp_path / ".claude" / "projects" / "-other-slug"
                                / "othersess" / "workflows" / "scripts" / "x.js")
        path.write_text(json.dumps(run))
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "crossed a worktree boundary" in row(result.stdout, "SLUG")

    def test_a_scriptpath_under_this_session_is_not_a_finding(self, tmp_path):
        healthy(tmp_path)
        path = session_dir(tmp_path) / "workflows" / f"{RUN_ID}.json"
        run = json.loads(path.read_text())
        run["scriptPath"] = str(session_dir(tmp_path) / "workflows" / "scripts" / "x.js")
        path.write_text(json.dumps(run))
        result = run_retro(tmp_path)
        assert result.returncode == 0
        assert row(result.stdout, "SLUG") == ""


# --- 7. C5 COST ------------------------------------------------------------------

class TestCostAndHealth:
    def test_non_completed_status_is_reported(self, tmp_path):
        healthy(tmp_path, status="failed")
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "status: failed" in row(result.stdout, "COST")

    def test_top_level_error_is_reported(self, tmp_path):
        healthy(tmp_path, error="Error: " + LOG_SIGNAL)
        assert "error:" in row(run_retro(tmp_path).stdout, "COST")

    def test_retried_nodes_are_reported_in_aggregate(self, tmp_path):
        write_run(tmp_path, [agent(0, "a-1", "implementer", attempt=2)])
        write_journal(tmp_path, ["a-1"], ["a-1"])
        result = run_retro(tmp_path)
        assert "1 node(s) retried" in row(result.stdout, "COST")

    def test_agent_count_mismatch_is_reported(self, tmp_path):
        healthy(tmp_path, agentCount=9)
        assert "agentCount says 9" in row(run_retro(tmp_path).stdout, "COST")

    def test_a_duration_outlier_is_reported(self, tmp_path):
        write_run(tmp_path, [
            agent(0, "a-1", "one", durationMs=1000),
            agent(1, "a-2", "two", durationMs=1000),
            agent(2, "a-3", "slow", durationMs=90000),
        ])
        write_journal(tmp_path, ["a-1", "a-2", "a-3"], ["a-1", "a-2", "a-3"])
        result = run_retro(tmp_path)
        assert "outlier durationMs" in row(result.stdout, "COST")
        assert "slow" in row(result.stdout, "COST")


# --- 8. degradation ladder + the never-fail-to-clean property ---------------------

class TestDegradation:
    def test_missing_journal_leaves_silent_unchecked_and_never_clean(self, tmp_path):
        """The gate returns INDETERMINATE; the retro must not call that CLEAN."""
        write_run(tmp_path, [agent(0, "a-1", "implementer")],
                  phases=[{"title": "Implement"}])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert parse(result.stdout)["RELAY_RETRO"] == "DEGRADED"
        assert "?" in row(result.stdout, "SILENT")
        assert "UNAUDITED" in result.stdout

    def test_missing_run_file_with_a_journal_is_journal_only_mode(self, tmp_path):
        """Rung 4 — thin, because the journal key is v2:<sha256>, not a label."""
        write_journal(tmp_path, ["a-1", "a-2"], ["a-1"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        out = parse(result.stdout)
        assert out["RELAY_RETRO"] == "DEGRADED"
        assert out["RELAY_RETRO_MODE"] == "journal-only"
        assert out["RELAY_RETRO_JOURNAL_STARTED"] == "2"
        assert out["RELAY_RETRO_JOURNAL_RESULTS"] == "1"
        assert "cannot be" in result.stdout

    def test_journal_only_mode_with_no_loss_is_not_a_deviation(self, tmp_path):
        write_journal(tmp_path, ["a-1"], ["a-1"])
        assert run_retro(tmp_path).returncode == 0

    def test_everything_aged_out_is_unavailable(self, tmp_path):
        """Rung 5 — report that the evidence is gone."""
        (tmp_path / ".claude" / "projects").mkdir(parents=True)
        result = run_retro(tmp_path)
        assert result.returncode == 2
        assert parse(result.stdout)["RELAY_RETRO"] == "UNAVAILABLE"
        assert "aged out" in result.stdout

    def test_run_id_resolves_by_glob_when_the_session_id_is_unset(self, tmp_path):
        """The slug is NEVER derived from $PWD, so a runId must resolve without it."""
        healthy(tmp_path)
        result = run_retro(tmp_path, unset_session=True)
        assert result.returncode == 0
        assert parse(result.stdout)["RELAY_RETRO_RESOLVED_BY"] == "runid-glob"

    def test_last_without_a_session_id_is_unavailable(self, tmp_path):
        healthy(tmp_path)
        result = run_retro(tmp_path, run_id=None, unset_session=True)
        assert result.returncode == 2
        assert parse(result.stdout)["RELAY_RETRO_REASON"] == "no_session_id"

    def test_bare_last_resolves_the_newest_run_in_the_session(self, tmp_path):
        healthy(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), "last"], capture_output=True, text=True,
            env={**os.environ, "HOME": str(tmp_path),
                 "CLAUDE_CODE_SESSION_ID": SESSION})
        assert result.returncode == 0
        assert parse(result.stdout)["RELAY_RETRO_RUN_ID"] == RUN_ID

    def test_a_run_id_with_a_path_separator_is_refused(self, tmp_path):
        healthy(tmp_path)
        result = run_retro(tmp_path, run_id="../../etc/passwd")
        assert result.returncode == 2

    def test_unparseable_run_file_is_unavailable_never_clean(self, tmp_path):
        path = session_dir(tmp_path) / "workflows" / f"{RUN_ID}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        result = run_retro(tmp_path)
        assert result.returncode == 2
        assert parse(result.stdout)["RELAY_RETRO"] == "UNAVAILABLE"

    def test_run_file_without_workflow_progress_is_unavailable(self, tmp_path):
        path = session_dir(tmp_path) / "workflows" / f"{RUN_ID}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "completed"}))
        result = run_retro(tmp_path)
        assert result.returncode == 2
        assert "format has changed" in result.stdout


class TestNeverReportsCleanOverALostNode:
    """The one property this script may never violate: a journal that plainly shows a
    started-with-no-result node must never come back CLEAN, whatever else is missing.
    """

    def _dead_run(self, tmp_path, **kw):
        write_run(tmp_path, [
            agent(0, "a-1", "implementer"),
            agent(1, "a-2", "verifier"),
        ], **kw)
        write_journal(tmp_path, ["a-1", "a-2"], ["a-1"])

    def test_no_phases_no_script_no_intent_still_flags_the_dead_node(self, tmp_path):
        self._dead_run(tmp_path)
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert parse(result.stdout)["RELAY_RETRO"] != "CLEAN"
        assert "verifier" in row(result.stdout, "SILENT")

    def test_status_completed_does_not_mask_the_dead_node(self, tmp_path):
        """The wf_f13a44bd-742 shape: harness said `completed` over dead nodes."""
        self._dead_run(tmp_path, status="completed")
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "verifier" in row(result.stdout, "SILENT")

    def test_an_intent_record_claiming_full_coverage_does_not_mask_it(self, tmp_path):
        self._dead_run(tmp_path)
        write_intent(tmp_path, intended_spine=["implementer", "verifier"])
        result = run_retro(tmp_path)
        assert result.returncode == 1
        assert "✓" in row(result.stdout, "SPINE")      # C1 is satisfied...
        assert "✗" in row(result.stdout, "SILENT")     # ...and C3 still fires.

    def test_a_gate_that_could_not_run_is_not_a_pass(self, tmp_path):
        """C3 delegates the §0 predicate to the gate, so C3 inherits the gate's failure
        modes — including the one where the gate never ran at all.

        The gate normalizes its own verdicts to 0/1/2. Any other code means it did not
        execute (absent, unreadable, killed), and bash reports 127 for the absent case.
        Reading an unrecognized code as the ✓ branch would report CLEAN over a run whose
        soft-failure check never happened, which is precisely the shape this whole
        script exists to detect.

        Driven by copying retro-run.sh alone into a directory with no sibling gate —
        line 244 is its only reference to a file beside itself.
        """
        self._dead_run(tmp_path)
        lonely = tmp_path / "bin"
        lonely.mkdir()
        detached = lonely / SCRIPT.name
        detached.write_text(SCRIPT.read_text())

        env = dict(os.environ)
        env["HOME"] = str(tmp_path)
        env["CLAUDE_CODE_SESSION_ID"] = SESSION
        result = subprocess.run(["bash", str(detached), RUN_ID],
                                capture_output=True, text=True, env=env)

        assert result.returncode == 1, result.stdout + result.stderr
        silent = row(result.stdout, "SILENT")
        assert "?" in silent, silent
        assert "✓" not in silent, "a check that could not run must never render as a pass"
        assert parse(result.stdout)["RELAY_RETRO"] != "CLEAN"


# --- 9. contract -----------------------------------------------------------------

class TestContract:
    def test_help_exits_zero_and_prints_the_three_exit_codes(self, tmp_path):
        result = subprocess.run(["bash", str(SCRIPT), "--help"],
                                capture_output=True, text=True)
        assert result.returncode == 0
        for token in ("0 CLEAN", "1 DEVIATIONS", "2 UNAVAILABLE"):
            assert token in result.stdout

    def test_unknown_flag_is_unavailable_not_a_pass(self, tmp_path):
        result = subprocess.run(["bash", str(SCRIPT), "--wat"],
                                capture_output=True, text=True,
                                env={**os.environ, "HOME": str(tmp_path)})
        assert result.returncode == 2

    def test_the_retro_writes_no_file_into_the_repo(self, tmp_path):
        """A retro must not dirty the branch it is auditing."""
        healthy(tmp_path)
        before = subprocess.run(["git", "status", "--porcelain"], cwd=PLUGIN_ROOT,
                                capture_output=True, text=True).stdout
        run_retro(tmp_path)
        after = subprocess.run(["git", "status", "--porcelain"], cwd=PLUGIN_ROOT,
                               capture_output=True, text=True).stdout
        assert before == after

    def test_the_predicate_is_not_reimplemented_here(self, tmp_path):
        """C3 must delegate to the gate so the §0 predicate has ONE implementation and
        the in-run and post-hoc definitions cannot drift."""
        body = SCRIPT.read_text()
        assert "verify-run-completeness.sh" in body
        assert "RELAY_DEAD_NODE=" in body
        # the predicate's own mechanics must live in the gate, not be copied here
        assert body.count('"type": "started"') == 0
        assert body.count('"type": "result"') == 0
