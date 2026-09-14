"""Static checks over the /wiki:ask surface -- the command, its backing
skill, and the doc-drift surfaces that name it. No scaffolding, no
subprocess. Uses the plugin_root and plugin_json fixtures from conftest.py."""

import pytest


def read(path):
    return path.read_text(encoding="utf-8")


def frontmatter(text):
    lines = text.splitlines()
    assert lines[0] == "---", "file does not open with a frontmatter fence"
    end = lines[1:].index("---") + 1
    return "\n".join(lines[1:end])


@pytest.fixture
def ask_path(plugin_root):
    return plugin_root / "commands" / "ask.md"


@pytest.fixture
def skill_path(plugin_root):
    return plugin_root / "skills" / "answering-from-okf-wikis" / "SKILL.md"


@pytest.fixture
def ask_text(ask_path):
    return read(ask_path)


@pytest.fixture
def skill_text(skill_path):
    return read(skill_path)


@pytest.fixture
def ask_surface(ask_path, skill_path):
    return [ask_path, skill_path]


def test_ask_command_exists_and_declares_frontmatter(ask_path):
    assert ask_path.is_file(), "commands/ask.md is missing"
    fm = frontmatter(read(ask_path))
    assert any(line.startswith("description:") for line in fm.splitlines()), \
        "ask.md frontmatter holds no description: line"
    assert any(line.startswith("argument-hint:") for line in fm.splitlines()), \
        "ask.md frontmatter holds no argument-hint: line"
    assert any(line.startswith("allowed-tools:") for line in fm.splitlines()), \
        "ask.md frontmatter holds no allowed-tools: line"


def test_ask_command_allows_the_tools_the_query_operation_needs(ask_text):
    allowed_line = next(
        line for line in ask_text.splitlines() if line.startswith("allowed-tools:")
    )
    for tool in ["Read", "Grep", "Glob", "Skill", "Edit", "Write", "AskUserQuestion"]:
        assert tool in allowed_line, f"ask.md allowed-tools is missing {tool}"
    assert "Bash(python3:*)" in allowed_line, \
        "ask.md allowed-tools is missing Bash(python3:*)"


def test_ask_command_allows_no_web_tool(ask_text, skill_text):
    for name in ["WebFetch", "WebSearch"]:
        assert name not in ask_text, f"{name} must not appear in ask.md"
        assert name not in skill_text, f"{name} must not appear in the skill"


def test_ask_and_ingest_share_the_step_0_failure_messages(ask_text, plugin_root):
    ingest_text = read(plugin_root / "commands" / "ingest.md")
    no_wiki = "This repository has no wiki. Run `/wiki:setup` first."
    # ingest.md soft-wraps this sentence right after "which", so the safe
    # shared literal starts just past that wrap point.
    broken_pointer = "does not exist. Run `/wiki:setup` to re-scaffold or fix the pointer."
    assert no_wiki in ask_text, "ask.md is missing the no-wiki message"
    assert no_wiki in ingest_text, "ingest.md is missing the no-wiki message"
    assert broken_pointer in ask_text, "ask.md is missing the broken-pointer message"
    assert broken_pointer in ingest_text, "ingest.md is missing the broken-pointer message"


def test_ask_command_resolves_the_wiki_json_pointer(ask_text):
    assert ".claude/wiki.json" in ask_text, "ask.md never names .claude/wiki.json"
    assert "test -f .claude/wiki.json" in ask_text, "ask.md never tests for the pointer file"
    assert "['container']" in ask_text, "ask.md never reads the container key"


def test_ask_command_invokes_the_answering_skill(ask_text):
    assert "wiki:answering-from-okf-wikis" in ask_text, \
        "ask.md never invokes the answering-from-okf-wikis skill"


def test_ask_command_demands_a_question(ask_text):
    assert "Give me a question. Run `/wiki:ask <your question>`." in ask_text, \
        "ask.md never stops on an empty question"


def test_every_skill_name_is_its_bare_directory_basename(plugin_root):
    skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
    assert len(skill_files) >= 2, \
        "expected at least 2 skills; the walk would pass vacuously with fewer"
    for path in skill_files:
        fm = frontmatter(read(path))
        name_line = next(
            line for line in fm.splitlines() if line.startswith("name:")
        )
        name = name_line.split("name:", 1)[1].strip()
        assert name == path.parent.name, \
            f"{path} declares name {name!r}, expected {path.parent.name!r}"
        assert ":" not in name, f"{path} declares a namespaced name {name!r}"


def test_answering_skill_declares_frontmatter(skill_text):
    fm = frontmatter(skill_text)
    for key in ["name:", "description:", "allowed-tools:"]:
        assert any(line.startswith(key) for line in fm.splitlines()), \
            f"SKILL.md frontmatter is missing a {key} line"
    description_line = next(
        line for line in fm.splitlines() if line.startswith("description:")
    )
    assert ".claude/wiki.json" in description_line, \
        "SKILL.md description never names .claude/wiki.json"
    assert "/wiki:ask" in description_line, \
        "SKILL.md description never names /wiki:ask"


def test_answering_skill_binds_to_operation_query(skill_text):
    assert "Operation: Query" in skill_text, \
        "SKILL.md never binds itself to AGENTS.md Operation: Query"


def test_answering_skill_states_the_empty_bundle_message(skill_text):
    assert "holds no pages yet" in skill_text, \
        "SKILL.md never states the empty-bundle message"
    assert "/wiki:ingest" in skill_text, \
        "SKILL.md never points the user at /wiki:ingest"


def test_answering_skill_states_the_no_fabrication_rule(skill_text):
    count = skill_text.count("I do not answer from outside the wiki")
    assert count >= 2, \
        f"expected the no-fabrication phrase at least twice, found {count}"


def test_answering_skill_states_the_no_answer_message(skill_text):
    assert "The wiki holds no page that answers this question." in skill_text, \
        "SKILL.md never states the no-answer message"


def test_answering_skill_states_the_partial_coverage_heading(skill_text):
    assert "## What the wiki does not cover" in skill_text, \
        "SKILL.md never states the partial-coverage heading"


def test_answering_skill_appends_a_query_log_entry(skill_text):
    count = skill_text.count("* **Query**")
    assert count >= 4, f"expected at least 4 Query log forms, found {count}"


def test_answering_skill_runs_the_blocking_gate(skill_text):
    assert "scripts/check_okf.py" in skill_text, \
        "SKILL.md never runs the blocking check_okf.py gate"
    assert "regen_indexes.py" in skill_text, \
        "SKILL.md never runs regen_indexes.py to rebuild the synthesis index"


def test_ask_surface_holds_no_unrendered_token(ask_surface):
    for path in ask_surface:
        assert path.is_file(), f"{path} is missing"
        assert "{{" not in read(path), f"{path} holds an unrendered token"


def test_ask_surface_holds_no_non_ascii(ask_surface, plugin_root):
    offenders = []
    for path in ask_surface:
        try:
            path.read_bytes().decode("ascii")
        except UnicodeDecodeError:
            offenders.append(str(path.relative_to(plugin_root)))
    assert not offenders, f"non-ASCII byte(s) found in: {offenders}"


def test_readme_names_three_commands(plugin_root):
    text = read(plugin_root / "README.md")
    assert "Three commands" in text, "README.md never says Three commands"
    assert "/wiki:ask" in text, "README.md never names /wiki:ask"
    assert "wiki:answering-from-okf-wikis" in text, \
        "README.md never names the answering-from-okf-wikis skill"
    assert "Two commands" not in text, \
        "README.md still says Two commands somewhere"


def test_plugin_manifest_names_all_three_commands_and_is_semver(plugin_json):
    description = plugin_json["description"]
    for command in ["/wiki:setup", "/wiki:ingest", "/wiki:ask"]:
        assert command in description, \
            f"plugin.json description is missing {command}"
    import re
    assert re.match(r"^\d+\.\d+\.\d+$", plugin_json["version"]), \
        f"plugin.json version {plugin_json['version']!r} is not semver"


def test_shipped_templates_name_the_ask_command(plugin_root):
    claude_block = read(plugin_root / "templates" / "claude-md-block.md")
    assert "/wiki:ask" in claude_block, \
        "claude-md-block.md never names /wiki:ask"

    agents_md = read(plugin_root / "templates" / "rendered" / "AGENTS.md")
    assert "/wiki:ask" in agents_md, \
        "templates/rendered/AGENTS.md never names /wiki:ask"
    for heading in [
        "## Operation: Initialization",
        "## Operation: Ingest",
        "## Operation: Query",
        "## Operation: Lint",
    ]:
        assert heading in agents_md, \
            f"templates/rendered/AGENTS.md is missing the {heading!r} heading"
