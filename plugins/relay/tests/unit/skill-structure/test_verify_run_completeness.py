"""Unit tests for scripts/verify-run-completeness.sh (spec §0, §2.3, §5).

Every fixture in this file is SYNTHETIC — hand-written minimal JSON that exercises the
documented shape of `wf_<runId>.json` and `journal.jsonl`. No real session transcript,
journal, or run record from ~/.claude/projects/ is copied, read, or derived from here.

The script is driven by pointing $HOME at a tmp_path tree and setting
CLAUDE_CODE_SESSION_ID, exactly as the script's own resolution order (§2.3) allows:

    $HOME/.claude/projects/<slug>/<session>/workflows/wf_<runId>.json
    $HOME/.claude/projects/<slug>/<session>/subagents/workflows/wf_<runId>/journal.jsonl
"""

import json
import os
import subprocess

import pytest

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "verify-run-completeness.sh"

RUN_ID = "wf_test-1"
SESSION = "sess"
SLUG = "-home-user-project"

# The literal harness error that §0 documents as a corroborating-only signal.
LOG_SIGNAL = (
    "agent({schema}): subagent completed without calling StructuredOutput "
    "(after in-conversation nudge)"
)


# --- synthetic fixture builders --------------------------------------------------

def phase(index, title="Implement"):
    """A workflowProgress[] entry of type workflow_phase. Carries NO agentId — the
    array is heterogeneous and phase entries must be skipped when scoping agents."""
    return {"type": "workflow_phase", "index": index, "phaseTitle": title,
            "state": "done"}


def agent(index, agent_id, label, phase_title="Implement", last_tool=None,
          state="done", **extra):
    """A workflowProgress[] entry of type workflow_agent. The reporting fields
    (durationMs/toolCalls/tokens/lastToolName) are OPTIONAL by design — omitting
    lastToolName models the older run-file schema."""
    entry = {"type": "workflow_agent", "index": index, "agentId": agent_id,
             "label": label, "phaseTitle": phase_title, "state": state}
    if last_tool is not None:
        entry["lastToolName"] = last_tool
    entry.update(extra)
    return entry


def started(agent_id):
    return {"type": "started", "agentId": agent_id}


def result(agent_id):
    return {"type": "result", "agentId": agent_id}


def write_run(home, progress, status="completed", logs=None, session=SESSION,
              run_id=RUN_ID, raw=None, slug=SLUG):
    """Materialize $HOME/.claude/projects/<slug>/<session>/workflows/<run_id>.json."""
    path = home / ".claude" / "projects" / slug / session / "workflows" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw)
        return path
    run = {"status": status, "workflowProgress": progress}
    if progress is None:
        run.pop("workflowProgress")
    if logs is not None:
        run["logs"] = logs
    path.write_text(json.dumps(run))
    return path


def write_journal(home, records, session=SESSION, run_id=RUN_ID, raw=None, slug=SLUG):
    """Materialize <sessionDir>/subagents/workflows/<run_id>/journal.jsonl."""
    path = (home / ".claude" / "projects" / slug / session / "subagents" / "workflows"
            / run_id / "journal.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw)
        return path
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def run_gate(home, run_id=RUN_ID, session=SESSION, unset_session=False):
    """Execute the gate against the fixture tree. Mirrors test_check_deps_agent.py::_run."""
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
    """Parse the printed KEY=value block into a dict (last write wins for repeats)."""
    out = {}
    for line in stdout.splitlines():
        line = line.strip()
        if "=" in line and line.split("=", 1)[0].startswith("RELAY_"):
            key, value = line.split("=", 1)
            out[key] = value
    return out


def dead_nodes(stdout):
    return [line.split("=", 1)[1] for line in stdout.splitlines()
            if line.startswith("RELAY_DEAD_NODE=")]


# --- 1. happy path ---------------------------------------------------------------

class TestComplete:
    def test_every_scoped_agent_returned_a_result(self, tmp_path):
        write_run(tmp_path, [
            phase(0, "Plan"),
            agent(1, "a-1", "plan-writer", "Plan", last_tool="StructuredOutput"),
            agent(2, "a-2", "implementer", "Implement", last_tool="StructuredOutput"),
        ])
        write_journal(tmp_path, [
            started("a-1"), result("a-1"),
            started("a-2"), result("a-2"),
        ])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "COMPLETE"
        assert d["RELAY_COMPLETENESS_AGENT_NODES"] == "2"
        assert d["RELAY_COMPLETENESS_DEAD_NODES"] == "0"
        assert d["RELAY_COMPLETENESS_RUN_ID"] == RUN_ID
        assert d["RELAY_COMPLETENESS_RESOLVED_BY"] == "session-id"


# --- 2. the core detection -------------------------------------------------------

class TestIncomplete:
    def test_started_without_result_is_detected(self, tmp_path):
        """THE test. The run file's top-level status is "completed" and every node
        reads state:"done" — the real-world shape, where the harness derives success
        from whether the generated script threw rather than from whether its nodes
        produced output. The predicate must see through both."""
        write_run(tmp_path, [
            phase(0, "Implement"),
            agent(1, "a-1", "implementer", "Implement", last_tool="StructuredOutput",
                  state="done", durationMs=12000, toolCalls=9, tokens=4200),
            agent(2, "a-2", "code-review r1", "Implement", last_tool="Bash",
                  state="done", durationMs=800, toolCalls=1, tokens=0),
        ], status="completed")
        write_journal(tmp_path, [
            started("a-1"), result("a-1"),
            started("a-2"),  # no result — soft-failed
        ])
        r = run_gate(tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "INCOMPLETE"
        assert d["RELAY_COMPLETENESS_DEAD_NODES"] == "1"
        assert d["RELAY_COMPLETENESS_AGENT_NODES"] == "2"
        # The harness's own verdict is reported, and contradicted.
        assert d["RELAY_COMPLETENESS_HARNESS_STATUS"] == "completed"
        # The dead node is named.
        lines = dead_nodes(r.stdout)
        assert len(lines) == 1
        assert "code-review r1" in lines[0]
        assert "agentId=a-2" in lines[0]
        assert "implementer" not in lines[0]
        # And the prose says the harness lied.
        assert 'state: "done"' in r.stdout
        assert "Do not report success" in r.stdout

    def test_multiple_dead_nodes_are_all_named_in_index_order(self, tmp_path):
        write_run(tmp_path, [
            phase(0, "Implement"),
            agent(3, "a-3", "third"),
            agent(1, "a-1", "first"),
            agent(2, "a-2", "second"),
        ])
        write_journal(tmp_path, [started("a-1"), started("a-2"), started("a-3")])
        r = run_gate(tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        labels = [line.split(" | ")[0] for line in dead_nodes(r.stdout)]
        assert labels == ["first", "second", "third"]

    def test_optional_reporting_fields_absent_render_as_dash(self, tmp_path):
        """Older run files carry no durationMs/toolCalls/tokens/lastToolName. A strict
        read would turn a real detection into "could not verify" — it must not."""
        write_run(tmp_path, [agent(1, "a-1", "implementer")])
        write_journal(tmp_path, [started("a-1")])
        r = run_gate(tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        line = dead_nodes(r.stdout)[0]
        assert "duration=-" in line
        assert "toolCalls=-" in line
        assert "tokens=-" in line
        assert "lastTool=-" in line


# --- 3. the mandatory scope restriction (§0) -------------------------------------

class TestScopeRestriction:
    def test_journal_only_agent_is_not_reported_dead(self, tmp_path):
        """§0 scope restriction, MANDATORY. The journal also carries superseded retry
        attempts whose agentId never reaches workflowProgress[]. Counting them produced
        one false positive per affected run — 4 of 38 runs in the real corpus."""
        write_run(tmp_path, [
            phase(0, "Implement"),
            agent(1, "a-1", "implementer"),
        ])
        write_journal(tmp_path, [
            started("a-1"), result("a-1"),
            started("retry-abandoned-1"),  # started, never resulted, NOT in progress[]
        ])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "COMPLETE"
        assert d["RELAY_COMPLETENESS_AGENT_NODES"] == "1"
        assert d["RELAY_COMPLETENESS_DEAD_NODES"] == "0"
        assert dead_nodes(r.stdout) == []

    def test_scoped_dead_node_survives_alongside_unscoped_noise(self, tmp_path):
        """The restriction narrows scope — it must not suppress a real detection."""
        write_run(tmp_path, [
            agent(1, "a-1", "implementer"),
            agent(2, "a-2", "verifier"),
        ])
        write_journal(tmp_path, [
            started("a-1"), result("a-1"),
            started("retry-abandoned-1"),
            started("a-2"),
        ])
        r = run_gate(tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS_DEAD_NODES"] == "1"
        assert "agentId=a-2" in dead_nodes(r.stdout)[0]


# --- 4. heterogeneous workflowProgress[] -----------------------------------------

class TestHeterogeneousArray:
    def test_phase_entries_are_skipped_and_do_not_miscount(self, tmp_path):
        """workflowProgress[] is [{type:"workflow_phase"} x N] ++
        [{type:"workflow_agent"} x M], with NO agentType field anywhere. Phase entries
        carry no agentId and must be skipped cleanly."""
        progress = [phase(i, f"Phase {i}") for i in range(4)]
        progress += [agent(4 + i, f"a-{i}", f"node-{i}") for i in range(3)]
        assert not any("agentType" in e for e in progress)
        write_run(tmp_path, progress)
        write_journal(tmp_path, [rec for i in range(3)
                                 for rec in (started(f"a-{i}"), result(f"a-{i}"))])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        d = parse(r.stdout)
        # 3, not 7 — the four phase entries are not agents.
        assert d["RELAY_COMPLETENESS_AGENT_NODES"] == "3"
        assert d["RELAY_COMPLETENESS"] == "COMPLETE"

    def test_phase_entries_do_not_mask_a_dead_agent(self, tmp_path):
        progress = [phase(0), phase(1), agent(2, "a-1", "implementer"), phase(3)]
        write_run(tmp_path, progress)
        write_journal(tmp_path, [started("a-1")])
        r = run_gate(tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS_AGENT_NODES"] == "1"

    def test_non_dict_progress_entries_are_tolerated(self, tmp_path):
        write_run(tmp_path, ["junk", None, 7, phase(0),
                             agent(1, "a-1", "implementer")])
        write_journal(tmp_path, [started("a-1"), result("a-1")])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS_AGENT_NODES"] == "1"


# --- 5. schema-less positive (lastToolName regression guard) ---------------------

class TestSchemaLessNodesAreComplete:
    def test_nodes_ending_on_bash_or_monitor_with_results_are_complete(self, tmp_path):
        """REGRESSION GUARD — do not reintroduce a `lastToolName != "StructuredOutput"`
        predicate. It was measured wrong: 9 false positives plus 21 unevaluable nodes
        across 426 real nodes. Nodes given no `schema:` legitimately never call
        StructuredOutput and end on Bash/Monitor while carrying perfectly good results.
        The journal's started/result pairing is the predicate; lastToolName is a
        reporting field and never gates the verdict."""
        write_run(tmp_path, [
            phase(0, "Improve"),
            agent(1, "a-1", "plan-fixer r1", "Improve", last_tool="Bash"),
            agent(2, "a-2", "plan-fixer r2", "Improve", last_tool="Monitor"),
            agent(3, "a-3", "plan-fixer r3", "Improve", last_tool="Bash"),
            agent(4, "a-4", "plan-fixer r4", "Improve", last_tool="Monitor"),
            agent(5, "a-5", "plan-fixer r5", "Improve"),  # field absent entirely
        ])
        write_journal(tmp_path, [rec for i in range(1, 6)
                                 for rec in (started(f"a-{i}"), result(f"a-{i}"))])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "COMPLETE"
        assert d["RELAY_COMPLETENESS_AGENT_NODES"] == "5"
        assert d["RELAY_COMPLETENESS_DEAD_NODES"] == "0"
        assert dead_nodes(r.stdout) == []


# --- 6. fail to INDETERMINATE, never to a pass -----------------------------------

def _degradation_cases(home):
    """Build every degradation fixture under `home`, each in its own subtree.
    Returns [(id, kwargs-for-run_gate)]."""
    cases = []

    def tree(name):
        root = home / name
        (root / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
        return root

    ok_progress = [agent(1, "a-1", "implementer")]
    ok_journal = [started("a-1"), result("a-1")]

    # session id unset
    root = tree("session-unset")
    write_run(root, ok_progress)
    write_journal(root, ok_journal)
    cases.append(("session_id_unset", {"home": root, "unset_session": True}))

    # session id set but empty
    root = tree("session-empty")
    write_run(root, ok_progress)
    write_journal(root, ok_journal)
    cases.append(("session_id_empty", {"home": root, "session": ""}))

    # session dir not found (nothing named <session> under projects/)
    root = tree("session-missing")
    write_run(root, ok_progress, session="other-session")
    write_journal(root, ok_journal, session="other-session")
    cases.append(("session_dir_not_found", {"home": root, "run_id": "wf_nonexistent"}))

    # projects root missing entirely
    root = home / "no-projects-root"
    root.mkdir(parents=True, exist_ok=True)
    cases.append(("projects_root_missing", {"home": root}))

    # run file missing (session dir exists, journal exists, run file does not)
    root = tree("run-file-missing")
    write_journal(root, ok_journal)
    cases.append(("run_file_missing", {"home": root}))

    # journal missing
    root = tree("journal-missing")
    write_run(root, ok_progress)
    cases.append(("journal_missing", {"home": root}))

    # a journal line that is not valid JSON
    root = tree("journal-bad-json")
    write_run(root, ok_progress)
    write_journal(root, None,
                  raw=json.dumps(started("a-1")) + "\n{ this is not json\n")
    cases.append(("journal_line_not_json", {"home": root}))

    # a journal line that is valid JSON but not an object
    root = tree("journal-not-object")
    write_run(root, ok_progress)
    write_journal(root, None, raw=json.dumps(started("a-1")) + "\n[1,2,3]\n")
    cases.append(("journal_line_not_object", {"home": root}))

    # run file that is not valid JSON
    root = tree("run-bad-json")
    write_run(root, None, raw="{ not json at all")
    write_journal(root, ok_journal)
    cases.append(("run_file_not_json", {"home": root}))

    # run file that is valid JSON but not an object
    root = tree("run-not-object")
    write_run(root, None, raw="[1, 2, 3]")
    write_journal(root, ok_journal)
    cases.append(("run_file_not_object", {"home": root}))

    # run file with no workflowProgress[] array
    root = tree("run-no-progress")
    write_run(root, None, raw=json.dumps({"status": "completed"}))
    write_journal(root, ok_journal)
    cases.append(("run_file_no_workflow_progress", {"home": root}))

    # run file where workflowProgress is present but not an array
    root = tree("run-progress-not-array")
    write_run(root, None,
              raw=json.dumps({"status": "completed", "workflowProgress": {}}))
    write_journal(root, ok_journal)
    cases.append(("run_file_progress_not_array", {"home": root}))

    # Both files are well-formed and neither names a single agent. This is the subtle
    # one: every check above it passes, `dead` comes out empty, and an empty `dead` is
    # the COMPLETE branch — so this exited 0 over a run that died before its first node
    # started. Absent input yielding a pass is the one shape this script may not have.
    root = tree("no-node-evidence")
    write_run(root, [])
    write_journal(root, [])
    cases.append(("no_agent_nodes", {"home": root}))

    return cases


class TestFailsToIndeterminate:
    """The script's one load-bearing property: a missing, unreadable, or unrecognized
    input always exits 2. There is deliberately no path where absent input yields 0."""

    def test_degradation_sweep_always_exits_two(self, tmp_path):
        for case_id, kwargs in _degradation_cases(tmp_path):
            r = run_gate(**kwargs)
            assert r.returncode == 2, (
                f"{case_id}: expected 2 INDETERMINATE, got {r.returncode}\n"
                f"{r.stdout}{r.stderr}"
            )
            assert "RELAY_COMPLETENESS=INDETERMINATE" in r.stdout, case_id
            assert "Do not treat INDETERMINATE as a pass" in r.stdout, case_id

    def test_degradation_sweep_never_exits_zero(self, tmp_path):
        codes = {case_id: run_gate(**kwargs).returncode
                 for case_id, kwargs in _degradation_cases(tmp_path)}
        assert not [k for k, v in codes.items() if v == 0], codes

    def test_a_run_with_no_node_evidence_is_not_a_pass(self, tmp_path):
        """Named separately from the sweep because it is the only degradation case that
        reaches the verdict logic with both files intact.

        An empty `workflowProgress[]` and an empty journal make the scoped agent set
        empty, and no agents means no dead agents — which is textually the COMPLETE
        branch. Step 4 of all five commands reads that as "proceed", so a run that died
        before its first node started would report as a clean pass.
        """
        write_run(tmp_path, [])
        write_journal(tmp_path, [])
        r = run_gate(tmp_path)
        assert r.returncode == 2, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "INDETERMINATE"
        assert d["RELAY_COMPLETENESS_REASON"] == "no_agent_nodes", d
        assert "All 0 agent node(s)" not in r.stdout, "must not render the COMPLETE line"

    def test_unknown_flag_is_indeterminate(self, tmp_path):
        (tmp_path / ".claude" / "projects").mkdir(parents=True)
        env = dict(os.environ)
        env["HOME"] = str(tmp_path)
        env["CLAUDE_CODE_SESSION_ID"] = SESSION
        r = subprocess.run(["bash", str(SCRIPT), "--nope"],
                           capture_output=True, text=True, env=env)
        assert r.returncode == 2, r.stdout + r.stderr
        assert "RELAY_COMPLETENESS=INDETERMINATE" in r.stdout

    def test_run_id_with_path_separator_is_rejected(self, tmp_path):
        """A caller-supplied id must not escape the projects root."""
        write_run(tmp_path, [agent(1, "a-1", "x")])
        write_journal(tmp_path, [started("a-1"), result("a-1")])
        r = run_gate(tmp_path, run_id="../../etc/passwd")
        assert r.returncode == 2, r.stdout + r.stderr

    def test_help_exits_zero_without_a_verdict(self, tmp_path):
        r = subprocess.run(["bash", str(SCRIPT), "--help"],
                           capture_output=True, text=True)
        assert r.returncode == 0
        assert "RELAY_COMPLETENESS=" not in r.stdout


# --- 7. drift guards in both directions ------------------------------------------

class TestDriftGuards:
    """The scoped agent set is an INTERSECTION of two files, so drift in EITHER file
    silently empties it — and an empty set has no dead nodes, which would exit 0 over a
    journal that plainly shows a dead node. That is fail-to-pass, the one thing this
    script may never do. All three directions must exit 2."""

    def test_journal_records_no_started_agents(self, tmp_path):
        """(a) The run file lists agent nodes but the journal records no `started`
        records at all — the journal's record vocabulary drifted."""
        write_run(tmp_path, [agent(1, "a-1", "implementer"),
                             agent(2, "a-2", "verifier")])
        write_journal(tmp_path, [{"type": "begin", "agentId": "a-1"},
                                 {"type": "end", "agentId": "a-1"}])
        r = run_gate(tmp_path)
        assert r.returncode == 2, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "INDETERMINATE"
        assert d["RELAY_COMPLETENESS_REASON"] == "journal_empty"

    def test_run_file_discriminator_renamed(self, tmp_path):
        """(b) THE MEASURED FAIL-TO-PASS. Before the fix this case returned exit 0
        COMPLETE: the run file's discriminator is renamed (type:"agent" instead of
        "workflow_agent"), so nothing scopes in, the dead set is empty, and the gate
        declared success over a journal that plainly shows a started-with-no-result
        node. It must exit 2."""
        progress = [phase(0), agent(1, "a-1", "implementer"),
                    agent(2, "a-2", "verifier")]
        for entry in progress:
            if entry["type"] == "workflow_agent":
                entry["type"] = "agent"
        write_run(tmp_path, progress)
        write_journal(tmp_path, [started("a-1"), result("a-1"), started("a-2")])
        r = run_gate(tmp_path)
        assert r.returncode == 2, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "INDETERMINATE"
        assert d["RELAY_COMPLETENESS_REASON"] == "run_file_schema"

    def test_agent_id_namespaces_diverge(self, tmp_path):
        """(c) Both files carry agents but share no agentId — the run file's id field
        was renamed, so the intersection is empty for a third reason."""
        progress = [agent(1, "a-1", "implementer"), agent(2, "a-2", "verifier")]
        for entry in progress:
            entry["agentId"] = "node::" + entry["agentId"]
        write_run(tmp_path, progress)
        write_journal(tmp_path, [started("a-1"), result("a-1"), started("a-2")])
        r = run_gate(tmp_path)
        assert r.returncode == 2, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "INDETERMINATE"
        assert d["RELAY_COMPLETENESS_REASON"] == "agent_id_mismatch"

    @pytest.mark.parametrize("case", ["journal_drift", "discriminator_drift",
                                      "id_drift"])
    def test_no_drift_direction_ever_exits_zero(self, tmp_path, case):
        home = tmp_path / case
        (home / ".claude" / "projects").mkdir(parents=True)
        if case == "journal_drift":
            write_run(home, [agent(1, "a-1", "implementer")])
            write_journal(home, [{"type": "begin", "agentId": "a-1"}])
        elif case == "discriminator_drift":
            entry = agent(1, "a-1", "implementer")
            entry["type"] = "agent"
            write_run(home, [entry])
            write_journal(home, [started("a-1")])
        else:
            entry = agent(1, "renamed-1", "implementer")
            write_run(home, [entry])
            write_journal(home, [started("a-1")])
        r = run_gate(home)
        assert r.returncode != 0, f"{case} exited 0 (fail-to-pass): {r.stdout}"
        assert r.returncode == 2, r.stdout + r.stderr


# --- 8. corroborating log signal (reported, never decisive) ----------------------

class TestLogSignal:
    def test_signal_present_but_all_nodes_resulted_is_still_complete(self, tmp_path):
        """The harness error string in logs[] is a corroborating signal only. It
        catches exactly one cause and must never decide the verdict — the predicate
        does. A run whose every scoped node returned a result is COMPLETE even when
        the string is present."""
        write_run(tmp_path, [
            phase(0, "Implement"),
            agent(1, "a-1", "implementer", last_tool="Bash"),
            agent(2, "a-2", "verifier", last_tool="StructuredOutput"),
        ], logs=["some earlier line", LOG_SIGNAL])
        write_journal(tmp_path, [started("a-1"), result("a-1"),
                                 started("a-2"), result("a-2")])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "COMPLETE"
        # Reported...
        assert d["RELAY_COMPLETENESS_LOG_SIGNAL"] == "present"
        assert any(line.startswith("RELAY_LOG_SIGNAL=") for line in r.stdout.splitlines())
        # ...and explicitly stated as non-decisive.
        assert "the predicate, not the log line, decides" in r.stdout

    def test_signal_absent_is_reported_absent(self, tmp_path):
        write_run(tmp_path, [agent(1, "a-1", "implementer")], logs=["nothing to see"])
        write_journal(tmp_path, [started("a-1"), result("a-1")])
        r = run_gate(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS_LOG_SIGNAL"] == "absent"

    def test_signal_accompanies_a_real_detection_without_causing_it(self, tmp_path):
        write_run(tmp_path, [agent(1, "a-1", "implementer"),
                             agent(2, "a-2", "verifier")],
                  logs=[{"level": "error", "message": LOG_SIGNAL}])
        write_journal(tmp_path, [started("a-1"), result("a-1"), started("a-2")])
        r = run_gate(tmp_path)
        assert r.returncode == 1, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS"] == "INCOMPLETE"
        assert d["RELAY_COMPLETENESS_LOG_SIGNAL"] == "present"
        assert "It is one cause, not the test." in r.stdout


# --- resolution order ------------------------------------------------------------

class TestResolution:
    def test_bare_run_id_without_wf_prefix_resolves(self, tmp_path):
        write_run(tmp_path, [agent(1, "a-1", "implementer")])
        write_journal(tmp_path, [started("a-1"), result("a-1")])
        r = run_gate(tmp_path, run_id="test-1")
        assert r.returncode == 0, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS_RUN_ID"] == RUN_ID

    def test_no_run_id_picks_a_run_under_the_session_dir(self, tmp_path):
        write_run(tmp_path, [agent(1, "a-1", "implementer")])
        write_journal(tmp_path, [started("a-1"), result("a-1")])
        r = run_gate(tmp_path, run_id=None)
        assert r.returncode == 0, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS_RUN_ID"] == RUN_ID

    def test_glob_fallback_when_session_id_matches_no_directory(self, tmp_path):
        """§2.3 step 3. The slug is fixed at session launch and EnterWorktree does not
        update it, so the run may live under a session dir the id no longer names.
        runIds are unique, so the glob fallback finds it — and the journal is resolved
        beside the run file, not beside the stale session id."""
        write_run(tmp_path, [agent(1, "a-1", "implementer")], session="real-session")
        write_journal(tmp_path, [started("a-1"), result("a-1")], session="real-session")
        r = run_gate(tmp_path, session="stale-session-id")
        assert r.returncode == 0, r.stdout + r.stderr
        d = parse(r.stdout)
        assert d["RELAY_COMPLETENESS_RESOLVED_BY"] == "runid-glob"
        assert "real-session" in d["RELAY_COMPLETENESS_JOURNAL"]

    def test_glob_fallback_still_detects_a_dead_node(self, tmp_path):
        write_run(tmp_path, [agent(1, "a-1", "implementer")], session="real-session")
        write_journal(tmp_path, [started("a-1")], session="real-session")
        r = run_gate(tmp_path, session="stale-session-id")
        assert r.returncode == 1, r.stdout + r.stderr
        assert parse(r.stdout)["RELAY_COMPLETENESS"] == "INCOMPLETE"
