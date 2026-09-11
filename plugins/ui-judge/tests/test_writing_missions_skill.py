import pytest

from conftest import frontmatter

SKILL = ("skills", "writing-missions", "SKILL.md")


@pytest.fixture
def skill(plugin_root):
    return plugin_root.joinpath(*SKILL).read_text(encoding="utf-8")


def test_skill_declares_name_and_description(plugin_root):
    text = plugin_root.joinpath(*SKILL).read_text(encoding="utf-8")
    meta = frontmatter(text, "writing-missions/SKILL.md")
    assert meta["name"] == "writing-missions"
    assert meta["description"].strip()


def test_it_runs_the_lint_before_it_saves(skill):
    assert "mission_lint.py" in skill


def test_it_records_the_source_hash(skill):
    assert "source_hash.py" in skill
    assert "grounded-in-hash" in skill


def test_it_asks_the_person_to_confirm(skill):
    lowered = skill.lower()
    assert "askuserquestion" in lowered or "confirm" in lowered


def test_it_writes_drafts_not_approved_missions(skill):
    assert "status: draft" in skill


def test_it_forbids_implementation_detail(skill):
    lowered = skill.lower()
    assert "never" in lowered
    assert "selector" in lowered or "url" in lowered
