"""Guard tests for dispatching-acpx-agents/SKILL.md: ROLE_RESULT enum, envelope contract."""
from pathlib import Path
import pytest

SKILL = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "dispatching-acpx-agents" / "SKILL.md"


class TestRoleResultEnum:
    def test_skill_file_exists(self):
        assert SKILL.is_file()

    def test_needs_decision_in_role_result_enum(self):
        body = SKILL.read_text()
        assert "NEEDS_DECISION" in body, \
            "SKILL.md must include NEEDS_DECISION in the ROLE_RESULT enum"

    def test_five_result_values_documented(self):
        body = SKILL.read_text()
        for val in ("DONE", "NOT_DONE", "BLOCKED", "ERRORED", "NEEDS_DECISION"):
            assert val in body, f"SKILL.md must document ROLE_RESULT={val}"

    def test_driver_envelope_section_present(self):
        body = SKILL.read_text()
        assert "Driver envelope contract" in body or "driver envelope" in body.lower(), \
            "SKILL.md must have a driver envelope contract section"

    def test_stale_acpx_max_turns_not_in_driver_vars(self):
        body = SKILL.read_text()
        # ACPX_MAX_TURNS was a stale var; it must not appear as a driver env var
        # (RELAY_MAX_TURNS replaces it)
        assert "ACPX_MAX_TURNS" not in body or "RELAY_MAX_TURNS" in body, \
            "SKILL.md must not reference the stale ACPX_MAX_TURNS without replacing it with RELAY_MAX_TURNS"

    def test_relay_max_turns_documented(self):
        body = SKILL.read_text()
        assert "RELAY_MAX_TURNS" in body, \
            "SKILL.md must document the RELAY_MAX_TURNS env var in the sidecar contract"

    def test_relay_role_path_documented(self):
        body = SKILL.read_text()
        assert "RELAY_ROLE_PATH" in body, \
            "SKILL.md must document RELAY_ROLE_PATH as the documented external role path var"

    def test_acpx_session_name_override_documented(self):
        body = SKILL.read_text()
        assert "ACPX_SESSION_NAME_OVERRIDE" in body, \
            "SKILL.md must document ACPX_SESSION_NAME_OVERRIDE"
