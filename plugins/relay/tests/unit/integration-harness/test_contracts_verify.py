# plugins/relay/tests/unit/integration-harness/test_contracts_verify.py
import pytest


def test_state_root_path_and_round_records(itest_contracts, git_repo, tmp_path):
    sb = git_repo(tmp_path)
    root = itest_contracts.verify_state_root(sb)
    assert root == sb / ".git" / "relay-verify"
    rec = root / "round-1"
    rec.mkdir(parents=True)
    (rec / "record").write_text("SIMPLIFY=ran\nREVIEW=ran\nCHECK=ran\n")
    itest_contracts.assert_round_records(root, 1)                 # no raise
    with pytest.raises(AssertionError):
        itest_contracts.assert_round_records(root, 1, keys=("FIX",))


def test_verify_verdict_reads_last_result_line(itest_contracts, write_stream, tmp_path):
    s = write_stream(tmp_path, "... RELAY_VERIFY_RESULT=unverified ...\nRELAY_VERIFY_RESULT=clean")
    assert itest_contracts.verify_verdict(s) == "clean"


def test_assert_verify_refusal_holds_when_nothing_ran(itest_contracts, git_repo, write_stream, tmp_path):
    sb = git_repo(tmp_path)
    base = itest_contracts.current_head(sb)
    s = write_stream(tmp_path, "RELAY_VERIFY_RESULT=unverified")
    itest_contracts.assert_verify_refusal(sb, s, base)            # no raise
    # A state root present means a node ran -> refusal contract must fail.
    (itest_contracts.verify_state_root(sb)).mkdir(parents=True)
    with pytest.raises(AssertionError):
        itest_contracts.assert_verify_refusal(sb, s, base)
    # A no-op — no verdict line and a non-zero exit — is a silent failure, not a
    # documented refusal, even with no state root and no commit. [inferred]
    d2 = tmp_path / "second"
    d2.mkdir()
    sb2 = git_repo(d2)
    base2 = itest_contracts.current_head(sb2)
    empty = write_stream(d2, "")
    with pytest.raises(AssertionError):
        itest_contracts.assert_verify_refusal(sb2, empty, base2, rc=137)
