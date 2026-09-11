import pytest
import yaml

from conftest import load_script

PLACEHOLDERS = ["TBD", "TODO", "FIXME", "XXX"]


@pytest.fixture
def templates(plugin_root):
    return plugin_root / "templates"


def load_lint(plugin_root):
    return load_script("mission_lint")


def test_every_template_exists(templates):
    for name in ["config.yaml", "credentials.md", "mission.feature"]:
        assert (templates / name).is_file(), f"templates/{name} is missing"


def test_config_is_valid_yaml_with_the_required_keys(templates):
    data = yaml.safe_load((templates / "config.yaml").read_text(encoding="utf-8"))
    for key in ["base_url", "start_command", "reset_command", "roles", "missions_dir"]:
        assert key in data, f"config.yaml has no {key}"


def test_config_declares_sequential_runs(templates):
    data = yaml.safe_load((templates / "config.yaml").read_text(encoding="utf-8"))
    assert data["run_missions"] == "one-after-another"


def test_the_example_mission_passes_the_lint(templates, plugin_root):
    text = (templates / "mission.feature").read_text(encoding="utf-8")
    assert load_lint(plugin_root).lint_text(text) == []


def test_credentials_template_holds_no_real_secret(templates):
    text = (templates / "credentials.md").read_text(encoding="utf-8").lower()
    assert "password:" not in text, "the template must never carry a value"
    assert "never" in text, "the template must tell the agent what never to do"


def test_no_template_holds_a_placeholder(templates):
    for path in templates.iterdir():
        text = path.read_text(encoding="utf-8")
        for word in PLACEHOLDERS:
            assert word not in text, f"{path.name} still holds {word}"


def test_the_example_mission_makes_a_plan_that_keeps_its_order(templates):
    """The shipped mission runs three When/Then cycles. Every mission written
    from this template copies its shape, so the template is where a lost order
    spreads from."""
    module = load_script("mission_to_plan")
    text = (templates / "mission.feature").read_text(encoding="utf-8")
    plan = module.to_plan(module.parse(text))
    assert (
        "5. I pay with the test card\n"
        "   - expect: the order is confirmed\n"
        "   - expect: the basket is empty"
    ) in plan
