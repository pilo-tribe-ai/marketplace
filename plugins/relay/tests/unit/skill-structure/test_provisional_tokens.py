"""Guard tests for the two provisional tokens, `DECISION:` and `ESCALATION from …:`
(bg dispatch contract §1.1 — docs/bg-dispatch-contract.md).

These tokens are explicitly NOT part of the frozen envelope set (C2). This file exists
to keep them out of it. It never imports `tests/unit/skill-structure/test_envelope_tokens.py`
— it reads that file as text and parses the `FROZEN_TOKENS` list literal, because
`"DECISION:"` is a SUBSTRING of the frozen token `"NEEDS_DECISION:"`, and a naive
`in`-on-text check would false-positive against the frozen file. Every assertion here
is membership on the parsed list, never substring search.
"""

import ast
import re
from pathlib import Path

from conftest import PLUGIN_ROOT

CONTRACT = PLUGIN_ROOT / "docs" / "bg-dispatch-contract.md"
ENVELOPE_TEST_FILE = (PLUGIN_ROOT / "tests" / "unit" / "skill-structure"
                       / "test_envelope_tokens.py")

EXPECTED_FROZEN = ["ROLE_DONE", "BLOCKED:", "NEEDS_DECISION:",
                   "^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$"]


def _parse_frozen_tokens():
    text = ENVELOPE_TEST_FILE.read_text()
    m = re.search(r"FROZEN_TOKENS\s*=\s*(\[.*?\n\])", text, re.S)
    assert m, "FROZEN_TOKENS list literal not found in test_envelope_tokens.py"
    return ast.literal_eval(m.group(1))


def test_contract_documents_both_provisional_tokens():
    text = CONTRACT.read_text()
    assert "DECISION: " in text
    assert "ESCALATION from " in text


def test_contract_marks_them_provisional():
    text = CONTRACT.read_text()
    # Find the section holding the provisional tokens and confirm "provisional"
    # appears near them, not just anywhere in the document.
    idx = text.find("DECISION: <answer>")
    assert idx != -1, "the DECISION: <answer> token form is not documented"
    window = text[max(0, idx - 500):idx + 1500]
    assert "provisional" in window.lower()


def test_frozen_list_is_exactly_the_four():
    frozen = _parse_frozen_tokens()
    assert frozen == EXPECTED_FROZEN


def test_provisional_tokens_are_not_in_the_frozen_list():
    frozen = _parse_frozen_tokens()
    assert "DECISION:" not in frozen  # membership check, not substring
    assert "ESCALATION from" not in frozen
    assert "ESCALATION from …:" not in frozen


def test_envelope_tokens_file_never_names_escalation():
    text = ENVELOPE_TEST_FILE.read_text()
    assert "ESCALATION" not in text


def test_decision_is_the_downward_reply():
    text = CONTRACT.read_text()
    idx = text.find("DECISION: <answer>")
    assert idx != -1
    window = text[idx:idx + 300]
    assert "NEEDS_DECISION" in window
    assert "reply" in window.lower() or "answer" in window.lower()


def test_escalation_is_distinct_from_blocked():
    text = CONTRACT.read_text()
    idx = text.find("ESCALATION from")
    assert idx != -1
    window = text[idx:idx + 600]
    assert "BLOCKED" in window
    assert "stuck" in window.lower()
