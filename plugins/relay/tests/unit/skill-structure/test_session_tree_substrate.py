"""Guard tests for the session-tree substrate wiring (spec §Deliverable 3, Doctrine
and Command wiring). `--engine session-tree` is `/relay:implement`-only in v1; the
other three delegating L3 commands must reject it with the standard
engine-not-supported error, and the substrate doc must record it as the second
documented exception to the one-Workflow doctrine."""
import re

import pytest

from conftest import PLUGIN_ROOT, deps_ok_env


def _collapsed(body):
    """Prose wraps at ~88 chars in this repo; a phrase asserted verbatim can
    legally straddle a line break. Collapse runs of whitespace to one space
    before substring checks, so wrapping never causes a false negative."""
    return re.sub(r"\s+", " ", body)

COMMANDS_DIR = PLUGIN_ROOT / "commands"
OTHER_COMMAND_NAMES = ["refine", "execute", "drive"]
# 4.38.0 moved implement's Steps 3.5 and 4 (and the "## Step 3 —" heading's own
# body) into this skill.
SPINE_SKILL = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"


def _body(name):
    text = (COMMANDS_DIR / f"{name}.md").read_text()
    if name == "implement":
        text += "\n" + SPINE_SKILL.read_text()
    return text


def _substrate_doc():
    return (PLUGIN_ROOT / "docs" / "orchestration-substrates.md").read_text()


class TestSubstrateDoc:
    def test_substrate_doc_names_the_second_exception(self):
        body = _substrate_doc()
        assert "session-tree" in body
        assert "/relay:drive" in body
        assert "second" in body.lower()

    def test_doc_no_longer_claims_a_single_substrate(self):
        body = _substrate_doc()
        assert "single orchestration substrate" not in body

    def test_doc_says_no_workflow_is_generated(self):
        body = _substrate_doc()
        assert "generates no Workflow" in body

    def test_doc_says_the_spine_still_governs(self):
        body = _substrate_doc()
        assert "§4.2.1" in body
        assert "spine" in body.lower()

    def test_doc_states_one_workflow_per_session(self):
        body = _collapsed(_substrate_doc()).lower()
        assert "one workflow per session" in body

    def test_doc_keeps_both_existing_exception_headings(self):
        body = _substrate_doc()
        assert "## The `/relay:drive` exception" in body
        assert "## The session-tree exception" in body

    def test_nested_dispatch_section_names_bg_dispatch_sh(self):
        body = _substrate_doc()
        assert "## The nested-dispatch exception" in body
        nested = body.split("## The nested-dispatch exception", 1)[1].split("\n## ", 1)[0]
        assert "skills/dispatching-bg-agents/bg-dispatch.sh" in nested


class TestImplementWiring:
    def test_implement_step_1_branches_on_session_tree(self):
        body = _body("implement")
        assert "session-tree" in body
        assert "orchestrating-session-trees" in body
        assert "terminal" in body.lower()
        assert "end the command turn" in _collapsed(body).lower()
        # Steps 2-5 each carry the precondition
        for step in ("## Step 2", "## Step 3 —", "## Step 3.5", "## Step 4", "## Step 5"):
            section = body.split(step, 1)[1].split("\n## ", 1)[0]
            assert "session-tree" in section, f"{step} is missing the session-tree precondition"

    def test_implement_argument_hint_lists_session_tree(self):
        body = _body("implement")
        hint_line = next(ln for ln in body.splitlines() if ln.startswith("argument-hint:"))
        assert "session-tree" in hint_line


class TestOtherCommandsReject:
    @pytest.mark.parametrize("name", OTHER_COMMAND_NAMES)
    def test_other_three_commands_reject_session_tree(self, name, tmp_path):
        """Issue #110 moved this rejection into scripts/l3-preflight.sh; run it
        for real (refine/execute share one case arm parameterized on $COMMAND,
        so a static grep on the script text cannot see the resolved name)."""
        import subprocess

        body = _body(name)
        assert f'l3-preflight.sh" {name} "$ARGUMENTS"' in body
        result = subprocess.run(
            [
                "bash",
                str(PLUGIN_ROOT / "scripts" / "l3-preflight.sh"),
                name,
                "--engine session-tree",
            ],
            capture_output=True,
            text=True,
            env=deps_ok_env(tmp_path),
        )
        expected = (
            f'[relay] error: engine=session-tree is not supported by /relay:{name} '
            f'(v1 scope: /relay:implement only)'
        )
        assert result.returncode == 1
        assert expected in _collapsed(result.stderr)

    @pytest.mark.parametrize("name", OTHER_COMMAND_NAMES)
    def test_other_three_hints_do_not_list_session_tree(self, name):
        body = _body(name)
        hint_line = next(ln for ln in body.splitlines() if ln.startswith("argument-hint:"))
        assert "session-tree" not in hint_line


class TestStep025:
    def test_step_025_does_not_offer_session_tree(self):
        body = _body("implement")
        assert "session-tree" in body.lower()
        # session-tree must never appear as a Step 0.25 option label
        assert "label `session-tree" not in body


class TestValidateL3:
    def test_validate_l3_knows_the_orchestrator_skill(self):
        src = (PLUGIN_ROOT / "scripts" / "validate_l3_command.py").read_text()
        assert '"orchestrating-session-trees"' in src


class TestAgentRoster:
    def test_roster_doc_holds_the_topology_roles(self):
        body = (PLUGIN_ROOT / "docs" / "agent-roster.md").read_text()
        assert "orchestrator" in body
        assert "operator" in body
        assert "worker" in body

    def test_roster_agent_count_sentence_unchanged(self):
        body = (PLUGIN_ROOT / "docs" / "agent-roster.md").read_text()
        assert "7 agents total" in body
