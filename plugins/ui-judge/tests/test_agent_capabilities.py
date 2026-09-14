"""The judge must not be able to open a browser.

This is the plugin's central invariant. A judge that can drive the application
can keep looking until it finds a reason to pass, and then two runs of the same
mission give two different verdicts.
"""

import pytest
import yaml


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name} does not open with a fence"
    body = text.split("---\n", 2)[1]
    return yaml.safe_load(body)


@pytest.fixture
def driver(plugin_root):
    return frontmatter(plugin_root / "agents" / "mission-driver.md")


@pytest.fixture
def judge(plugin_root):
    return frontmatter(plugin_root / "agents" / "mission-judge.md")


def tools_of(meta):
    value = meta["tools"]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(value)


def test_both_agents_declare_a_name_and_a_description(driver, judge):
    for meta in (driver, judge):
        assert meta["name"]
        assert meta["description"].strip()


def test_the_agents_are_named_as_the_skills_dispatch_them(driver, judge):
    assert driver["name"] == "mission-driver"
    assert judge["name"] == "mission-judge"


def test_the_driver_can_open_a_browser(driver):
    assert any("browser_" in tool for tool in tools_of(driver)), (
        "the driver must be able to drive the application"
    )


def test_the_judge_has_no_browser_tool(judge):
    offenders = [tool for tool in tools_of(judge) if "browser_" in tool]
    assert offenders == [], (
        f"the judge must not be able to open a browser, but it may use {offenders}"
    )


def test_the_judge_has_no_wildcard_tool_grant(judge):
    assert "*" not in tools_of(judge), (
        "a wildcard would hand the judge every browser tool"
    )


def test_the_judge_cannot_run_shell_commands(judge):
    assert "Bash" not in tools_of(judge), (
        "Bash would let the judge reach the application another way"
    )


def test_setup_enables_the_opt_in_playwright_capabilities(plugin_root):
    """browser_verify_* sits in the `testing` capability and
    browser_storage_state in `storage`. Both are off by default, so the MCP
    entry setup shows must name them, or every tool in the driver's `Then`
    check list is missing at run time."""
    text = (plugin_root / "commands" / "setup.md").read_text(encoding="utf-8")
    assert "--caps=testing,storage" in text
    assert "--allowed-origins" in text


def test_the_driver_is_told_what_to_do_when_a_capability_is_off(plugin_root):
    text = (plugin_root / "agents" / "mission-driver.md").read_text(encoding="utf-8")
    assert "--caps=testing,storage" in text, (
        "the driver must say which capability its check tools need"
    )


def test_the_driver_can_restore_a_saved_session(plugin_root):
    """The judging skill holds no browser tool, so only the driver can do it."""
    text = (plugin_root / "agents" / "mission-driver.md").read_text(encoding="utf-8")
    assert "browser_set_storage_state" in text


def test_the_driver_is_told_it_must_not_rule(plugin_root):
    text = (plugin_root / "agents" / "mission-driver.md").read_text(encoding="utf-8")
    assert "do not rule" in text.lower() or "never rule" in text.lower()


def test_the_judge_is_told_it_may_answer_unclear(plugin_root):
    text = (plugin_root / "agents" / "mission-judge.md").read_text(encoding="utf-8")
    assert "unclear" in text.lower()


def test_the_judge_rules_on_one_scenario(plugin_root):
    """Spec 4.1 makes the scenario the unit of judgement, not the mission."""
    text = (plugin_root / "agents" / "mission-judge.md").read_text(encoding="utf-8")
    assert "one scenario" in text.lower(), (
        "the judge must be told it rules on a single scenario"
    )


def test_the_judge_does_not_write_the_two_caller_fields(plugin_root):
    """The judge never sees the drift result, so it cannot write these itself."""
    text = (plugin_root / "agents" / "mission-judge.md").read_text(encoding="utf-8")
    for field in ["grounded_in", "source_changed_since_approval"]:
        assert field in text, f"the verdict shape must show {field}"
    assert "the caller writes" in text.lower(), (
        "the judge must be told which fields the caller adds after it returns"
    )
