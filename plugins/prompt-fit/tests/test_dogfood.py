"""The plugin's own prompts obey the rules the plugin sells.

A prompt-engineering plugin whose own prompts break its rules cannot be
believed. These tests fail the build rather than let that ship.
"""

import pytest

SKILLS = ["reviewing-prompts", "revising-prompts", "writing-prompts"]
COMMANDS = ["review", "revise", "new"]


def report_for(lint, path):
    return lint.analyse(path.read_text(encoding="utf-8"), str(path))


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_raises_no_finding(lint, plugin_root, name):
    report = report_for(lint, plugin_root / "skills" / name / "SKILL.md")
    assert report["findings"] == [], f"{name}: {[f['kind'] for f in report['findings']]}"


@pytest.mark.parametrize("name", COMMANDS)
def test_each_command_raises_no_finding(lint, plugin_root, name):
    report = report_for(lint, plugin_root / "commands" / f"{name}.md")
    assert report["findings"] == [], f"{name}: {[f['kind'] for f in report['findings']]}"


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_stays_out_of_the_at_risk_band(lint, plugin_root, name):
    report = report_for(lint, plugin_root / "skills" / name / "SKILL.md")
    assert report["band"] in ("healthy", "watch"), f"{name} counts {report['instructions']}"


def test_the_corpus_is_mostly_reference_material(lint, plugin_root):
    """P2 in practice: the rulebook is small, and the corpus is big."""
    report = report_for(lint, plugin_root / "reference" / "principles.md")
    assert report["reference_lines"] > 100
    assert report["instructions"] <= 5
    assert report["findings"] == []
