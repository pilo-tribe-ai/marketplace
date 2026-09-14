# plugins/relay/tests/unit/integration-harness/test_build_sandbox.py
import json
import subprocess


def _git(sb, *args):
    return subprocess.run(["git", "-C", str(sb), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_feature_variant_starts_on_feature_branch(itest_conftest, tmp_path):
    sb = itest_conftest.build_sandbox(tmp_path / "sb", itest_conftest.SEEDS_DIR,
                                      variant="implement", start_on="feature",
                                      pin={"engine": "in-session", "agent": "claude"})
    assert _git(sb, "rev-parse", "--abbrev-ref", "HEAD") == "feature/itest"
    assert (sb / "src" / "wordcount.py").exists()
    assert (sb / ".claude" / "commands" / "verify.md").exists()
    assert json.loads((sb / ".claude" / "relay.json").read_text())["engine"] == "in-session"
    assert _git(sb, "status", "--porcelain") == ""          # clean tree


def test_verify_variant_commits_a_change_to_polish(itest_conftest, tmp_path):
    sb = itest_conftest.build_sandbox(tmp_path / "sb", itest_conftest.SEEDS_DIR,
                                      variant="verify", start_on="feature")
    assert int(_git(sb, "rev-list", "--count", "main..HEAD")) == 1


def test_main_variant_stays_on_default_branch(itest_conftest, tmp_path):
    sb = itest_conftest.build_sandbox(tmp_path / "sb", itest_conftest.SEEDS_DIR,
                                      start_on="main")
    assert _git(sb, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_detached_variant_detaches_head(itest_conftest, tmp_path):
    sb = itest_conftest.build_sandbox(tmp_path / "sb", itest_conftest.SEEDS_DIR,
                                      start_on="detached")
    assert _git(sb, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
