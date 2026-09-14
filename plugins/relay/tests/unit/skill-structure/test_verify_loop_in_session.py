"""The in-session engine of the verify loop — the `--phase pre` / `--phase post` protocol.

Relay 4.32.0. Bash cannot make a tool call, so an in-session node cannot reach its
command from inside `verify-loop-node.sh`. The script therefore splits one step into two
calls and keeps every decision: the gate, the verdict parse, the retry, the commit and the
record all stay in the script, so the node holds no state and makes no judgement.

The risk this engine adds is that a record becomes a CLAIM rather than evidence. With
acpx the script starts the child itself, so a written record proves a step ran. These
tests pin the five guards that stop a fabricated pass from being recorded, and they pin
that the acpx single-call path is unchanged.
"""

import pathlib
import subprocess

import pytest

from conftest import PLUGIN_ROOT, fenced_stub, verify_check_command

NODE = PLUGIN_ROOT / "scripts" / "verify-loop-node.sh"


def run(*args):
    return subprocess.run(
        ["bash", str(NODE), *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
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
    return pathlib.Path(out.stdout.strip()) / "relay-verify"


def pre_reply_path(result):
    """The path `pre` told the caller to write to. The caller never guesses it."""
    for line in result.stdout.splitlines():
        if line.startswith("PRE_REPLY_FILE="):
            return pathlib.Path(line.split("=", 1)[1])
    return None


def pre_command(result):
    """The command text between the two markers, exactly as `pre` printed it."""
    out = result.stdout.splitlines()
    start = out.index("PRE_COMMAND_BEGIN") + 1
    end = out.index("PRE_COMMAND_END")
    return "\n".join(out[start:end])


class TestPrePrintsTheCommand:
    def test_pre_prints_the_command_and_the_reply_path(self, repo):
        run("init", repo, 2)
        r = run("--phase", "pre", "simplify", repo, 1, 2)
        assert r.returncode == 0
        assert pre_command(r) == "/simplify"
        assert pre_reply_path(r) is not None
        assert "NODE_STATUS=pre" in r.stdout

    def test_pre_prints_the_review_command_with_its_flags(self, repo):
        run("init", repo, 2)
        r = run("--phase", "pre", "review", repo, 1, 2)
        assert pre_command(r) == "/code-review medium --fix"

    def test_pre_prints_the_same_verdict_contract_the_acpx_path_sends(self, repo):
        """One contract, both engines. A second copy would drift from the first."""
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        assert pre_command(r) == verify_check_command()

    def test_the_equals_form_of_the_flag_works_too(self, repo):
        run("init", repo, 2)
        r = run("--phase=pre", "simplify", repo, 1, 2)
        assert "NODE_STATUS=pre" in r.stdout


class TestAReplyIsRecorded:
    def test_a_reply_the_caller_wrote_is_recorded_and_committed(self, repo):
        run("init", repo, 2)
        r = run("--phase", "pre", "simplify", repo, 1, 2)
        pre_reply_path(r).write_text("I simplified two functions.\n")
        (repo / "a.txt").write_text("two\n")
        r2 = run("--phase", "post", "simplify", repo, 1, 2)
        assert "NODE_STATUS=ran" in r2.stdout
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "SIMPLIFY=ran" in record
        assert "SIMPLIFY_COMMIT=" in record

    def test_post_fences_the_reply_so_the_caller_cannot_forge_one(self, repo):
        """Guard 4. The parser needs a fence, and the fence has to be the script's:
        the caller writes the reply only, and `post` wraps it."""
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        pre_reply_path(r).write_text("Ran the suite.\n\n**Verdict:** PASS\n")
        r2 = run("--phase", "post", "check", repo, 1, 2)
        assert "NODE_STATUS=done verdict=PASS label=clean" in r2.stdout
        saved = (state_root(repo) / "round-1" / "check.out").read_text()
        assert saved.startswith("POLISH_CMD_OUTPUT_BEGIN")
        assert "POLISH_CMD_OUTPUT_END" in saved


class TestNoReplyIsNeverAPass:
    """Guard 3, the fail-closed rule of this engine."""

    def test_an_absent_reply_is_failed_no_reply(self, repo):
        run("init", repo, 2)
        run("--phase", "pre", "simplify", repo, 1, 2)
        r = run("--phase", "post", "simplify", repo, 1, 2)
        assert "NODE_STATUS=failed:no-reply" in r.stdout
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "SIMPLIFY=failed:no-reply" in record
        assert "SIMPLIFY=ran" not in record

    @pytest.mark.parametrize("blank", ["", "   \n\t\n"], ids=["empty", "whitespace"])
    def test_a_blank_reply_is_failed_no_reply(self, repo, blank):
        """A file holding no visible character is not an answer."""
        run("init", repo, 2)
        r = run("--phase", "pre", "simplify", repo, 1, 2)
        pre_reply_path(r).write_text(blank)
        r2 = run("--phase", "post", "simplify", repo, 1, 2)
        assert "NODE_STATUS=failed:no-reply" in r2.stdout

    def test_a_no_reply_check_leaves_the_run_unverified(self, repo):
        run("init", repo, 2)
        run("--phase", "pre", "check", repo, 1, 2)
        run("--phase", "post", "check", repo, 1, 2)
        r = run("report", repo, 2)
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" not in r.stdout

    def test_a_fix_that_reported_nothing_still_commits_what_landed(self, repo):
        """A half-applied fix is on disk. The next round must read the real tree."""
        root = state_root(repo)
        run("init", repo, 2)
        (root / "state").write_text("LABEL=findings ROUND=1 NOOPS=0 EXIT=continue\n")
        (root / "round-1").mkdir(exist_ok=True)
        (root / "round-1" / "check.out").write_text("**Verdict:** FAIL\n")
        run("--phase", "pre", "fix", repo, 1, 2)
        (repo / "a.txt").write_text("half a fix\n")
        r = run("--phase", "post", "fix", repo, 1, 2)
        assert "NODE_STATUS=failed:no-reply" in r.stdout
        record = (root / "round-1" / "record").read_text()
        assert "FIX=failed:no-reply" in record
        assert "FIX_COMMIT=" in record
        assert "commit-failed" not in record


class TestTheOrderingGuards:
    def test_pre_deletes_a_stale_reply_so_it_cannot_stand_in(self, repo):
        """Guard 1. A file present at `post` time was written after `pre` ran."""
        run("init", repo, 2)
        r = run("--phase", "pre", "simplify", repo, 1, 2)
        path = pre_reply_path(r)
        path.write_text("a reply from an attempt that is over\n")
        run("--phase", "pre", "simplify", repo, 1, 2)
        assert not path.exists(), "pre left a stale reply on disk"

    def test_post_without_a_pre_refuses_and_writes_no_record(self, repo):
        """Guard 2. A post with no pre behind it must add no record line of its own."""
        run("init", repo, 2)
        r = run("--phase", "post", "simplify", repo, 1, 2)
        assert "NODE_STATUS=failed:no-pre" in r.stdout
        record = state_root(repo) / "round-1" / "record"
        assert not record.exists() or "SIMPLIFY=" not in record.read_text()

    def test_a_skipped_pre_survives_a_stray_post(self, repo):
        """The two guards together: the skip record stays the record."""
        root = state_root(repo)
        run("init", repo, 2)
        (root / "state").write_text("LABEL=clean ROUND=1 NOOPS=0 EXIT=clean\n")
        r = run("--phase", "pre", "simplify", repo, 1, 2)
        assert "NODE_STATUS=skipped" in r.stdout
        run("--phase", "post", "simplify", repo, 1, 2)
        record = (root / "round-1" / "record").read_text()
        assert "SIMPLIFY=skipped" in record
        assert "no-reply" not in record

    def test_a_second_pre_after_a_successful_post_changes_nothing(self, repo):
        """Guard 5. A step that already holds its claim refuses re-entry."""
        run("init", repo, 2)
        r = run("--phase", "pre", "simplify", repo, 1, 2)
        path = pre_reply_path(r)
        path.write_text("I simplified two functions.\n")
        run("--phase", "post", "simplify", repo, 1, 2)
        r2 = run("--phase", "pre", "simplify", repo, 1, 2)
        assert path.exists(), "a second pre deleted a completed step's reply"
        assert "NODE_STATUS=already-done" in r2.stdout
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert record.count("SIMPLIFY=") == 1

    def test_a_second_post_does_not_overwrite_the_out_file_or_the_state(self, repo):
        """Guard 5 covers post-side re-entry too, not only pre-side."""
        run("init", repo, 2)
        r = run("--phase", "pre", "review", repo, 1, 2)
        pre_reply_path(r).write_text("Reviewed the diff. No issues found.\n")
        run("--phase", "post", "review", repo, 1, 2)
        out_path = state_root(repo) / "round-1" / "review.out"
        state_path = state_root(repo) / "state"
        out_before = out_path.read_bytes()
        state_before = state_path.read_text()
        r2 = run("--phase", "post", "review", repo, 1, 2)
        assert "NODE_STATUS=already-done" in r2.stdout
        assert out_path.read_bytes() == out_before
        assert state_path.read_text() == state_before

    def test_a_full_re_entry_on_review_leaves_exactly_one_record_line(self, repo):
        run("init", repo, 2)
        r = run("--phase", "pre", "review", repo, 1, 2)
        pre_reply_path(r).write_text("Reviewed the diff. No issues found.\n")
        run("--phase", "post", "review", repo, 1, 2)
        run("--phase", "pre", "review", repo, 1, 2)
        run("--phase", "post", "review", repo, 1, 2)
        record = (state_root(repo) / "round-1" / "record").read_text()
        lines = [line for line in record.splitlines() if line.startswith("REVIEW=")]
        assert len(lines) == 1

    def test_the_report_refuses_a_record_that_holds_two_review_lines(self, repo):
        """The exact 8-line record from run wf_59fede2c-9e2, hand-written. The report
        must count terminal LINES, not the last value, or this run prints clean."""
        root = state_root(repo)
        run("init", repo, 2)
        (root / "round-1" / "record").write_text(
            "SIMPLIFY=ran\n"
            "SIMPLIFY_COMMIT=no changes\n"
            "REVIEW=ran\n"
            "REVIEW_COMMIT=no changes\n"
            "REVIEW=failed:no-reply\n"
            "REVIEW=skipped\n"
            "CHECK=skipped\n"
            "FIX=skipped\n"
        )
        (root / "state").write_text("LABEL=clean ROUND=1 NOOPS=0 EXIT=clean\n")
        r = run("report", repo, 1)
        assert "REVIEW=conflict:" in r.stdout
        assert "RELAY_VERIFY_FAILED=1" in r.stdout
        assert "RELAY_VERIFY_RESULT=unverified" in r.stdout
        assert "RELAY_VERIFY_RESULT=clean" not in r.stdout


class TestTheRetryDecisionStaysInTheScript:
    def test_a_blocked_verdict_asks_for_one_more_reply(self, repo):
        """The one retried shape that can occur in-session. `post` always builds a
        valid fence, so `no-output-fence` — the other acpx-retried shape — cannot."""
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        pre_reply_path(r).write_text("Cannot run the suite.\n\n**Verdict:** BLOCKED\n")
        r2 = run("--phase", "post", "check", repo, 1, 2)
        assert "NODE_RETRY=1" in r2.stdout
        assert "NODE_STATUS=retry" in r2.stdout
        record = state_root(repo) / "round-1" / "record"
        assert not record.exists() or "CHECK=" not in record.read_text()
        # The first reply is kept, so a silent second one cannot erase the evidence.
        assert (state_root(repo) / "round-1" / "check-1.out").exists()

    def test_the_retry_reply_is_read_and_marked_retried(self, repo):
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        path = pre_reply_path(r)
        path.write_text("**Verdict:** BLOCKED\n")
        assert "NODE_RETRY=1" in run("--phase", "post", "check", repo, 1, 2).stdout
        path.write_text("Ran it after all.\n\n**Verdict:** PASS\n")
        r3 = run("--phase", "post", "check", repo, 1, 2)
        assert "verdict=PASS" in r3.stdout
        assert "retried=1" in r3.stdout
        assert "RETRIED=1" in (state_root(repo) / "round-1" / "record").read_text()

    def test_only_one_retry_is_ever_asked_for(self, repo):
        """Two BLOCKED replies end the round; they do not loop."""
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        path = pre_reply_path(r)
        path.write_text("**Verdict:** BLOCKED\n")
        run("--phase", "post", "check", repo, 1, 2)
        path.write_text("**Verdict:** BLOCKED\n")
        r3 = run("--phase", "post", "check", repo, 1, 2)
        assert "NODE_RETRY=1" not in r3.stdout
        assert "label=no-answer" in r3.stdout

    def test_a_reply_with_no_verdict_line_is_not_retried(self, repo):
        """A format the loop cannot change is deterministic: asking again only spends
        another turn. Same rule as the acpx path."""
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        pre_reply_path(r).write_text("Everything looks fine to me.\n")
        r2 = run("--phase", "post", "check", repo, 1, 2)
        assert "NODE_RETRY=1" not in r2.stdout
        assert "label=no-answer" in r2.stdout
        assert "reason=no-verdict-line" in r2.stdout

    def test_a_check_with_no_reply_is_not_retried(self, repo):
        """No reply is the absence of an attempt, not a verdict of a bad shape. One
        record must not stand for both, so it is recorded rather than asked again."""
        run("init", repo, 2)
        run("--phase", "pre", "check", repo, 1, 2)
        r = run("--phase", "post", "check", repo, 1, 2)
        assert "NODE_RETRY=1" not in r.stdout
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "CHECK=failed:no-reply" in record

    def test_the_retry_cycle_still_records_a_verdict_after_the_late_claim(self, repo):
        """REGRESSION for guard 5: the check claim sits after the retry decision, so
        this documented two-post cycle must still end with a recorded verdict."""
        run("init", repo, 2)
        r = run("--phase", "pre", "check", repo, 1, 2)
        path = pre_reply_path(r)
        path.write_text("**Verdict:** BLOCKED\n")
        assert "NODE_RETRY=1" in run("--phase", "post", "check", repo, 1, 2).stdout
        path.write_text("Ran it after all.\n\n**Verdict:** PASS\n")
        run("--phase", "post", "check", repo, 1, 2)
        record = (state_root(repo) / "round-1" / "record").read_text()
        assert "CHECK=ran" in record
        assert "VERDICT=PASS" in record
        assert "LABEL=clean" in record


class TestThePhaseFlagIsValidated:
    @pytest.mark.parametrize("kind", ["init", "report"])
    def test_a_phase_is_rejected_for_a_kind_that_starts_no_child(self, repo, kind):
        """Accepting the flag and ignoring it would let a caller believe it had split
        a step that was never split."""
        r = run("--phase", "pre", kind, repo, 2)
        assert r.returncode == 64
        assert f"phase-not-supported-for-kind:{kind}" in r.stdout

    def test_an_unknown_phase_is_rejected(self, repo):
        r = run("--phase", "sideways", "check", repo, 1, 2)
        assert r.returncode == 64
        assert "bad-phase:sideways" in r.stdout

    def test_an_empty_phase_is_rejected(self, repo):
        r = run("--phase", "--", "check", repo, 1, 2)
        assert r.returncode == 64
        assert "bad-phase:" in r.stdout


class TestTheAcpxPathIsUnchanged:
    def test_without_a_phase_the_script_starts_the_child_itself(self, repo, tmp_path):
        """One call is still one whole step, and it still runs the helper."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        helper = bin_dir / "run-claude-command.sh"
        helper.write_text("#!/usr/bin/env bash\n" + fenced_stub("done") + "\n")
        helper.chmod(0o755)
        staged = tmp_path / "scripts"
        staged.mkdir()
        for name in ("verify-loop-node.sh", "parse-verify-verdict.sh"):
            (staged / name).write_text((PLUGIN_ROOT / "scripts" / name).read_text())
            (staged / name).chmod(0o755)
        (staged / "run-claude-command.sh").write_text(helper.read_text())
        (staged / "run-claude-command.sh").chmod(0o755)
        node = staged / "verify-loop-node.sh"
        subprocess.run(
            ["bash", str(node), "init", str(repo), "2"], capture_output=True, text=True
        )
        r = subprocess.run(
            ["bash", str(node), "simplify", str(repo), "1", "2"],
            capture_output=True,
            text=True,
        )
        assert "NODE_STATUS=ran" in r.stdout
        assert "NODE_STATUS=pre" not in r.stdout
