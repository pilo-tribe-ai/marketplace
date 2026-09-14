import subprocess
import sys
from pathlib import Path

from conftest import load_script

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN_ROOT / "scripts" / "mission_to_plan.py"

MISSION = """\
# grounded-in: docs/user-guide.md#buying-an-item
@shopper @checkout
Feature: Checkout

  Scenario: A shopper buys one item
    Given I am signed in as a shopper
    When I add any item to my basket
    Then the basket shows one item
    When I begin checkout
    Then I see a total price

  Rule: never
    - an error in the browser console
    - a total of zero, blank, or "NaN"
"""


def load():
    return load_script("mission_to_plan")


def test_parse_reads_the_feature_name():
    assert load().parse(MISSION).feature == "Checkout"


def test_parse_reads_the_tags():
    assert load().parse(MISSION).tags == ["shopper", "checkout"]


def test_parse_reads_one_scenario():
    assert [s.name for s in load().parse(MISSION).scenarios] == [
        "A shopper buys one item"
    ]


def test_parse_keeps_the_steps_in_the_order_of_the_mission():
    """The moment at which each check holds is the whole point. A basket that
    shows one item and a basket that is empty are true at different moments."""
    module = load()
    scenario = module.parse(MISSION).scenarios[0]
    assert scenario.steps == [
        module.Step("does", "I am signed in as a shopper"),
        module.Step("does", "I add any item to my basket"),
        module.Step("must", "the basket shows one item"),
        module.Step("does", "I begin checkout"),
        module.Step("must", "I see a total price"),
    ]


def test_parse_reads_the_never_list():
    assert load().parse(MISSION).never == [
        "an error in the browser console",
        'a total of zero, blank, or "NaN"',
    ]


def test_parse_handles_two_scenarios():
    text = (
        "Feature: X\n"
        "  Scenario: one\n"
        "    When I do a\n"
        "    Then b happens\n"
        "  Scenario: two\n"
        "    When I do c\n"
        "    Then d happens\n"
    )
    module = load()
    mission = module.parse(text)
    assert [s.name for s in mission.scenarios] == ["one", "two"]
    assert mission.scenarios[1].steps == [
        module.Step("does", "I do c"),
        module.Step("must", "d happens"),
    ]


def test_and_continues_the_kind_of_the_step_above_it():
    text = (
        "Feature: X\n"
        "  Scenario: one\n"
        "    Then a happens\n"
        "    And b happens\n"
    )
    module = load()
    scenario = module.parse(text).scenarios[0]
    assert scenario.steps == [
        module.Step("must", "a happens"),
        module.Step("must", "b happens"),
    ]


def test_to_plan_names_the_feature_and_the_scenario():
    plan = load().to_plan(load().parse(MISSION))
    assert "# Checkout" in plan
    assert "A shopper buys one item" in plan


def test_to_plan_puts_each_check_under_the_step_it_follows():
    """Two flat lists ask for a basket that shows one item and is empty at the
    same time. The generator then checks everything at the end, which fails
    against a working application, or drops a check without saying so."""
    plan = load().to_plan(load().parse(MISSION))
    assert "**Steps:**" in plan
    assert plan.count("- expect:") == 2
    assert (
        "2. I add any item to my basket\n"
        "   - expect: the basket shows one item\n"
        "3. I begin checkout\n"
        "   - expect: I see a total price"
    ) in plan


def test_to_plan_keeps_a_check_that_comes_before_any_step():
    """A dropped check is a test that asks for less than the mission asked
    for, and nothing says so."""
    text = "Feature: X\n  Scenario: one\n    Then a holds\n    When I do b\n"
    module = load()
    plan = module.to_plan(module.parse(text))
    assert "Before the first step:\n   - expect: a holds" in plan
    assert "1. I do b" in plan


def test_to_plan_carries_the_never_list_as_failure_criteria():
    plan = load().to_plan(load().parse(MISSION))
    assert "Failure criteria" in plan
    assert "an error in the browser console" in plan


def test_to_plan_holds_no_url_path_or_selector():
    """The plan inherits the mission's freedom from implementation detail."""
    module = load_script("mission_lint")
    plan = load().to_plan(load().parse(MISSION))
    assert module.lint_text(plan) == []


def test_a_missing_file_exits_two_and_prints_no_plan(tmp_path):
    """A shell redirect makes the target file before the script runs. If the
    script printed a part of a plan, or exited 1 with a traceback, the compile
    step would hand an empty plan to the Playwright generator."""
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.feature")],
        capture_output=True, text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stdout == ""
    assert "Traceback" not in done.stderr
    assert "cannot read" in done.stderr


def test_a_mission_with_no_scenario_exits_two_and_prints_no_plan(tmp_path):
    path = tmp_path / "m.feature"
    path.write_text("Feature: X\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stdout == ""
    assert "no Scenario" in done.stderr


def test_a_file_that_is_not_utf8_exits_two_and_prints_no_plan(tmp_path):
    """`UnicodeDecodeError` is not an `OSError`. Uncaught it ends the process
    with code 1 and a traceback, and code 1 is not one of the two answers this
    script gives."""
    path = tmp_path / "m.feature"
    path.write_bytes(b"Feature: \xff\xfe caf\xe9\n")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stdout == ""
    assert "Traceback" not in done.stderr
    assert "not valid UTF-8" in done.stderr


def test_an_extended_never_rule_still_opens_the_never_block():
    """`Rule: never happens` matched nothing, so every bullet under it was
    dropped in silence and the plan lost its failure criteria."""
    text = (
        "Feature: X\n"
        "  Scenario: one\n"
        "    When I do a\n"
        "  Rule: never happens\n"
        "    - an error in the browser console\n"
    )
    module = load()
    mission = module.parse(text)
    assert mission.never == ["an error in the browser console"]
    assert "Failure criteria" in module.to_plan(mission)


def test_cli_prints_the_plan(tmp_path):
    path = tmp_path / "m.feature"
    path.write_text(MISSION, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert "# Checkout" in done.stdout
