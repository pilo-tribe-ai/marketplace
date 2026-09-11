# plugins/relay/tests/unit/integration-harness/test_session_cleanup.py
def test_parse_session_names_extracts_first_column(itest_conftest):
    listing = (
        "NAME                 CWD\n"
        "relay-impl-abc123    /tmp/results/row-x/sandbox\n"
        "relay-verify-def456  /tmp/results/row-y/sandbox\n"
    )
    assert itest_conftest.parse_session_names(listing) == [
        "relay-impl-abc123", "relay-verify-def456",
    ]


def test_parse_session_names_empty_is_empty_list(itest_conftest):
    assert itest_conftest.parse_session_names("") == []
    assert itest_conftest.parse_session_names("NAME  CWD\n") == []


def test_live_fixtures_are_registered(itest_conftest):
    assert hasattr(itest_conftest, "relay_session")
    assert hasattr(itest_conftest, "make_sandbox")
