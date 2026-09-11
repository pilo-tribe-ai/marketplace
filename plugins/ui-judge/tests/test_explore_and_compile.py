import pytest

from conftest import frontmatter


def read(plugin_root, *parts):
    return plugin_root.joinpath(*parts).read_text(encoding="utf-8")


@pytest.fixture
def explore(plugin_root):
    return read(plugin_root, "skills", "exploring-web-apps", "SKILL.md")


@pytest.fixture
def compile_skill(plugin_root):
    return read(plugin_root, "skills", "compiling-missions", "SKILL.md")


def test_both_skills_declare_a_name(plugin_root, explore, compile_skill):
    for text, name in ((explore, "exploring-web-apps"), (compile_skill, "compiling-missions")):
        meta = frontmatter(text, f"{name}/SKILL.md")
        assert meta["name"] == name


def test_explore_forbids_guessing_an_address(explore):
    lowered = explore.lower()
    assert "do not guess" in lowered
    assert "click" in lowered


def test_explore_writes_proposals_to_findings_not_missions(explore):
    assert "findings/" in explore
    assert "never write" in explore.lower() or "do not write" in explore.lower()


def test_explore_reports_controls_with_no_test_id(explore):
    lowered = explore.lower()
    assert "data-testid" in lowered or "test id" in lowered


def test_explore_has_a_step_budget(explore):
    assert "step_budget" in explore or "budget" in explore.lower()


def test_compile_requires_three_passes_in_a_row(compile_skill):
    lowered = compile_skill.lower()
    assert "three" in lowered or "passes_needed_to_compile" in compile_skill
    assert "in a row" in lowered


def test_compile_uses_the_transform_script(compile_skill):
    assert "mission_to_plan.py" in compile_skill


def test_compile_hands_over_to_the_playwright_generator(compile_skill):
    lowered = compile_skill.lower()
    assert "generator" in lowered
    assert "1.56" in compile_skill


def test_the_failed_transform_branch_does_not_exit_zero(compile_skill):
    """`... || { rm; echo; }` ends on an echo, which succeeds, so the whole
    line reports a failed transform as a good step."""
    assert "exit 1" in compile_skill, (
        "the failure branch of the transform must exit non-zero"
    )


def test_compile_does_not_repair_a_broken_test(compile_skill):
    lowered = compile_skill.lower()
    assert "healer" in lowered


def test_compile_says_the_plan_keeps_the_order_of_the_mission(compile_skill):
    """The prose said `Then` becomes expected results. The plan now puts each
    check under the step above it. Prose that says otherwise sends the next
    reader to write a test that checks everything at the end."""
    assert "expect:" in compile_skill
    assert "keeps the order" in compile_skill
