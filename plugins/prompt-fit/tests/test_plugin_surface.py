"""Static checks over the prompt-fit plugin surface."""

import json
import re

from conftest import frontmatter

EXPECTED_COMMANDS = ["review", "revise", "new"]
EXPECTED_SKILLS = ["reviewing-prompts", "revising-prompts", "writing-prompts"]
EXPECTED_SCRIPTS = ["resolve_target", "prompt_lint", "compare_prompts"]

VERSION = "0.1.0"


def test_manifest_declares_name_and_version(plugin_json):
    assert plugin_json["name"] == "prompt-fit"
    assert plugin_json["version"] == VERSION


def test_manifest_has_description_and_license(plugin_json):
    assert plugin_json["description"].strip()
    assert plugin_json["license"] == "MIT"


def test_every_command_exists(plugin_root):
    for name in EXPECTED_COMMANDS:
        assert (plugin_root / "commands" / f"{name}.md").is_file(), f"commands/{name}.md is missing"


def test_every_skill_exists(plugin_root):
    for name in EXPECTED_SKILLS:
        assert (
            plugin_root / "skills" / name / "SKILL.md"
        ).is_file(), f"skills/{name}/SKILL.md is missing"


def test_every_script_exists(plugin_root):
    for name in EXPECTED_SCRIPTS:
        assert (plugin_root / "scripts" / f"{name}.py").is_file()


def test_the_corpus_exists(plugin_root):
    assert (plugin_root / "reference" / "principles.md").is_file()


def test_no_unexpected_command_ships(plugin_root):
    found = sorted(item.stem for item in (plugin_root / "commands").glob("*.md"))
    assert found == sorted(EXPECTED_COMMANDS)


def test_no_unexpected_skill_ships(plugin_root):
    found = sorted(item.name for item in (plugin_root / "skills").iterdir() if item.is_dir())
    assert found == sorted(EXPECTED_SKILLS)


def test_every_command_declares_a_description(plugin_root):
    for name in EXPECTED_COMMANDS:
        path = plugin_root / "commands" / f"{name}.md"
        meta = frontmatter(path.read_text(encoding="utf-8"), path.name)
        assert meta["description"].strip()


def test_every_skill_declares_its_own_name_and_a_description(plugin_root):
    for name in EXPECTED_SKILLS:
        path = plugin_root / "skills" / name / "SKILL.md"
        meta = frontmatter(path.read_text(encoding="utf-8"), path.name)
        assert meta["name"] == name, f"{name} registers under a different name"
        assert meta["description"].strip()


def test_every_command_invokes_a_skill_that_ships(plugin_root):
    """A command that names a missing skill is unreachable."""
    for name in EXPECTED_COMMANDS:
        text = (plugin_root / "commands" / f"{name}.md").read_text(encoding="utf-8")
        named = re.findall(r"Skill\('prompt-fit:([a-z-]+)'\)", text)
        assert named, f"commands/{name}.md invokes no skill"
        for skill in named:
            assert skill in EXPECTED_SKILLS, f"commands/{name}.md names skill {skill}"


def test_every_script_path_in_a_skill_points_at_a_file_that_ships(plugin_root):
    for name in EXPECTED_SKILLS:
        text = (plugin_root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for reference in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w/.-]+)", text):
            assert (plugin_root / reference).is_file(), f"{name} names missing {reference}"


def test_the_plugin_is_listed_in_the_marketplace(plugin_root):
    marketplace = plugin_root.parent.parent / ".claude-plugin" / "marketplace.json"
    entries = json.loads(marketplace.read_text(encoding="utf-8"))["plugins"]
    listed = [entry for entry in entries if entry["name"] == "prompt-fit"]
    assert listed, "prompt-fit is not listed in marketplace.json"
    assert listed[0]["source"] == "./plugins/prompt-fit"


def test_the_changelog_records_this_version(plugin_root):
    """The version is the cache key for plugin distribution."""
    text = (plugin_root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {VERSION}" in text


def test_the_readme_names_every_command(plugin_root):
    text = (plugin_root / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED_COMMANDS:
        assert f"/prompt-fit:{name}" in text
