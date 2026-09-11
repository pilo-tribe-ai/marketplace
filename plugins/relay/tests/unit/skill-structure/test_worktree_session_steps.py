"""Structure test for the command-body worktree wiring (spec §7 test 4):

- Step 0.5 — Worktree isolation gate on the 4 MODIFYING commands
  (implement, refine, execute, drive).

The Step 0.0 session-rename preflight was removed (the built-in `/rename` is
UI-only and is not available via `SlashCommand` on any harness, so the step
errored every run); TestSessionRenameRemoved guards against its reintroduction.

State crosses the Bash->Claude boundary as printed stdout; these tests only
assert the command BODY wiring + allowed-tools frontmatter, not runtime behavior.
"""
from conftest import PLUGIN_ROOT, parse_frontmatter

CMD_ROOT = PLUGIN_ROOT / "commands"

ALL_COMMANDS = ["implement", "refine", "execute", "drive", "diagnose", "setup"]
MODIFYING = ["implement", "refine", "execute", "drive"]
READONLY = ["diagnose", "setup"]


def _cmd(name):
    return parse_frontmatter(CMD_ROOT / f"{name}.md")


class TestSessionRenameRemoved:
    def test_no_command_references_session_slug(self):
        for name in ALL_COMMANDS:
            _, body = _cmd(name)
            assert "session-slug.sh" not in body, (
                f"{name}.md: Step 0.0 session-rename must stay removed"
            )
            assert "Step 0.0" not in body, f"{name}.md: Step 0.0 heading must stay removed"

    def test_no_command_allows_slashcommand(self):
        for name in ALL_COMMANDS:
            fm, _ = _cmd(name)
            allowed = str(fm.get("allowed-tools", ""))
            assert "SlashCommand" not in allowed, (
                f"{name}.md: SlashCommand (rename-only) must be removed from allowed-tools"
            )


class TestStep05WorktreeGateModifying:
    def test_modifying_invoke_ensuring_worktree_isolation(self):
        for name in MODIFYING:
            _, body = _cmd(name)
            assert "relay:ensuring-worktree-isolation" in body, (
                f"{name}.md: missing relay:ensuring-worktree-isolation invocation"
            )

    def test_modifying_have_step_0_5_heading(self):
        for name in MODIFYING:
            _, body = _cmd(name)
            assert "Step 0.5" in body, f"{name}.md: missing 'Step 0.5' heading"

    def test_modifying_classify_worktree_preflight(self):
        for name in MODIFYING:
            _, body = _cmd(name)
            assert "worktree-preflight.sh" in body, (
                f"{name}.md: Step 0.5 must source worktree-preflight.sh"
            )
            assert "--classify" in body, (
                f"{name}.md: Step 0.5 must source worktree-preflight.sh --classify"
            )

    def test_modifying_allowed_tools_enterworktree(self):
        for name in MODIFYING:
            fm, _ = _cmd(name)
            allowed = str(fm.get("allowed-tools", ""))
            assert "EnterWorktree" in allowed, (
                f"{name}.md: allowed-tools must include EnterWorktree"
            )

    def test_modifying_allowed_tools_askuserquestion(self):
        # substring check: the harness accepts AskUserQuestion or AskUserQuestion(*)
        # (diagnose.md already carries the scoped form).
        for name in MODIFYING:
            fm, _ = _cmd(name)
            allowed = str(fm.get("allowed-tools", ""))
            assert "AskUserQuestion" in allowed, (
                f"{name}.md: allowed-tools must include AskUserQuestion"
            )

    def test_modifying_allowed_tools_bash(self):
        # Step 0.5 sources worktree-preflight.sh, so every modifying command needs Bash.
        for name in MODIFYING:
            fm, _ = _cmd(name)
            allowed = str(fm.get("allowed-tools", ""))
            assert "Bash" in allowed, f"{name}.md: allowed-tools must include Bash"


class TestExecuteGainsBashFence:
    def test_execute_has_bash_fence(self):
        # execute.md's only ```bash fence is now Step 0.5's worktree-preflight call.
        _, body = _cmd("execute")
        assert "```bash" in body, "execute.md: must retain a ```bash fence"

    def test_execute_allowed_tools_bash(self):
        fm, _ = _cmd("execute")
        allowed = str(fm.get("allowed-tools", ""))
        assert "Bash" in allowed, "execute.md: allowed-tools must include Bash"


class TestDriveResumeVerifyOnly:
    def test_drive_resume_verify_only_note(self):
        _, body = _cmd("drive")
        assert "verify-only" in body, "drive.md: missing --resume verify-only note"
        assert "RELAY_DRIVE_WORKSPACE" in body, (
            "drive.md: must reference RELAY_DRIVE_WORKSPACE for resume reconciliation"
        )


class TestReadOnlyCommandsNoWorktreeGate:
    def test_readonly_do_not_invoke_worktree_skill(self):
        for name in READONLY:
            _, body = _cmd(name)
            assert "relay:ensuring-worktree-isolation" not in body, (
                f"{name}.md: read-only/provisioning — must NOT invoke worktree gate"
            )

    def test_readonly_no_enterworktree(self):
        for name in READONLY:
            fm, _ = _cmd(name)
            allowed = str(fm.get("allowed-tools", ""))
            assert "EnterWorktree" not in allowed, (
                f"{name}.md: read-only — must NOT add EnterWorktree"
            )


class TestSetupRetainsBashAndSkill:
    def test_setup_keeps_bash_and_skill(self):
        # setup.md provisions dependencies — it retains Bash+Skill (SlashCommand,
        # added only for the removed rename step, is gone).
        fm, _ = _cmd("setup")
        allowed = str(fm.get("allowed-tools", ""))
        assert "Bash" in allowed and "Skill" in allowed, (
            "setup.md: must retain Bash+Skill"
        )
