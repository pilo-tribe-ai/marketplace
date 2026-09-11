# plugins/relay/tests/unit/integration-harness/test_contracts_git.py
import subprocess

import pytest


def test_branch_and_ahead_count(itest_contracts, git_repo, tmp_path):
    sb = git_repo(tmp_path)
    assert itest_contracts.current_branch(sb) == "main"
    assert not itest_contracts.is_detached(sb)
    subprocess.run(["git", "-C", str(sb), "checkout", "-q", "-b", "feature/x"], check=True)
    (sb / "g.txt").write_text("y\n")
    subprocess.run(["git", "-C", str(sb), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(sb), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "more"], check=True)
    assert itest_contracts.commits_ahead(sb, "main") == 1
    assert itest_contracts.working_tree_clean(sb)


def test_assert_refusal_and_no_new_commit(itest_contracts, git_repo, write_stream, tmp_path):
    sb = git_repo(tmp_path)
    base = itest_contracts.current_head(sb)
    s = write_stream(tmp_path, "verify: refusing to run on the default branch. ...")
    itest_contracts.assert_refusal(s, "refusing to run on the default branch")   # no raise
    itest_contracts.assert_no_new_commit(sb, base)                               # no raise
    with pytest.raises(AssertionError):
        itest_contracts.assert_refusal(s, "this phrase is absent")
