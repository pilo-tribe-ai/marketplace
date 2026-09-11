"""Tests for the AGENTS.md / CLAUDE.md schema documents."""
from conftest import REPO_ROOT, WIKI_ROOT


def test_claude_md_points_to_agents_md():
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    assert "[AGENTS.md](./{{CONTAINER}}AGENTS.md)" in text
    assert "{{CONTAINER}}" in text


def test_agents_md_documents_layout_and_checker():
    text = (WIKI_ROOT / "AGENTS.md").read_text()
    assert "scripts/check_okf.py" in text
    assert "raw/<date>-<slug>.<ext>" in text
    assert "schema.md" in text


def test_agents_md_documents_all_four_operations():
    text = (WIKI_ROOT / "AGENTS.md").read_text()
    for heading in (
        "## Operation: Initialization",
        "## Operation: Ingest",
        "## Operation: Query",
        "## Operation: Lint",
    ):
        assert heading in text, f"missing {heading}"


def test_agents_md_documents_actor_strings():
    text = (WIKI_ROOT / "AGENTS.md").read_text()
    for actor in ("{{AGENT_ACTOR}}", "process:adversarial-verifier", "{{HUMAN_ACTOR}}"):
        assert actor in text
