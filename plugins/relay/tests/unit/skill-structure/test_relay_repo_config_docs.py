from conftest import PLUGIN_ROOT


DOC = PLUGIN_ROOT / "docs" / "superpowers" / "references" / "relay-repo-config.md"
USING_RELAY = PLUGIN_ROOT / "skills" / "using-relay" / "SKILL.md"


def test_relay_repo_config_reference_exists_and_documents_bootstrap():
    assert DOC.is_file(), "relay repo config reference doc missing"
    body = DOC.read_text()
    assert ".claude/relay.json" in body
    assert '"bootstrap"' in body
    assert "pnpm install --frozen-lockfile && pnpm build:ts" in body
    assert "primary checkout" in body
    assert "new worktree" in body
    assert "stderr" in body
    assert "RELAY_WT_BOOTSTRAP=ran" in body
    assert "RELAY_WT_BOOTSTRAP=skipped" in body
    assert "No package-manager auto-detection" in body


def test_using_relay_points_to_repo_config_reference():
    body = USING_RELAY.read_text()
    assert "relay-repo-config.md" in body
    assert ".claude/relay.json" in body
