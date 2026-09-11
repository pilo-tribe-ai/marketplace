"""Guard tests for docs/dispatch-contract.md: public envelope contract + reconciliation."""
from pathlib import Path
import pytest

CONTRACT = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "dispatch-contract.md"


class TestPublicEnvelopeContract:
    def test_file_exists(self):
        assert CONTRACT.is_file()

    def test_public_envelope_contract_section_present(self):
        body = CONTRACT.read_text()
        assert "Public envelope contract" in body, \
            "dispatch-contract.md must have a 'Public envelope contract' section"

    def test_role_done_token_frozen(self):
        body = CONTRACT.read_text()
        assert "ROLE_DONE" in body, "frozen token ROLE_DONE must appear in the contract"

    def test_blocked_sentinel_frozen(self):
        body = CONTRACT.read_text()
        assert "BLOCKED:" in body, "frozen sentinel BLOCKED: must appear in the contract"

    def test_needs_decision_sentinel_frozen(self):
        body = CONTRACT.read_text()
        assert "NEEDS_DECISION:" in body, \
            "frozen sentinel NEEDS_DECISION: must appear in the contract"

    def test_key_value_grammar_frozen(self):
        body = CONTRACT.read_text()
        assert "KEY=VALUE" in body or "^[A-Z][A-Z0-9_]*=" in body, \
            "frozen KEY=VALUE envelope grammar must be documented"

    def test_correct_capture_regex(self):
        body = CONTRACT.read_text()
        # The stale regex was ^(ROLE_DONE|[A-Z_]+=)
        # The correct regex is ^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$
        assert "[A-Z][A-Z0-9_]*" in body, \
            "contract must use the correct capture regex pattern [A-Z][A-Z0-9_]*"
        assert "[A-Z_]+=" not in body, \
            "stale capture regex [A-Z_]+= must be removed"

    def test_stale_acpx_max_turns_removed(self):
        body = CONTRACT.read_text()
        assert "ACPX_MAX_TURNS" not in body, \
            "stale ACPX_MAX_TURNS must be removed from dispatch-contract.md"

    def test_stale_acpx_nudge_prompt_removed(self):
        body = CONTRACT.read_text()
        assert "ACPX_NUDGE_PROMPT" not in body, \
            "stale ACPX_NUDGE_PROMPT must be removed from dispatch-contract.md"

    def test_four_explicitly_not_frozen_items(self):
        body = CONTRACT.read_text()
        # Explicitly not frozen: per-role envelope_tokens, ROLE_RESULT
        assert "ROLE_RESULT" in body, \
            "contract must mention ROLE_RESULT (as internal, not frozen)"
