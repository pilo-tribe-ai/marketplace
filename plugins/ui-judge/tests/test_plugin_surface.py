"""Static checks over the ui-judge plugin surface. No browser, no network."""

import json

from conftest import frontmatter

EXPECTED_COMMANDS = ["setup", "missions", "judge", "explore", "compile"]

EXPECTED_SKILLS = [
    "writing-missions",
    "judging-missions",
    "exploring-web-apps",
    "compiling-missions",
]

EXPECTED_AGENTS = ["mission-driver", "mission-judge"]


def test_manifest_declares_name_and_version(plugin_json):
    assert plugin_json["name"] == "ui-judge"
    assert plugin_json["version"] == "0.1.3"


def test_manifest_has_description_and_license(plugin_json):
    assert plugin_json["description"].strip()
    assert plugin_json["license"] == "MIT"


def test_every_command_exists(plugin_root):
    for name in EXPECTED_COMMANDS:
        path = plugin_root / "commands" / f"{name}.md"
        assert path.is_file(), f"commands/{name}.md is missing"


def test_every_skill_exists(plugin_root):
    for name in EXPECTED_SKILLS:
        path = plugin_root / "skills" / name / "SKILL.md"
        assert path.is_file(), f"skills/{name}/SKILL.md is missing"


def test_every_agent_exists(plugin_root):
    for name in EXPECTED_AGENTS:
        path = plugin_root / "agents" / f"{name}.md"
        assert path.is_file(), f"agents/{name}.md is missing"


def test_plugin_is_listed_in_the_marketplace(plugin_root):
    marketplace = plugin_root.parent.parent / ".claude-plugin" / "marketplace.json"
    entries = json.loads(marketplace.read_text(encoding="utf-8"))["plugins"]
    names = [entry["name"] for entry in entries]
    assert "ui-judge" in names, "ui-judge is not listed in marketplace.json"


def frontmatter_of(path):
    return frontmatter(path.read_text(encoding="utf-8"), path.name)


def test_setup_command_declares_a_description(plugin_root):
    meta = frontmatter_of(plugin_root / "commands" / "setup.md")
    assert meta["description"].strip()


def test_setup_tells_the_agent_to_ignore_the_run_folder(plugin_root):
    text = (plugin_root / "commands" / "setup.md").read_text(encoding="utf-8")
    assert ".gitignore" in text
    assert "runs/" in text
    assert "auth/" in text


def test_setup_never_writes_a_secret_value(plugin_root):
    text = (plugin_root / "commands" / "setup.md").read_text(encoding="utf-8").lower()
    assert "never write the value" in text or "records only the place" in text


def test_judge_command_invokes_the_judging_skill(plugin_root):
    text = (plugin_root / "commands" / "judge.md").read_text(encoding="utf-8")
    assert "judging-missions" in text


def test_judge_command_declares_a_description(plugin_root):
    meta = frontmatter_of(plugin_root / "commands" / "judge.md")
    assert meta["description"].strip()


def test_judge_command_says_it_does_not_repair(plugin_root):
    text = (plugin_root / "commands" / "judge.md").read_text(encoding="utf-8").lower()
    assert "does not" in text and "repair" in text


def test_readme_exists_and_names_every_command(plugin_root):
    text = (plugin_root / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED_COMMANDS:
        assert f"/ui-judge:{name}" in text, f"README does not name /ui-judge:{name}"


def test_readme_says_the_plugin_does_not_repair(plugin_root):
    text = (plugin_root / "README.md").read_text(encoding="utf-8").lower()
    assert "never repair" in text or "does not repair" in text


def test_changelog_records_the_manifest_version(plugin_root, plugin_json):
    text = (plugin_root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert plugin_json["version"] in text, (
        "the CHANGELOG must carry the version in plugin.json"
    )


def test_a_ci_workflow_runs_this_suite(plugin_root):
    workflow = plugin_root.parent.parent / ".github" / "workflows" / "ui-judge.yml"
    assert workflow.is_file(), "there is no CI workflow for ui-judge"
    text = workflow.read_text(encoding="utf-8")
    assert "plugins/ui-judge" in text
    assert "pytest" in text


def test_explore_command_can_open_a_browser(plugin_root):
    """exploring-web-apps drives the application itself; it dispatches no
    agent. Without a browser tool the command cannot do the one thing it is
    for."""
    meta = frontmatter_of(plugin_root / "commands" / "explore.md")
    tools = meta["allowed-tools"]
    assert "playwright" in tools, (
        "explore has no browser tool, and its skill dispatches no agent"
    )


def test_every_command_argument_is_handled_by_its_skill(plugin_root):
    """An argument a command advertises and its skill ignores is a silent
    no-op: the run reports success and the argument did nothing."""
    pairs = [
        ("judge", "judging-missions", ["--tag", "--all"]),
        ("explore", "exploring-web-apps", ["--budget"]),
        ("missions", "writing-missions", ["--from"]),
    ]
    for command, skill, arguments in pairs:
        text = (plugin_root / "skills" / skill / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for argument in arguments:
            assert argument in text, (
                f"/ui-judge:{command} advertises {argument}, "
                f"but {skill} never says what to do with it"
            )


def test_setup_warns_about_a_real_site_before_it_writes_the_config(plugin_root):
    """The config that names a real site is what lets a later run click
    buttons on it. A warning printed after the file exists guards nothing."""
    text = (plugin_root / "commands" / "setup.md").read_text(encoding="utf-8")
    warning = text.find("This looks like a real site")
    write = text.find("Write the files")
    assert warning != -1 and write != -1
    assert warning < write, "the warning comes after the config is written"


def test_judge_command_runs_missions_that_need_review(plugin_root):
    """A drifted mission is marked `needs review`. It must still be run, or the
    drift is never judged and the mission is skipped in silence."""
    text = (plugin_root / "commands" / "judge.md").read_text(encoding="utf-8").lower()
    assert "needs review" in text
