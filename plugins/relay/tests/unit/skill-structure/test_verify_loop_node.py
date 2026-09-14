"""The verify-loop node script.

The loop's node bodies used to be inline bash inside the generated Workflow script.
Inline bash cannot be unit-tested, so the shape the skill documented and the shape a
run executed could drift apart with nothing to catch it. These tests execute the real
script, so the behaviour the skill promises is the behaviour that runs.

The fail-closed rules are the point of most of them: a node that did not run must never
be recorded as one that passed, and the report must never print `clean` it did not earn.
"""

import os
import shutil
import stat
import subprocess
import time

import pytest

from conftest import PLUGIN_ROOT, TEMPLATE_LINE, fenced_stub, verify_check_command

NODE = PLUGIN_ROOT / "scripts" / "verify-loop-node.sh"


def run(*args):
    return subprocess.run(
        ["bash", str(NODE), *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A real git checkout with one commit, so state lands under a real git dir."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("one\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "feat(core): first")
    return r


def state_root(repo):
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    return __import__("pathlib").Path(out.stdout.strip()) / "relay-verify"


class TestScriptHygiene:
    def test_script_exists_and_is_executable(self):
        assert NODE.is_file()
        assert os.stat(NODE).st_mode & stat.S_IXUSR

    def test_passes_bash_syntax_check(self):
        r = subprocess.run(["bash", "-n", str(NODE)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_unknown_kind_is_64(self, repo):
        r = run("teleport", repo, 1)
        assert r.returncode == 64
        assert "unknown-kind" in r.stdout

    def test_missing_worktree_is_66(self, tmp_path):
        r = run("init", tmp_path / "nope", 3)
        assert r.returncode == 66
        assert "worktree-not-found" in r.stdout

    def test_too_few_arguments_is_64(self, repo):
        r = run("init", repo)
        assert r.returncode == 64


class TestInit:
    def test_seeds_the_state_file(self, repo):
        r = run("init", repo, 3)
        assert r.returncode == 0
        assert "NODE_STATUS=ran" in r.stdout
        assert (state_root(repo) / "state").read_text().strip() == (
            "LABEL= ROUND=1 NOOPS=0 EXIT=continue"
        )

    def test_clears_only_the_round_directories(self, repo):
        sr = state_root(repo)
        (sr / "round-2").mkdir(parents=True)
        (sr / "round-2" / "record").write_text("SIMPLIFY=ran\n")
        keep = sr / "keep-me.txt"
        keep.write_text("not mine to delete\n")

        run("init", repo, 3)

        assert not (sr / "round-2").exists(), "a previous run's round survived the reset"
        assert keep.exists(), (
            "the reset deleted a file outside the round directories; it must clear "
            "round-* only"
        )

    def test_state_lives_under_the_git_dir_not_the_working_tree(self, repo):
        """A scratch directory inside the working tree makes `git status --short`
        non-empty every round, which silently defeats the fix-noop check and lets
        `git add -A` commit the run's own logs."""
        run("init", repo, 3)
        r = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            capture_output=True,
            text=True,
        )
        assert r.stdout.strip() == "", "the loop's own state dirtied the working tree"


class TestAMissingStateFileIsNotASkip:
    """`skipped` says the loop decided to stop. `failed:no-state` says the loop never
    started. Recording both the same way hides a refused init node behind an
    orderly-looking record — which is exactly how one refused node voided a whole
    thirteen-node run.
    """

    @pytest.mark.parametrize("kind", ["simplify", "review", "check", "fix"])
    def test_every_node_reports_no_state(self, repo, kind):
        r = run(kind, repo, 1, 3)
        assert r.returncode == 0
        assert "NODE_STATUS=failed:no-state" in r.stdout
        assert "verify-init-did-not-run" in r.stdout
        assert "skipped" not in r.stdout

    @pytest.mark.parametrize("kind", ["simplify", "review", "check", "fix"])
    def test_the_record_says_no_state_not_skipped(self, repo, kind):
        run(kind, repo, 1, 3)
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "failed:no-state" in record
        assert "=skipped" not in record


class TestATerminalExitSkips:
    @pytest.mark.parametrize("kind", ["simplify", "review", "check"])
    def test_a_finished_round_skips_later_nodes(self, repo, kind):
        run("init", repo, 3)
        (state_root(repo) / "state").write_text("LABEL=clean ROUND=1 NOOPS=0 EXIT=clean\n")
        r = run(kind, repo, 1, 3)
        assert "NODE_STATUS=skipped" in r.stdout
        assert "round-already-ended" in r.stdout

    def test_a_skipped_node_is_never_recorded_as_passed(self, repo):
        run("init", repo, 3)
        (state_root(repo) / "state").write_text("LABEL=clean ROUND=1 NOOPS=0 EXIT=clean\n")
        run("simplify", repo, 1, 3)
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "SIMPLIFY=skipped" in record
        assert "SIMPLIFY=ran" not in record


class TestReport:
    def test_no_state_at_all_is_unverified(self, repo):
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_MISSING=unknown" in r.stdout

    def test_absent_node_keys_are_named_and_counted(self, repo):
        """A node that never ran writes no line. Printing only the keys that are
        present shows a short round as a complete one."""
        run("init", repo, 3)
        r = run("report", repo, 3)
        assert "SIMPLIFY=missing" in r.stdout
        assert "RELAY_VERIFY_MISSING=4" in r.stdout

    def test_a_run_that_did_nothing_is_never_clean(self, repo):
        run("init", repo, 3)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" not in r.stdout

    COMPLETE_RECORD = (
        "SIMPLIFY=ran\nREVIEW=ran\nCHECK=ran\nVERDICT=PASS\nLABEL=clean\nFIX=skipped\n"
    )
    CLEAN_STATE = "LABEL=clean ROUND=1 NOOPS=0 EXIT=clean\n"

    def _round_1(self, repo, record):
        d = state_root(repo) / "round-1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "record").write_text(record)
        (state_root(repo) / "state").write_text(self.CLEAN_STATE)

    def test_clean_is_printed_only_when_the_last_label_is_clean(self, repo):
        """A clean label over a round that recorded every step. This test used to hand
        `report` an init-only tree, where all four keys are missing, and still assert
        `clean` — it pinned the defect that 4.33.0 fixes rather than the rule it names."""
        run("init", repo, 3)
        self._round_1(repo, self.COMPLETE_RECORD)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_MISSING=0" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" in r.stdout

    def test_a_round_with_a_missing_step_is_never_clean(self, repo):
        """Regression for run wf_6f6f4d1a-4d3. Its review node ended its turn between
        `pre` and `post`, so `/code-review medium --fix` never ran and no REVIEW line was
        written. The loop reported the branch clean anyway. A step that wrote no record
        proved nothing, so the run cannot be clean."""
        run("init", repo, 3)
        self._round_1(
            repo, "SIMPLIFY=ran\nCHECK=ran\nVERDICT=PASS\nLABEL=clean\nFIX=skipped\n"
        )
        r = run("report", repo, 3)
        assert "REVIEW=missing" in r.stdout
        assert "RELAY_VERIFY_MISSING=1" in r.stdout
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" not in r.stdout

    def test_a_blocked_clean_names_its_cause(self, repo):
        """A bare `unverified` under a passing verdict reads as a loop that broke. The
        reason line separates the two, so the user reads a cause and not a bare word."""
        run("init", repo, 3)
        self._round_1(repo, "SIMPLIFY=ran\nCHECK=ran\nVERDICT=PASS\nLABEL=clean\n")
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_REASON=incomplete-round steps=2" in r.stdout

    def test_a_complete_clean_run_names_no_cause(self, repo):
        """The reason line prints only on the path the gate blocks, so it never sits
        beside a result it does not explain."""
        run("init", repo, 3)
        self._round_1(repo, self.COMPLETE_RECORD)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_REASON=" not in r.stdout

    def test_a_round_with_a_failed_step_is_never_clean(self, repo):
        """A step that ran and recorded its own failure is not a missing step, so the
        4.33.0 `missing` gate does not catch it. This is a genuinely separate hole."""
        run("init", repo, 3)
        record = self.COMPLETE_RECORD.replace("SIMPLIFY=ran", "SIMPLIFY=failed:no-reply")
        self._round_1(repo, record)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" not in r.stdout
        assert "RELAY_VERIFY_MISSING=0" in r.stdout
        assert "RELAY_VERIFY_FAILED=1" in r.stdout

    def test_a_generic_rc_failure_is_never_clean(self, repo):
        record = self.COMPLETE_RECORD.replace("REVIEW=ran", "REVIEW=failed:2")
        run("init", repo, 3)
        self._round_1(repo, record)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_FAILED=1" in r.stdout

    def test_a_value_outside_the_approved_set_is_never_clean(self, repo):
        """Proof the gate is an allow-list, not a deny-list: a value the script has
        never printed still blocks `clean`."""
        record = self.COMPLETE_RECORD.replace("REVIEW=ran", "REVIEW=weird-new-value")
        run("init", repo, 3)
        self._round_1(repo, record)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_FAILED=1" in r.stdout

    def test_fix_noop_is_approved_for_fix_only(self, repo):
        run("init", repo, 3)
        record = self.COMPLETE_RECORD.replace("FIX=skipped", "FIX=fix-noop")
        self._round_1(repo, record)
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=clean" in r.stdout
        assert "RELAY_VERIFY_FAILED=0" in r.stdout

        record2 = self.COMPLETE_RECORD.replace("SIMPLIFY=ran", "SIMPLIFY=fix-noop")
        self._round_1(repo, record2)
        r2 = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r2.stdout

    def test_a_blocked_clean_names_both_causes(self, repo):
        run("init", repo, 3)
        self._round_1(
            repo,
            "SIMPLIFY=failed:no-reply\nCHECK=ran\nVERDICT=PASS\nLABEL=clean\n",
        )
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_REASON=incomplete-round steps=2 failed-step steps=1" in r.stdout
        assert "RELAY_VERIFY_MISSING=2" in r.stdout
        assert "RELAY_VERIFY_FAILED=1" in r.stdout

    def test_a_failed_step_does_not_turn_findings_into_unverified(self, repo):
        run("init", repo, 3)
        record = self.COMPLETE_RECORD.replace("SIMPLIFY=ran", "SIMPLIFY=failed:2")
        self._round_1(repo, record)
        (state_root(repo) / "state").write_text(
            "LABEL=findings ROUND=1 NOOPS=0 EXIT=findings\n"
        )
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=findings" in r.stdout

    def test_a_no_reply_simplify_ends_the_run_at_the_source(self, repo):
        run("init", repo, 2)
        run("--phase", "pre", "simplify", repo, 1, 2)
        run("--phase", "post", "simplify", repo, 1, 2)
        state = (state_root(repo) / "state").read_text()
        assert "EXIT=unverified" in state

    def test_a_generic_rc_simplify_ends_the_run_at_the_source(self, repo, staged):
        stub(staged, "run-claude-command.sh", "exit 7")
        run_staged(staged, "init", repo, 3)
        run_staged(staged, "simplify", repo, 1, 3)
        state = (state_root(repo) / "state").read_text()
        assert "EXIT=unverified" in state

    def test_findings_is_not_reported_as_clean(self, repo):
        run("init", repo, 3)
        (state_root(repo) / "state").write_text(
            "LABEL=findings ROUND=3 NOOPS=0 EXIT=findings\n"
        )
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=findings" in r.stdout

    def test_a_no_answer_label_is_not_reported_as_clean(self, repo):
        """BLOCKED and SKIP both land here. Neither is a pass."""
        run("init", repo, 3)
        (state_root(repo) / "state").write_text(
            "LABEL=no-answer ROUND=2 NOOPS=0 EXIT=unverified\n"
        )
        r = run("report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout

    def test_the_result_line_is_last(self, repo):
        """Callers read the last line. A trailing diagnostic would be read as the
        result."""
        run("init", repo, 3)
        lines = [l for l in run("report", repo, 3).stdout.strip().splitlines() if l.strip()]
        assert lines[-1].startswith("RELAY_VERIFY_RESULT=")


@pytest.fixture
def staged(tmp_path):
    """The real node script beside stub child helpers.

    `run_child` resolves helpers next to the script, so copying the whole scripts
    directory and overwriting the two child helpers lets a test control exactly how
    long a child session takes without starting one.
    """
    bin_dir = tmp_path / "bin"
    shutil.copytree(PLUGIN_ROOT / "scripts", bin_dir)
    return bin_dir


def stub(bin_dir, name, body):
    p = bin_dir / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(0o755)


def run_staged(bin_dir, *args, seconds="1", env=None):
    e = dict(os.environ, RELAY_VERIFY_NODE_TIMEOUT=str(seconds))
    e.update(env or {})
    return subprocess.run(
        ["bash", str(bin_dir / "verify-loop-node.sh"), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        env=e,
    )


class TestAChildThatOutlivesItsBudget:
    """A node runs as one Bash call, and that call is cut off after ten minutes.

    Before this budget existed, a child that outlived the cut was killed together with
    the node, before the script reached the line that writes the record. The round left
    no trace, and the report read the absent keys as nodes that never ran — which is
    what happened to nine of twelve steps in a real run. The loop still reported
    `unverified`, so nothing was claimed that was not earned, but the record named no
    cause. These tests pin the cause into the record.
    """

    @pytest.mark.parametrize("kind", ["simplify", "review"])
    def test_a_slow_child_is_recorded_as_a_timeout(self, repo, staged, kind):
        """The budget here is one second, and the node does its own work — git calls,
        state reads — before it starts a child. That work can spend the whole second,
        in which case the child never starts and the node correctly reports
        `node-budget-spent-before-child-started` rather than blaming a child. Both are
        timeouts, and which one fires is a race, so pin the pair instead of one of them.
        Naming only one made this test fail about once in twenty runs.
        """
        stub(staged, "run-claude-command.sh", "sleep 30")
        run_staged(staged, "init", repo, 3)
        r = run_staged(staged, kind, repo, 1, 3)
        assert "NODE_STATUS=failed:timeout" in r.stdout
        assert (
            "child-exceeded-1s" in r.stdout
            or "node-budget-spent-before-child-started" in r.stdout
        ), f"a timeout must name one of its two known causes: {r.stdout!r}"

    def test_a_timeout_is_never_recorded_as_a_skip_or_a_pass(self, repo, staged):
        stub(staged, "run-claude-command.sh", "sleep 30")
        run_staged(staged, "init", repo, 3)
        run_staged(staged, "simplify", repo, 1, 3)
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "SIMPLIFY=failed:timeout" in record
        assert "SIMPLIFY=ran" not in record
        assert "=skipped" not in record

    def test_a_timeout_leaves_the_run_unverified(self, repo, staged):
        stub(staged, "run-claude-command.sh", "sleep 30")
        run_staged(staged, "init", repo, 3)
        run_staged(staged, "check", repo, 1, 3)
        state = (state_root(repo) / "state").read_text()
        assert "EXIT=unverified" in state
        assert "LABEL=no-answer" in state

    def test_the_check_node_does_not_retry_after_a_timeout(self, repo, staged):
        """The retry-once rule exists for a BLOCKED or unparseable verdict. Applying it
        to a timeout starts a second full child with the budget already spent, so it can
        only end the same way, one round later.

        Count "no more than one", never "exactly one". The budget here is one second and
        the node does its own work — git calls, state reads — before it starts a child,
        so that work can spend the whole second and the FIRST child is refused too:
        `run_child` returns 124 without running the helper, and the counter file is never
        created. `verify-loop-node.sh` names that path
        `node-budget-spent-before-child-started` and it is correct behaviour, so an exact
        count fails on it — measured at 2 runs in 40 here, and the same race already
        forced `test_a_slow_child_is_recorded_as_a_timeout` above to pin a pair of causes
        instead of one.

        What this test guards is the retry, which is two children, and `<= 1` still
        catches it. The status assertion is what stops a zero-child run from passing
        vacuously: whichever path ran, the node must still record the timeout.
        """
        counter = staged / "calls"
        stub(staged, "run-claude-command.sh", f'echo x >> "{counter}"\nsleep 30')
        run_staged(staged, "init", repo, 3)
        r = run_staged(staged, "check", repo, 1, 3)
        started = counter.read_text().count("x") if counter.exists() else 0
        assert started <= 1, (
            f"the check node started {started} children after a timeout; a timeout must "
            "never be retried"
        )
        assert "NODE_STATUS=failed:timeout" in r.stdout, (
            f"a refused or cut-off child must still be recorded as a timeout: {r.stdout!r}"
        )

    def test_a_timed_out_fix_commits_what_landed(self, repo, staged):
        """A killed fix step still left edits on disk. Leaving them uncommitted makes
        the next round read a tree that does not match what ran."""
        stub(
            staged,
            "run-claude-prompt.sh",
            f'printf "half a fix\\n" > "{repo}/a.txt"\nsleep 30',
        )
        run_staged(staged, "init", repo, 3)
        round_dir = state_root(repo) / "round-1"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "check.out").write_text("findings here\n")
        (state_root(repo) / "state").write_text(
            "LABEL=findings ROUND=1 NOOPS=0 EXIT=continue\n"
        )
        r = run_staged(staged, "fix", repo, 1, 3)
        assert "NODE_STATUS=failed:timeout" in r.stdout
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            capture_output=True,
            text=True,
        )
        assert dirty.stdout.strip() == "", "a timed-out fix left edits uncommitted"

    def test_a_report_over_timed_out_rounds_is_unverified(self, repo, staged):
        stub(staged, "run-claude-command.sh", "sleep 30")
        run_staged(staged, "init", repo, 3)
        run_staged(staged, "simplify", repo, 1, 3)
        r = run_staged(staged, "report", repo, 3)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" not in r.stdout

    def test_zero_turns_the_budget_off(self, repo, staged):
        """Tests and slow machines need an escape hatch, and a child that finishes
        inside its budget must be unaffected by it."""
        stub(staged, "run-claude-command.sh", 'echo "done"')
        run_staged(staged, "init", repo, 3, seconds="0")
        r = run_staged(staged, "simplify", repo, 1, 3, seconds="0")
        assert "NODE_STATUS=ran" in r.stdout
        assert "timeout" not in r.stdout

    def test_a_fast_child_is_unaffected_by_the_budget(self, repo, staged):
        stub(staged, "run-claude-command.sh", 'echo "done"')
        run_staged(staged, "init", repo, 3, seconds="30")
        r = run_staged(staged, "simplify", repo, 1, 3, seconds="30")
        assert "NODE_STATUS=ran" in r.stdout


def last_line(text):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else ""


class TestTheStatusLineIsLast:
    """The node running this script is a model, and it relays what it reads.

    The status line used to sit above 25 to 40 lines of child output. Nodes summarised
    the block instead of relaying the line: run wf_8ad76eec-5ac returned invented
    `detail` values, one of them the literal word `placeholder`, and reported `ran` for
    a step that had run nothing. Putting the line last makes "read the last line" a
    mechanical rule that needs no judgement — the same rule the report node already
    follows for its result line.
    """

    def test_init_ends_on_the_status_line(self, repo):
        """`init` printed the seeded state after its status, so the last line was
        state rather than status."""
        assert last_line(run("init", repo, 3).stdout).startswith("NODE_STATUS=")

    @pytest.mark.parametrize("kind", ["simplify", "review"])
    def test_a_step_that_ran_ends_on_the_status_line(self, repo, staged, kind):
        """The success path is the one that carried a tail of child output. A short
        stub would pass even unfixed, so the stub prints more lines than the tail."""
        stub(staged, "run-claude-command.sh", 'for i in $(seq 40); do echo "line $i"; done')
        run_staged(staged, "init", repo, 3)
        r = run_staged(staged, kind, repo, 1, 3, seconds="30")
        assert last_line(r.stdout).startswith("NODE_STATUS=")

    def test_a_check_that_ran_ends_on_the_status_line(self, repo, staged):
        stub(staged, "run-claude-command.sh", 'for i in $(seq 60); do echo "line $i"; done')
        run_staged(staged, "init", repo, 3)
        r = run_staged(staged, "check", repo, 1, 3, seconds="30")
        assert last_line(r.stdout).startswith("NODE_STATUS=")

    @pytest.mark.parametrize("kind", ["simplify", "review", "check", "fix"])
    def test_a_step_with_no_state_ends_on_the_status_line(self, repo, kind):
        assert last_line(run(kind, repo, 1, 3).stdout).startswith("NODE_STATUS=")

    @pytest.mark.parametrize("kind", ["simplify", "review", "check"])
    def test_a_skipped_step_ends_on_the_status_line(self, repo, kind):
        run("init", repo, 3)
        (state_root(repo) / "state").write_text("LABEL=clean ROUND=1 NOOPS=0 EXIT=clean\n")
        assert last_line(run(kind, repo, 1, 3).stdout).startswith("NODE_STATUS=")

    def test_a_timed_out_step_ends_on_the_status_line(self, repo, staged):
        stub(staged, "run-claude-command.sh", "sleep 30")
        run_staged(staged, "init", repo, 3)
        r = run_staged(staged, "simplify", repo, 1, 3)
        assert last_line(r.stdout).startswith("NODE_STATUS=")

    @pytest.mark.parametrize(
        "args", [("teleport", "R", 1), ("init", "MISSING", 3)], ids=["bad-kind", "no-worktree"]
    )
    def test_an_argument_failure_ends_on_the_status_line(self, repo, tmp_path, args):
        kind, where, n = args
        target = repo if where == "R" else tmp_path / "nope"
        assert last_line(run(kind, target, n).stdout).startswith("NODE_STATUS=")

    @pytest.mark.parametrize("kind", ["init", "simplify", "review", "check", "fix"])
    def test_the_status_line_is_printed_exactly_once(self, repo, staged, kind):
        """Two status lines put the node back in the position of choosing one.

        This runs the paths that reach a child, so it must use stubs: calling the real
        helper would start an acpx session from a unit test.
        """
        stub(staged, "run-claude-command.sh", 'echo "VERIFY: no blocking issues"')
        stub(staged, "run-claude-prompt.sh", 'echo "fixed"')
        run_staged(staged, "init", repo, 3, seconds="30")
        if kind == "init":
            out = run_staged(staged, "init", repo, 3, seconds="30").stdout
        else:
            round_dir = state_root(repo) / "round-1"
            round_dir.mkdir(parents=True, exist_ok=True)
            (round_dir / "check.out").write_text("findings here\n")
            (state_root(repo) / "state").write_text(
                "LABEL=findings ROUND=1 NOOPS=0 EXIT=continue\n"
            )
            out = run_staged(staged, kind, repo, 1, 3, seconds="30").stdout
        assert out.count("NODE_STATUS=") == 1


class TestTheCheckNodeStatesTheVerdictContract:
    """`/verify` is not relay's command. It resolves to whatever the repository
    defines, and a repository that holds its own `verify` skill can prescribe no
    report format at all. Run `wf_918a4deb-aba` sent a bare `/verify`, the child
    answered `## Verify result: productivity v0.7.0 — PASS`, and the parser read
    `no-answer` because that reply holds no verdict token. The check node must send
    the exact line it needs the child to print.
    """

    def test_the_check_node_sends_the_contract_with_the_command(self, repo, staged):
        sent = staged / "sent.txt"
        stub(
            staged,
            "run-claude-command.sh",
            f'printf %s "$3" > {str(sent)!r}\n' + fenced_stub("**Verdict:** PASS"),
        )
        run_staged(staged, "init", repo, 3, seconds="30")
        run_staged(staged, "check", repo, 1, 3, seconds="30")
        text = sent.read_text()
        assert text.startswith("/verify")
        assert TEMPLATE_LINE in text

    def test_the_contract_text_passes_the_slash_only_guard(self, tmp_path):
        contract = verify_check_command()
        helper = NODE.parent / "run-claude-command.sh"
        r = subprocess.run(
            ["bash", str(helper), str(tmp_path / "nope"), "s", contract],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 66, (
            f"the contract failed the slash-only guard: rc={r.returncode} "
            f"stderr={r.stderr!r}"
        )


class TestADeterministicFormatMismatchIsNotRetried:
    """The retry-once rule exists for BLOCKED, a temporary condition: a second
    child can see a different result. A reply that parsed but carried no verdict
    token is deterministic — the same command in the same repository answers in
    the same format — so retrying it only spends a child. That wasted retry is
    what pushed the check node past the caller's 600-second ceiling in run
    `wf_918a4deb-aba`.
    """

    def test_a_reply_with_no_verdict_line_runs_one_child(self, repo, staged):
        counter = staged / "calls"
        stub(
            staged,
            "run-claude-command.sh",
            f'echo x >> {str(counter)!r}\n'
            + fenced_stub("## Verify result: productivity v0.7.0 — PASS"),
        )
        run_staged(staged, "init", repo, 3, seconds="30")
        run_staged(staged, "check", repo, 1, 3, seconds="30")
        assert counter.read_text().count("x") == 1, "the deterministic mismatch was retried"
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "RETRIED=0" in record
        assert "LABEL=no-answer" in record
        assert "REASON=no-verdict-line" in record

    def test_a_reply_with_no_fence_is_still_retried_once(self, repo, staged):
        counter = staged / "calls"
        stub(
            staged,
            "run-claude-command.sh",
            f'echo x >> {str(counter)!r}\necho "no fence here"',
        )
        run_staged(staged, "init", repo, 3, seconds="30")
        run_staged(staged, "check", repo, 1, 3, seconds="30")
        assert counter.read_text().count("x") == 2, "the temporary miss was not retried"
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "RETRIED=1" in record
        assert "REASON=no-output-fence" in record
        assert (state_root(repo) / "round-1" / "check-1.out").exists(), (
            "the retry overwrote the first reply instead of preserving it"
        )

    def test_the_report_names_why_no_verdict_was_read(self, repo, staged):
        stub(
            staged,
            "run-claude-command.sh",
            fenced_stub("## Verify result: productivity v0.7.0 — PASS"),
        )
        run_staged(staged, "init", repo, 3, seconds="30")
        run_staged(staged, "check", repo, 1, 3, seconds="30")
        r = run_staged(staged, "report", repo, 3, seconds="30")
        assert "REASON=no-verdict-line" in r.stdout
        report_lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert report_lines[-1] == "RELAY_VERIFY_RESULT=unverified"


class TestTheNodeBudgetIsADeadline:
    """The budget must bound the whole node, not each child. A per-child limit let
    the check node's retry run two children of `NODE_TIMEOUT` seconds against the
    caller's ceiling, which is exactly the shape that broke run `wf_918a4deb-aba`.
    """

    def test_the_retry_shares_the_nodes_budget(self, repo, staged):
        """A per-child limit gives the retry a fresh budget; a deadline does not.

        The detector is the record, not the clock: with a shared deadline the second
        child runs out of time and the round records `failed:timeout`, while a
        per-child limit lets both children finish and records `CHECK=ran`. That
        separation does not depend on machine load, so the budget here can stay small.

        The stub also counts, because `CHECK=failed:timeout` has a second cause: if the
        FIRST child were killed the round would record it too, and the test would pass
        without the retry ever happening. Requiring that a child finished rules that
        out, and fails loudly instead of passing for the wrong reason.
        """
        marks = staged / "marks"
        stub(
            staged,
            "run-claude-command.sh",
            "sleep 1.2\n"
            + f'echo done >> "{marks}"\n'
            + fenced_stub("**Verdict:** BLOCKED"),
        )
        run_staged(staged, "init", repo, 3, seconds="2")
        run_staged(staged, "check", repo, 1, 3, seconds="2")
        assert marks.is_file() and marks.read_text().count("done") >= 1, (
            "no child ran to completion, so the retry was never reached and this test "
            "proves nothing about the budget"
        )
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "CHECK=failed:timeout" in record, (
            f"the retry got a fresh budget instead of sharing the node's: {record!r}"
        )

    def test_a_timeout_reason_matches_how_many_children_started(
        self, repo, staged, tmp_path
    ):
        """`failed:timeout` has two causes and must name the right one.

        A retry the deadline refused never started a child, so reporting
        `child-exceeded-<N>s` for it is narration, not evidence. Which branch fires
        depends on where the node's start lands inside a second — `date +%s` floors,
        so a child that finishes late in the last second can leave `remaining` at 0.
        Fixing that timing would make the test flaky, so the stub records every start
        and every finish instead, and the reason has to match what actually happened.
        """
        counter = tmp_path / "children"
        stub(
            staged,
            "run-claude-command.sh",
            f'echo start >> "{counter}"\n'
            "sleep 1.6\n"
            f'echo done >> "{counter}"\n'
            + fenced_stub("**Verdict:** BLOCKED"),
        )
        run_staged(staged, "init", repo, 3, seconds="30")
        r = run_staged(staged, "check", repo, 1, 3, seconds="2")
        marks = counter.read_text().split()
        starts, dones = marks.count("start"), marks.count("done")
        assert "NODE_STATUS=failed:timeout" in r.stdout, r.stdout
        if starts == 1 and dones == 1:
            assert "reason=node-budget-spent-before-child-started" in r.stdout, (
                "the first child finished and no second child started, so the budget "
                f"was spent before the retry — the reason must not blame a child: {r.stdout!r}"
            )
        else:
            assert "reason=child-exceeded-2s" in r.stdout, (
                f"a child was killed ({starts} started, {dones} finished), so the "
                f"reason must say so: {r.stdout!r}"
            )

    @pytest.mark.parametrize("value", ["0900", "00"])
    def test_a_budget_with_a_leading_zero_is_read_as_base_ten(self, repo, staged, value):
        """Digits alone are not enough, because bash reads a leading zero as octal.

        `0900` is not a legal octal number: the deadline arithmetic fails, the deadline
        is never set, and `set -u` ends `run_child` on its first read of it. The node
        reported `failed:1` and started no child — a valid 900-second budget became an
        immediate hard failure. `00` is the same hole from the other side: it is not the
        string `0`, so the off-switch misses it and the deadline lands on the current
        second, which refuses every child before it starts.

        `0600` is not here. It shrinks to 384 seconds, which is still long enough for a
        stub child to run, so this shape of test cannot see it. The shrink is measured in
        `test_a_leading_zero_budget_is_not_shrunk_to_octal` instead.
        """
        stub(staged, "run-claude-command.sh", 'echo "done"')
        run_staged(staged, "init", repo, 3, seconds="30")
        r = run_staged(staged, "simplify", repo, 1, 3, seconds=value)
        report_lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert report_lines, f"the node ended with no output at all: stderr={r.stderr!r}"
        assert report_lines[-1].startswith("NODE_STATUS="), (
            f"budget {value!r} ended the node without a status line: {r.stdout!r} "
            f"stderr={r.stderr!r}"
        )
        assert "NODE_STATUS=ran" in r.stdout, (
            f"budget {value!r} refused a child that had time: {r.stdout!r}"
        )

    @pytest.mark.parametrize(
        "value,seconds",
        [("010", "10"), ("0600", "600"), ("0900", "900"), ("abc", "540")],
    )
    def test_the_budget_the_node_computes_is_the_budget_it_was_given(
        self, repo, staged, value, seconds
    ):
        """A leading zero makes bash read the budget as octal: `010` is 8, `0600` is 384.

        A value that is no number at all falls back to 540, and that number matters too.

        Waiting for a child to be killed would prove this only for a budget small enough
        to wait out, and `0600` is not. So the test reads the number the node computed
        instead: `run_child` calls `timeout -k 10 <remaining>`, resolved from PATH, so a
        stub `timeout` on PATH records the budget it was asked for and then runs the real
        child. That measures the deadline arithmetic directly and costs no wall-clock.
        """
        asked = staged / "asked-seconds"
        stub(staged, "run-claude-command.sh", 'echo "done"')
        stub(
            staged,
            "timeout",
            # `timeout -k 10 <secs> <cmd> ...` — record <secs>, then run the command.
            f'printf "%s" "$3" > {str(asked)!r}\n'
            "shift 3\n"
            'exec "$@"',
        )
        run_staged(staged, "init", repo, 3, seconds="30")
        env = {"PATH": f"{staged}:{os.environ['PATH']}"}
        r = run_staged(staged, "simplify", repo, 1, 3, seconds=value, env=env)
        assert "NODE_STATUS=ran" in r.stdout, r.stdout
        # Prove the stub was actually used before reading what it wrote. If a later
        # change calls timeout by absolute path, or reorders its flags, the stub is
        # bypassed and records nothing — and a test that then read a missing file
        # would report a pass while proving nothing at all.
        assert asked.is_file() and asked.read_text().strip(), (
            "the timeout stub recorded nothing, so the node never called `timeout` "
            "through PATH and this test proves nothing"
        )
        # The node asks for the time LEFT, not the budget, so a call that lands on the
        # far side of a second asks for one less. Allow that one second. It costs the
        # test nothing: every wrong reading here is an octal one, and those are far
        # away — 8 against 10, 384 against 600.
        want = int(seconds)
        got = int(asked.read_text())
        assert want - 1 <= got <= want, (
            f"budget {value!r} must mean {want} seconds, not its octal reading; "
            f"the node asked timeout for {got}"
        )

    def test_a_budget_that_is_not_a_number_says_so_and_carries_on(self, repo, staged):
        """The fallback VALUE is pinned by the parametrized test above. What is left to
        prove here is that the node warns and still ends on a status line, rather than
        rejecting the budget by dying."""
        stub(staged, "run-claude-command.sh", 'echo "done"')
        run_staged(staged, "init", repo, 3, seconds="30")
        r = run_staged(staged, "simplify", repo, 1, 3, seconds="abc")
        report_lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert report_lines, "the node ended with no output at all"
        assert report_lines[-1].startswith("NODE_STATUS="), (
            f"a non-numeric budget must still end on a status line: {r.stdout!r} "
            f"stderr={r.stderr!r}"
        )
        assert "NODE_STATUS=ran" in r.stdout
        assert "not a whole number of seconds" in r.stderr, (
            f"a rejected budget must say so: {r.stderr!r}"
        )
