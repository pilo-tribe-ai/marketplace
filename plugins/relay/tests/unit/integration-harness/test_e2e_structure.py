# plugins/relay/tests/unit/integration-harness/test_e2e_structure.py

EXPECTED_IDS = [
    "implement-in-session-claude",
    "implement-acpx-claude",
    "implement-bg-sessions-claude",
    "verify-in-session-claude",
    "verify-acpx-claude",
    "implement-verify-in-session-claude",
]


def test_default_matrix_is_the_six_approved_rows(collect_integration):
    # -m integration wins over pytest.ini's addopts, so a missing marker on the
    # tier file would deselect every row and drop these ids — this is also the
    # marker guard.
    out = collect_integration("tests/integration/test_e2e.py").stdout
    for rid in EXPECTED_IDS:
        assert rid in out, f"row {rid} missing from the matrix:\n{out}"
