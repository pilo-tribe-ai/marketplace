import pytest

from conftest import PLUGIN_ROOT

# Relay-owned skills introduced by the obra-gap-port. Each is added to EXPECTED_SKILLS
# in test_plugin.py in the task that ships it; this guard asserts the file is actually
# present (EXPECTED_SKILLS parametrization only skips on absence).
# IMPORTANT: the remaining skill ("setting-up-relay") is appended to this
# list in the same task that ships its SKILL.md, so the suite stays green at every commit.
GAP_PORT_SKILLS = ["setting-up-relay"]


@pytest.mark.parametrize("name", GAP_PORT_SKILLS)
def test_gap_port_skill_present(name):
    path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
    assert path.is_file(), f"relay-owned skill {name} must ship a SKILL.md"
