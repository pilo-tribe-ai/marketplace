"""Guard tests for the bg-sessions wiring in the four delegating L3 commands (spec
§Deliverable 2, Dispatch — "Command wiring: ... Without this edit, --engine
bg-sessions parses but every command's wiring note falls through to the in-session
path — a silent, unreported no-op")."""
import re
from pathlib import Path

import pytest

from conftest import PLUGIN_ROOT

COMMANDS_DIR = PLUGIN_ROOT / "commands"
COMMAND_NAMES = ["implement", "refine", "execute", "drive"]


def _body(name):
    return (COMMANDS_DIR / f"{name}.md").read_text()


def _collapsed(body):
    """Prose wraps at ~88 chars in this repo; a phrase asserted verbatim can
    legally straddle a line break. Collapse runs of whitespace to one space
    before substring checks, so wrapping never causes a false negative."""
    return re.sub(r"\s+", " ", body)


class TestBgSessionsWiring:
    @pytest.mark.parametrize("name", COMMAND_NAMES)
    def test_argument_hint_lists_bg_sessions(self, name):
        body = _body(name)
        hint_line = next(ln for ln in body.splitlines() if ln.startswith("argument-hint:"))
        assert "bg-sessions" in hint_line

    @pytest.mark.parametrize("name", COMMAND_NAMES)
    def test_wiring_note_has_a_bg_arm(self, name):
        body = _body(name)
        assert "## Delegation wiring note" in body
        note = body.split("## Delegation wiring note", 1)[1]
        assert "bg-sessions" in note
        assert "dispatching-bg-agents" in note

    @pytest.mark.parametrize("name", COMMAND_NAMES)
    def test_step_025_offers_bg_sessions(self, name):
        body = _body(name)
        assert "bg-sessions (claude)" in body

    @pytest.mark.parametrize("name", COMMAND_NAMES)
    def test_step_025_keeps_the_first_two_options(self, name):
        """Both engines stay on the menu everywhere. Only the label carrying
        `(default)` moves: 4.47.0 made acpx the default for /relay:implement, so
        that command marks acpx and offers in-session under a plain label."""
        body = _body(name)
        assert "acpx (hybrid)" in body
        if name == "implement":
            assert "acpx (default)" in body
            assert "in-session (claude)" in body
        else:
            assert "in-session (default)" in body

    @pytest.mark.parametrize("name", COMMAND_NAMES)
    def test_bg_re_resolution_block_present(self, name):
        """Issue #110: the Step 0.25 re-resolution block collapsed into one
        call to scripts/l3-preflight.sh's --axis-only mode."""
        body = _body(name)
        assert 'l3-preflight.sh" --axis-only bg-sessions claude --source prompt' in body

    @pytest.mark.parametrize("name", COMMAND_NAMES)
    def test_step0_invariant_prose_names_bg_sessions(self, name):
        body = _body(name)
        assert "bg-sessions⇒claude" in body


class TestValidateL3KnowsTheNewSkill:
    def test_validate_l3_knows_the_new_skill(self):
        src = (PLUGIN_ROOT / "scripts" / "validate_l3_command.py").read_text()
        assert '"dispatching-bg-agents"' in src


WORDING = ("Finish your current turn and stop. Do not start new work. "
           "Do not message any other session.")

CONTRACT = PLUGIN_ROOT / "docs" / "bg-dispatch-contract.md"
SPINE_SKILL = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"
SESSION_TREE_SKILL = PLUGIN_ROOT / "skills" / "orchestrating-session-trees" / "SKILL.md"


def _end_of_run_section():
    """Slice `## End of run` from its heading to the next `## ` heading, so a
    mention elsewhere in the file cannot satisfy an assertion about this section."""
    body = SESSION_TREE_SKILL.read_text()
    start = body.index("## End of run")
    rest = body[start:]
    end = rest.index("\n## ", 1)
    return rest[:end]


class TestKeepSessionsWiring:
    def test_argument_hint_lists_keep_sessions(self):
        body = _body("implement")
        hint_line = next(ln for ln in body.splitlines() if ln.startswith("argument-hint:"))
        assert "--keep-sessions" in hint_line

    def test_error_branch_names_both_bg_engines(self):
        """The branch lives in scripts/l3-preflight.sh, not inline in the command.
        Issue #110 moved every Step 0 `case`/`if` shape into that script, because a
        worktree-isolated session refuses them inline."""
        body = _collapsed((PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text())
        assert "--keep-sessions" in body
        assert "bg-sessions" in body
        assert "session-tree" in body
        assert "creates none" in body

    def test_step1_strip_sentence_mentions_keep_sessions(self):
        body = _collapsed(_body("implement"))
        assert "minus `--keep-sessions`" in body

    def test_allowed_tools_lists_send_message(self):
        body = _body("implement")
        frontmatter = body.split("---", 2)[1]
        assert "allowed-tools: Bash, EnterWorktree, AskUserQuestion, Workflow, Skill, SendMessage" in frontmatter

    def test_spine_skill_names_bg_cleanup_script(self):
        body = SPINE_SKILL.read_text()
        assert "bg-cleanup.sh" in body

    def test_spine_skill_declares_keep_sessions_input(self):
        body = SPINE_SKILL.read_text()
        assert "`keep_sessions`" in body

    def test_spine_skill_states_all_four_cleanup_exit_codes(self):
        body = SPINE_SKILL.read_text()
        assert "| `0` |" in body
        assert "| `1` |" in body
        assert "| `2` |" in body
        assert "| `3` |" in body

    def test_pinned_finish_and_stop_wording(self):
        first = WORDING.splitlines()[0]
        assert WORDING in CONTRACT.read_text()
        assert re.match(r"^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$", first) is None
        assert not first.startswith(("BLOCKED:", "NEEDS_DECISION:"))


class TestSessionTreeCleanupWiring:
    def test_end_of_run_section_names_bg_cleanup_script(self):
        section = _end_of_run_section()
        assert "bg-cleanup.sh" in section

    def test_end_of_run_states_retry_loop_and_naming_rule(self):
        collapsed = _collapsed(_end_of_run_section())
        assert "retry loop" in collapsed
        assert "in the run's final report" in collapsed

    def test_retry_phrase_precedes_naming_phrase(self):
        collapsed = _collapsed(_end_of_run_section())
        retry = "retry loop"
        naming = "in the run's final report"
        assert collapsed.index(retry) < collapsed.index(naming)
