"""Unit tests for scripts/bg-manifest.sh (bg dispatch contract, spec §Deliverable 3,
Bookkeeping — docs/bg-dispatch-contract.md).

Everything here is SYNTHETIC. `HOME` is pointed at `tmp_path`, in the same style
test_record_run_intent.py drives record-run-intent.sh, so no real home directory is
ever touched.
"""

import json
import os
import stat
import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bg-manifest.sh"


def _run(tmp_path, args, home=None):
    if home is None:
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    result = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                             text=True, env=env)
    return result, home


def _manifest_path(home, runid):
    return home / ".claude" / "relay" / "runs" / runid / "manifest.json"


class TestScriptShape:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.is_file(), "scripts/bg-manifest.sh is missing"
        assert os.access(SCRIPT, os.X_OK), "scripts/bg-manifest.sh is not executable"


class TestInit:
    def test_init_creates_the_documented_path(self, tmp_path):
        result, home = _run(tmp_path, ["--runid", "7f3c", "init", "--command", "implement"])
        assert result.returncode == 0, result.stderr
        path = _manifest_path(home, "7f3c")
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["runid"] == "7f3c"
        assert data["command"] == "implement"
        assert data["sessions"] == []

    def test_runid_charset_is_enforced(self, tmp_path):
        for bad in ("WF_123", "abc", "abcdefghi"):
            result, _ = _run(tmp_path, ["--runid", bad, "init", "--command", "x"])
            assert result.returncode == 2, f"{bad!r} should be rejected: {result.stderr}"


class TestAddSessionAndSetPhase:
    def _init(self, tmp_path):
        result, home = _run(tmp_path, ["--runid", "7f3c", "init", "--command", "implement"])
        assert result.returncode == 0, result.stderr
        return home

    def test_add_session_records_every_field(self, tmp_path):
        home = self._init(tmp_path)
        result, _ = _run(tmp_path, [
            "--runid", "7f3c", "add-session",
            "--name", "roi-dashboard-implementer-feature-a-7f3c",
            "--launch-id", "abc123",
            "--role", "implementer",
            "--parent", "MAIN",
            "--phase", "spawned",
        ], home=home)
        assert result.returncode == 0, result.stderr
        data = json.loads(_manifest_path(home, "7f3c").read_text())
        assert len(data["sessions"]) == 1
        s = data["sessions"][0]
        assert s["name"] == "roi-dashboard-implementer-feature-a-7f3c"
        assert s["launch_id"] == "abc123"
        assert s["role"] == "implementer"
        assert s["parent"] == "MAIN"
        assert s["phase"] == "spawned"

    def test_set_phase_updates_in_place(self, tmp_path):
        home = self._init(tmp_path)
        _run(tmp_path, [
            "--runid", "7f3c", "add-session",
            "--name", "n1", "--launch-id", "id1",
            "--role", "implementer", "--parent", "MAIN", "--phase", "spawned",
        ], home=home)
        result, _ = _run(tmp_path, [
            "--runid", "7f3c", "set-phase", "--name", "n1", "--phase", "done",
        ], home=home)
        assert result.returncode == 0, result.stderr
        data = json.loads(_manifest_path(home, "7f3c").read_text())
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["phase"] == "done"

    def test_manifest_is_state_not_a_log(self, tmp_path):
        home = self._init(tmp_path)
        _run(tmp_path, [
            "--runid", "7f3c", "add-session",
            "--name", "n1", "--launch-id", "id1",
            "--role", "implementer", "--parent", "MAIN", "--phase", "spawned",
        ], home=home)
        _run(tmp_path, ["--runid", "7f3c", "set-phase", "--name", "n1", "--phase", "working"], home=home)
        _run(tmp_path, ["--runid", "7f3c", "set-phase", "--name", "n1", "--phase", "done"], home=home)
        data = json.loads(_manifest_path(home, "7f3c").read_text())
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["phase"] == "done"


class TestAtomicityAndFailure:
    def test_write_is_atomic(self, tmp_path):
        result, home = _run(tmp_path, ["--runid", "7f3c", "init", "--command", "implement"])
        assert result.returncode == 0, result.stderr
        run_dir = home / ".claude" / "relay" / "runs" / "7f3c"
        leftovers = [p for p in run_dir.iterdir() if ".tmp." in p.name]
        assert leftovers == [], f"temp file left behind: {leftovers}"
        json.loads(_manifest_path(home, "7f3c").read_text())  # parses cleanly

    def test_write_failure_is_fatal(self, tmp_path):
        result, home = _run(tmp_path, ["--runid", "7f3c", "init", "--command", "implement"])
        assert result.returncode == 0, result.stderr
        run_dir = home / ".claude" / "relay" / "runs" / "7f3c"
        os.chmod(run_dir, 0o555)
        try:
            result2, _ = _run(tmp_path, [
                "--runid", "7f3c", "add-session",
                "--name", "n1", "--launch-id", "id1",
                "--role", "implementer", "--parent", "MAIN", "--phase", "spawned",
            ], home=home)
            assert result2.returncode == 1
            assert "manifest write failed" in result2.stderr
        finally:
            os.chmod(run_dir, 0o755)


class TestReadAndNames:
    def test_read_prints_valid_json(self, tmp_path):
        result, home = _run(tmp_path, ["--runid", "7f3c", "init", "--command", "implement"])
        assert result.returncode == 0, result.stderr
        result2, _ = _run(tmp_path, ["--runid", "7f3c", "read"], home=home)
        assert result2.returncode == 0
        json.loads(result2.stdout)  # does not raise

    def test_names_prints_key_value_pairs(self, tmp_path):
        result, home = _run(tmp_path, ["--runid", "7f3c", "init", "--command", "implement"])
        assert result.returncode == 0, result.stderr
        for i in range(2):
            _run(tmp_path, [
                "--runid", "7f3c", "add-session",
                "--name", f"n{i}", "--launch-id", f"id{i}",
                "--role", "implementer", "--parent", "MAIN", "--phase", "spawned",
            ], home=home)
        result2, _ = _run(tmp_path, ["--runid", "7f3c", "names"], home=home)
        assert result2.returncode == 0
        assert result2.stdout.count("RELAY_BG_NAME=") == 2
        assert result2.stdout.count("RELAY_BG_SHORT_ID=") == 2


class TestUsageErrors:
    def test_usage_error_exits_2(self, tmp_path):
        result, _ = _run(tmp_path, ["--runid", "7f3c", "not-a-subcommand"])
        assert result.returncode == 2
        result2, _ = _run(tmp_path, ["init", "--command", "x"])
        assert result2.returncode == 2
