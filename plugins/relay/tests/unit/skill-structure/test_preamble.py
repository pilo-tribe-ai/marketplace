"""Guard tests for dispatching-acpx-agents/preamble.md: interactive autonomy variant."""
from pathlib import Path
import pytest

PREAMBLE = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "dispatching-acpx-agents" / "preamble.md"


class TestPreambleInteractiveVariant:
    def test_file_exists(self):
        assert PREAMBLE.is_file()

    def test_autonomy_interactive_section_present(self):
        body = PREAMBLE.read_text()
        assert "AUTONOMY=interactive" in body, \
            "preamble.md must document the AUTONOMY=interactive variant"

    def test_needs_decision_token_licensed(self):
        body = PREAMBLE.read_text()
        assert "NEEDS_DECISION:" in body, \
            "preamble.md interactive section must license NEEDS_DECISION:"

    def test_at_most_one_needs_decision_per_turn(self):
        body = PREAMBLE.read_text()
        assert "exactly one" in body or "never more than one" in body or "at most one" in body, \
            "preamble.md must state at most one NEEDS_DECISION: line per turn"

    def test_never_combined_with_role_done(self):
        body = PREAMBLE.read_text()
        assert "ROLE_DONE" in body, "preamble.md must mention ROLE_DONE"
        combined = "never combined" in body or "not combined" in body or "mutually exclusive" in body or "Never combine" in body
        assert combined, \
            "preamble.md must forbid combining NEEDS_DECISION: with ROLE_DONE in the same turn"

    def test_ask_user_question_forbidden(self):
        body = PREAMBLE.read_text()
        assert "AskUserQuestion" in body, \
            "preamble.md must mention AskUserQuestion"
        assert "forbidden" in body or "not available" in body or "must not" in body, \
            "preamble.md must forbid AskUserQuestion in interactive mode"

    def test_role_done_only_when_complete(self):
        body = PREAMBLE.read_text()
        assert "ROLE_DONE" in body
        # Must clarify ROLE_DONE is emitted only on full completion
        assert "complete" in body or "no outstanding" in body, \
            "preamble.md must state ROLE_DONE is emitted only when task is complete"

    def test_fire_and_forget_section_preserved(self):
        body = PREAMBLE.read_text()
        assert "fire-and-forget" in body or "Fire-and-forget" in body, \
            "existing fire-and-forget section must be preserved"
