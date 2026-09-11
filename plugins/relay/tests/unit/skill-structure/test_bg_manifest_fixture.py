"""Fixture-based reader tests for scripts/bg-manifest.sh (bg dispatch contract,
spec §Deliverable 3, Bookkeeping — docs/bg-dispatch-contract.md).

tests/unit/skill-structure/test_bg_manifest.py already exercises the write path
(init/add-session/set-phase) end to end. This file is different: it never calls
`init` or `add-session`. It plants a HAND-AUTHORED fixture manifest — the shape a
resumed session-tree run would actually find on disk — directly at the documented
path, then asserts the `read` and `names` subcommands surface every required field.
A regression that only breaks the reader (not the writer) would slip past
test_bg_manifest.py; it cannot slip past this file.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bg-manifest.sh"
FIXTURE = PLUGIN_ROOT / "tests" / "fixtures" / "bg-manifest" / "basic.json"
RUNID = "9a3f2c"

# The manifest shape bg-manifest.sh's own writer produces (spec §Deliverable 3,
# Bookkeeping) — top-level keys plus the per-session record keys. Every one of these
# must round-trip through the reader.
TOP_LEVEL_FIELDS = ["runid", "command", "started_at", "sessions"]
SESSION_FIELDS = ["name", "launch_id", "role", "parent", "phase"]


def _plant_fixture(tmp_path):
    home = tmp_path / "home"
    run_dir = home / ".claude" / "relay" / "runs" / RUNID
    run_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, run_dir / "manifest.json")
    return home


def _run(home, *args):
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run(["bash", str(SCRIPT), "--runid", RUNID, *args],
                           capture_output=True, text=True, env=env)


class TestFixtureShape:
    def test_fixture_itself_is_valid_json_with_every_field(self):
        # Guards the fixture against drifting out of sync with the documented shape
        # before it is ever handed to the script.
        data = json.loads(FIXTURE.read_text())
        for field in TOP_LEVEL_FIELDS:
            assert field in data, f"fixture is missing top-level field {field!r}"
        assert len(data["sessions"]) == 2
        for session in data["sessions"]:
            for field in SESSION_FIELDS:
                assert field in session, f"fixture session is missing field {field!r}"


class TestReadSurfacesEveryField:
    def test_read_returns_the_manifest_unchanged(self, tmp_path):
        home = _plant_fixture(tmp_path)
        result = _run(home, "read")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        expected = json.loads(FIXTURE.read_text())
        assert data == expected

    def test_read_output_carries_every_top_level_field(self, tmp_path):
        home = _plant_fixture(tmp_path)
        result = _run(home, "read")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        for field in TOP_LEVEL_FIELDS:
            assert field in data

    def test_read_output_carries_every_session_field(self, tmp_path):
        home = _plant_fixture(tmp_path)
        result = _run(home, "read")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert len(data["sessions"]) == 2
        for session in data["sessions"]:
            for field in SESSION_FIELDS:
                assert field in session, f"reader dropped {field!r} from a session record"

    def test_read_preserves_the_parent_child_edge(self, tmp_path):
        # The second fixture session names the first as its parent, not "MAIN" — the
        # tree-shaped case, distinct from every session hanging directly off MAIN.
        home = _plant_fixture(tmp_path)
        result = _run(home, "read")
        data = json.loads(result.stdout)
        child = next(s for s in data["sessions"] if s["role"] == "implementer")
        assert child["parent"] == "roi-dashboard-operator-feature-a-9a3f2c"


class TestNamesSurfacesEverySession:
    def test_names_emits_one_pair_per_session(self, tmp_path):
        home = _plant_fixture(tmp_path)
        result = _run(home, "names")
        assert result.returncode == 0, result.stderr
        assert result.stdout.count("RELAY_BG_NAME=") == 2
        assert result.stdout.count("RELAY_BG_SHORT_ID=") == 2

    def test_names_pairs_each_name_with_its_own_launch_id(self, tmp_path):
        home = _plant_fixture(tmp_path)
        result = _run(home, "names")
        assert result.returncode == 0, result.stderr
        fixture = json.loads(FIXTURE.read_text())
        lines = result.stdout.splitlines()
        for session in fixture["sessions"]:
            name_idx = lines.index(f"RELAY_BG_NAME={session['name']}")
            # bg-manifest.sh prints the pair back to back, name then short id.
            assert lines[name_idx + 1] == f"RELAY_BG_SHORT_ID={session['launch_id']}"
