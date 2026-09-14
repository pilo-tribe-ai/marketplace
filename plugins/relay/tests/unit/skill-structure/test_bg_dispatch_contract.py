"""Doc guard for docs/bg-dispatch-contract.md (spec Deliverable 1).

Prose is source here: this module pins the load-bearing claims of the contract doc so
a future edit cannot quietly drop one.
"""

import re

from conftest import PLUGIN_ROOT

CONTRACT = PLUGIN_ROOT / "docs" / "bg-dispatch-contract.md"

FROZEN_TOKENS = ["ROLE_DONE", "BLOCKED:", "NEEDS_DECISION:",
                 "^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$"]

CODE_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:sh|py|js|md|json|yaml))`")


def _text():
    assert CONTRACT.is_file(), "docs/bg-dispatch-contract.md is missing"
    return CONTRACT.read_text()


def test_doc_exists_and_is_substantial():
    text = _text()
    assert len(text) > 2000


def test_holds_the_four_frozen_tokens_verbatim():
    text = _text()
    for token in FROZEN_TOKENS:
        assert token in text, f"frozen token {token!r} missing from the contract doc"


def test_adds_no_token_to_the_frozen_set():
    text = _text().lower()
    assert "frozen set is unchanged" in text or "no token to the frozen" in text \
        or "frozen envelope set" in text


def test_naming_grammar_block_present():
    text = _text()
    assert "<product>-<role>-<goal>-<runid>" in text


def test_runid_is_mandatory_and_says_why():
    text = _text()
    assert "Mandatory" in text
    assert "S4-3" in text


def _mapping_table_slice():
    """Slice the mapping table itself out of the doc — the ### Permission-mode
    mapping heading plus the pipe-delimited rows that follow it, and no more. A
    slice that ran to the next markdown heading would also swallow the raw-argument
    paragraph below the table, and that paragraph keeps the word `bypassPermissions`
    on purpose; the guard here is on the table rows themselves (spec §1.6)."""
    text = _text()
    heading = "### Permission-mode mapping"
    start = text.index(heading)
    lines = text[start:].splitlines()
    kept = [lines[0]]
    seen_table = False
    for line in lines[1:]:
        if line.startswith("|"):
            seen_table = True
            kept.append(line)
        elif seen_table:
            break
        else:
            kept.append(line)
    return "\n".join(kept)


def test_permission_mode_mapping_rows():
    slice_ = _mapping_table_slice()
    # approve-all now maps to `auto` inside the mapping table.
    assert re.search(r"`approve-all`\s*\|\s*`auto`", slice_), \
        f"approve-all row does not map to `auto`:\n{slice_}"
    assert "approve-reads" in slice_ and "`plan`" in slice_
    assert "no `permissions` key" in slice_
    # bypassPermissions must not appear inside the mapping table itself.
    assert "bypassPermissions" not in slice_, \
        f"bypassPermissions still appears in the mapping table:\n{slice_}"


def test_failure_behavior_table_names_classifier_refused():
    text = _text()
    assert "classifier refused" in text
    # The row lives in the failure-behavior table and follows its three-column shape.
    assert re.search(
        r"Classifier refused a tool call under `auto`.*BLOCKED: classifier refused",
        text,
    ), "classifier-refusal failure row missing from the failure-behavior table"


def test_dontask_is_named_forbidden():
    text = _text()
    assert "dontAsk" in text
    assert "forbidden" in text
    assert "S3-1" in text


STATE_VERDICT_ROWS = [
    ("working", "alive"),
    ("blocked", "alive"),
    ("done", "alive"),
    ("stopped", "stopped"),
    ("failed", "stopped"),
]


def test_state_verdict_table_rows():
    text = _text()
    for state, verdict in STATE_VERDICT_ROWS:
        pattern = rf"`{state}`\s*\|\s*{verdict}"
        assert re.search(pattern, text), f"missing row for state={state} -> {verdict}"
    assert "unknown" in text


def test_state_file_is_not_a_success_oracle():
    text = _text()
    assert "state file" in text.lower()
    assert "S4-2" in text


def test_stale_default_is_900():
    text = _text()
    assert "RELAY_BG_STALE_SECONDS" in text
    assert "900" in text


def test_identity_preamble_five_lines():
    text = _text()
    assert "Your name is" in text
    assert "AskUserQuestion" in text
    assert "Never command a sibling" in text
    assert "Never address the user" in text
    assert "envelope grammar only" in text
    # bg-sessions substitution
    assert "handoff-file" in text or "handoff file" in text


def test_fork_lines_are_marked_reserved():
    text = _text()
    assert "You are a fork of" in text
    assert "reserved" in text.lower()
    assert "unused" in text.lower()


def test_single_stop_mechanism_stated_once():
    text = _text()
    assert "finish-and-stop" in text
    assert "SendMessage" in text
    assert "bg-liveness.sh" in text
    assert text.count("finish-and-stop instruction") == 1


def test_both_scripts_named_and_present():
    text = _text()
    assert "scripts/bg-launch.sh" in text
    assert "scripts/bg-liveness.sh" in text
    assert (PLUGIN_ROOT / "scripts" / "bg-launch.sh").is_file()
    assert (PLUGIN_ROOT / "scripts" / "bg-liveness.sh").is_file()


def test_every_backticked_repo_path_exists():
    text = _text()
    candidates = set(CODE_PATH.findall(text))
    checkable = {
        c for c in candidates
        if "/" in c and c.split("/", 1)[0] in
        {"agents", "roles", "skills", "commands", "docs", "scripts", "tests",
         "bindings", "tools"}
    }
    assert checkable, "no checkable backticked paths — guard has gone vacuous"
    missing = sorted(c for c in checkable if not (PLUGIN_ROOT / c).exists())
    assert not missing, f"contract doc references non-existent paths: {missing}"


def test_live_validation_section_present():
    text = _text()
    assert "tests/e2e/bg-s1-roundtrip.sh" in text
    assert "RELAY_RUN_LIVE_BG" in text
