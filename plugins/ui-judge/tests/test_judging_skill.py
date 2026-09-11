import pytest

from conftest import frontmatter

REQUIRED_ORDER = ["RESOLVE", "RESET", "WALK", "CHECK", "RULE", "WRITE"]


@pytest.fixture
def skill(plugin_root):
    return (plugin_root / "skills" / "judging-missions" / "SKILL.md").read_text(
        encoding="utf-8"
    )


@pytest.fixture
def meta(plugin_root):
    text = (plugin_root / "skills" / "judging-missions" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    return frontmatter(text, "judging-missions/SKILL.md")


def test_skill_declares_name_and_description(meta):
    assert meta["name"] == "judging-missions"
    assert meta["description"].strip()


def test_the_six_stages_appear_in_order(skill):
    positions = [skill.find(stage) for stage in REQUIRED_ORDER]
    assert all(position != -1 for position in positions), (
        f"a stage is missing: {dict(zip(REQUIRED_ORDER, positions))}"
    )
    assert positions == sorted(positions), "the stages are out of order"


def test_it_dispatches_both_agents(skill):
    assert "mission-driver" in skill
    assert "mission-judge" in skill


def test_it_says_the_judge_never_sees_the_application(skill):
    lowered = skill.lower()
    assert "never sees the application" in lowered or "cannot open a browser" in lowered


def test_it_runs_missions_one_after_another(skill):
    lowered = skill.lower()
    assert "one after another" in lowered
    assert "at the same time" in lowered  # it must say NOT to


def test_it_checks_the_source_hash_before_it_opens_a_browser(skill):
    assert "source_hash.py" in skill
    position_hash = skill.find("source_hash.py")
    position_walk = skill.find("WALK")
    assert position_hash < position_walk, "drift is checked before the walk"


def test_it_names_the_four_verdicts(skill):
    for verdict in ["pass", "app-broken", "spec-stale", "unclear"]:
        assert verdict in skill


def test_it_runs_the_deterministic_checks_before_the_model(skill):
    assert skill.find("CHECK") < skill.find("RULE")


def test_the_scenario_is_the_unit_of_judgement(skill):
    """Spec 4.1: each scenario gets its own verdict."""
    lowered = skill.lower()
    assert "for each scenario" in lowered, (
        "the skill must loop over scenarios, not only over missions"
    )
    assert "every scenario passes" in lowered, (
        "the mission verdict must roll up from the scenario verdicts"
    )


def test_it_marks_a_drifted_mission_for_review(skill):
    """Spec 4.1 and 7: a changed source makes the mission need re-approval."""
    assert "needs review" in skill, (
        "a mission whose source changed must be marked, or it is judged as "
        "approved forever"
    )


def test_it_separates_an_unreadable_mission_from_real_drift(skill):
    """source_hash.py exits 2 when the mission itself cannot be read. Reading
    every non-zero code as drift would mark a mission `needs review` and say a
    document changed, when in truth nothing was checked at all."""
    lowered = skill.lower()
    assert "exit code" in lowered, "the skill must read the exit code, not just non-zero"
    assert "| 2 |" in skill, "the skill must say what exit code 2 means"


def test_it_reads_the_missions_folder_from_the_config(skill):
    """A search over the whole repository finds the plugin's own template and
    judges it as if somebody wrote it as a mission."""
    assert "missions_dir" in skill


def test_it_carries_on_when_the_project_has_no_reset_command(skill):
    """Setup allows `there is none`. Reading an empty command as a failed one
    stops every scenario in such a project."""
    lowered = skill.lower()
    assert "skip this step" in lowered, (
        "RESET must say what to do when reset_command is empty"
    )


def test_a_fault_from_an_earlier_scenario_is_not_a_hard_failure(skill):
    """The browser keeps running between scenarios, and a hard failure cannot
    be lifted. One console error in scenario 1 would otherwise rule every
    later scenario `app-broken`."""
    lowered = skill.lower()
    assert "first step" in lowered, (
        "CHECK must read only this scenario's console and network entries"
    )
    assert "own origin" in lowered, (
        "a third-party request is not the application failing"
    )


def test_the_caller_writes_the_two_verdict_fields(skill):
    """The judge never sees the drift result, so the skill must add these."""
    for field in ["grounded_in", "source_changed_since_approval"]:
        assert field in skill, f"WRITE must add {field} to verdict.json"


def test_a_failed_hard_check_cannot_be_lifted_by_the_judge(skill):
    """The deterministic checks run before the model, so the model must not be
    able to overrule them. Without this, a console error or a `Rule: never`
    breach could be recorded as a hard failure in CHECK and then written as
    `pass` in WRITE, because the judge is the only thing WRITE reads."""
    lowered = skill.lower()
    assert "hard failure" in lowered, "CHECK must name the hard failure"
    assert "cannot lift a hard failure" in lowered, (
        "the skill must say the judge's verdict cannot lift a hard failure"
    )
    assert "when a hard check failed, write `app-broken` instead" in lowered, (
        "WRITE must state which verdict wins when a hard check failed"
    )
