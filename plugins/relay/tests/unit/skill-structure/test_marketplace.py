import json

from conftest import PLUGIN_ROOT

# PLUGIN_ROOT == plugins/relay/ ; the repo-root manifest lives two levels up.
MARKETPLACE = PLUGIN_ROOT.parents[1] / ".claude-plugin" / "marketplace.json"


def _relay_entry():
    data = json.loads(MARKETPLACE.read_text())
    matches = [p for p in data["plugins"] if p.get("name") == "relay"]
    return matches


def test_marketplace_parses():
    data = json.loads(MARKETPLACE.read_text())
    assert isinstance(data.get("plugins"), list) and data["plugins"], (
        "repo-root marketplace.json must parse with a non-empty plugins array"
    )


def test_relay_entry_present():
    assert _relay_entry(), "marketplace.json plugins[] must contain a relay entry"


def test_relay_entry_conforms():
    entry = _relay_entry()[0]
    assert entry["source"] == "./plugins/relay", "relay source must be ./plugins/relay"
    assert entry["strict"] is False, "relay entry must set strict: false"
    assert entry.get("description"), "relay entry must have a non-empty description"
    assert "version" not in entry, (
        "relay entry must NOT carry a top-level version (version lives in plugin.json)"
    )
