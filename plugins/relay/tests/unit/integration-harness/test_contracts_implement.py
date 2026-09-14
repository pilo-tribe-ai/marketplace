# plugins/relay/tests/unit/integration-harness/test_contracts_implement.py
import pytest


def test_spine_ok_requires_status_ok_block(itest_contracts, write_stream, tmp_path):
    ok = write_stream(tmp_path, 'done\n{"status": "ok", "run_id": "wf_1", "commit": "abc1234"}')
    itest_contracts.assert_implement_spine_ok(ok)                      # no raise
    bad = write_stream(tmp_path, '{"status": "error", "run_id": "wf_1"}')
    with pytest.raises(AssertionError):
        itest_contracts.assert_implement_spine_ok(bad)


def test_deliverable_linecount_runs_the_script(itest_contracts, tmp_path):
    sb = tmp_path / "sb"
    (sb / "scripts").mkdir(parents=True)
    (sb / "scripts" / "linecount.py").write_text(
        "import sys\n"
        "n = sum(1 for ln in open(sys.argv[1]) if ln.strip())\n"
        "print(n)\n"
    )
    itest_contracts.assert_deliverable_linecount(sb, tmp_path)         # 3 non-empty lines


def test_deliverable_linecount_flags_missing_script(itest_contracts, tmp_path):
    sb = tmp_path / "empty"
    sb.mkdir()
    with pytest.raises(AssertionError):
        itest_contracts.assert_deliverable_linecount(sb, tmp_path)
