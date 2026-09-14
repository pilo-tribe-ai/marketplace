# plugins/relay/tests/unit/integration-harness/test_release_hygiene.py
import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def test_results_dir_is_self_ignoring():
    gi = PLUGIN_ROOT / "tests" / "integration" / "results" / ".gitignore"
    body = gi.read_text()
    assert "*" in body.splitlines()
    assert "!.gitignore" in body.splitlines()


def test_version_bumped_to_4_52_0():
    pj = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert pj["version"] == "4.52.0"


def test_changelog_notes_the_harness():
    body = (PLUGIN_ROOT / "CHANGELOG.md").read_text()
    assert "4.52.0" in body
    assert "integration" in body.lower()
