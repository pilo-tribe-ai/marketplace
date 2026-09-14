"""Guard tests for the ensuring-worktree-isolation skill (spec §5.2/§5.3, §6).

Mirrors the structure-presence style of test_driving_to_done.py / test_l2_skills_present.py:
assert the load-bearing state-machine content on the ACTUAL shipped SKILL.md, robust to
minor wording changes (case-insensitive / structural substrings) but still verifying the
four states, the call-EnterWorktree-exactly-once invariant, the script contract, and the
drive --resume verify-only reconciliation.

parse_frontmatter is loaded via importlib.util (path-explicit) so collection succeeds
regardless of invocation CWD — same pattern as test_l2_skills_present.py.
"""
import importlib.util
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]

_conftest_path = PLUGIN_ROOT / "tests" / "conftest.py"
_cf_spec = importlib.util.spec_from_file_location("conftest", _conftest_path)
_cf = importlib.util.module_from_spec(_cf_spec)
_cf_spec.loader.exec_module(_cf)
parse_frontmatter = _cf.parse_frontmatter

SKILL = PLUGIN_ROOT / "skills" / "ensuring-worktree-isolation" / "SKILL.md"


def _parse():
    assert SKILL.is_file(), "skills/ensuring-worktree-isolation/SKILL.md missing"
    return parse_frontmatter(SKILL)


class TestSkillFilesExist:
    def test_skill_file_exists(self):
        assert SKILL.is_file(), "skills/ensuring-worktree-isolation/SKILL.md missing"


class TestSkillFrontmatter:
    def test_name(self):
        fm, _ = _parse()
        assert fm.get("name") == "ensuring-worktree-isolation"

    def test_description_non_empty(self):
        fm, _ = _parse()
        assert (fm.get("description") or "").strip(), "description must be non-empty"

    def test_user_invocable_false(self):
        fm, _ = _parse()
        assert fm.get("user-invocable") is False, (
            "ensuring-worktree-isolation is an internal skill — must set user-invocable: false"
        )

    def test_body_length(self):
        _, body = _parse()
        assert len(body) > 200, "skill body must be substantive (> 200 chars)"


class TestNotAnL2PatternSkill:
    def test_no_relay_vocab_block(self):
        """It is NOT an L2 pattern skill (same rule as routing/selecting policy skills)."""
        _, body = _parse()
        assert "```relay-vocab" not in body, (
            "ensuring-worktree-isolation must NOT carry a relay-vocab block (not an L1 shape)"
        )


class TestStateMachine:
    def test_all_four_states_documented(self):
        _, body = _parse()
        lower = body.lower()
        for state in ("worktree", "main", "stray", "not-git"):
            assert state in lower, f"body must document the '{state}' state"

    def test_classify_and_create_referenced(self):
        _, body = _parse()
        assert "worktree-preflight.sh" in body, "body must reference worktree-preflight.sh"
        assert "--classify" in body, "body must reference the --classify mode"
        assert "--create" in body, "body must reference the --create mode"

    def test_enter_worktree_path_form(self):
        _, body = _parse()
        assert "EnterWorktree({path:" in body, (
            "body must reference the path-form EnterWorktree({path: ...}) entry"
        )

    def test_ask_user_question_drives_confirmations(self):
        _, body = _parse()
        assert "AskUserQuestion" in body, (
            "body must drive confirmations via AskUserQuestion"
        )


class TestBootstrapContract:
    def test_bootstrap_status_and_failure_contract_documented(self):
        _, body = _parse()
        lower = body.lower()
        assert "relay_wt_bootstrap" in lower
        assert "bootstrap" in lower
        assert "no `RELAY_WT_CREATED_PATH`" in body or "no RELAY_WT_CREATED_PATH" in body
        assert "stderr" in lower
        assert "EnterWorktree" in body

    def test_bootstrap_timeout_guidance_documented(self):
        _, body = _parse()
        lower = body.lower()
        assert "longest timeout" in lower
        assert "bootstrap" in lower


class TestEnterWorktreeOnceInvariant:
    def test_called_exactly_once_never_re_switch(self):
        _, body = _parse()
        lower = body.lower()
        assert "exactly once" in lower, (
            "body must state EnterWorktree is called exactly once per run"
        )
        assert "EnterWorktree" in body, "body must name the EnterWorktree tool"
        assert "re-switch" in lower or "never re-switch" in lower or "never re-enter" in lower, (
            "body must state the session never re-switches worktrees after entry"
        )


class TestDriveResumeReconciliation:
    def test_verify_only_resume_mode(self):
        _, body = _parse()
        assert "verify-only" in body, "body must document the drive --resume verify-only mode"
        assert "--resume" in body, "body must reference the --resume entry"

    def test_workspace_mode_recorded(self):
        _, body = _parse()
        assert "RELAY_DRIVE_WORKSPACE" in body, (
            "body must document the RELAY_DRIVE_WORKSPACE workspace-mode record"
        )
        lower = body.lower()
        assert "worktree" in lower and "in-place" in lower, (
            "body must reconcile both worktree and in-place recorded modes"
        )
        assert "loop-state.md" in body, "body must record the workspace mode into loop-state.md"


class TestSelfContainment:
    def test_no_delegation_to_using_git_worktrees(self):
        _, body = _parse()
        lower = body.lower()
        assert "superpowers:using-git-worktrees" in body, (
            "body must explicitly name superpowers:using-git-worktrees to state non-delegation"
        )
        assert "not delegate" in lower or "does not delegate" in lower or "without delegating" in lower, (
            "body must state it does NOT delegate to superpowers:using-git-worktrees"
        )
