"""Guard tests: NEEDS_DECISION: first-line branch in all three session drivers."""
from pathlib import Path
import pytest

DRIVER_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "dispatching-acpx-agents"
DRIVERS = ["claude-session-driver.sh", "codex-session-driver.sh", "opencode-session-driver.sh"]


@pytest.mark.parametrize("driver", DRIVERS)
class TestNeedsDecisionBranch:
    def test_driver_exists(self, driver):
        assert (DRIVER_DIR / driver).is_file()

    def test_needs_decision_first_line_branch(self, driver):
        body = (DRIVER_DIR / driver).read_text()
        assert "^NEEDS_DECISION:" in body, \
            f"{driver}: must have a first-line branch matching ^NEEDS_DECISION:"

    def test_emits_role_result_needs_decision(self, driver):
        body = (DRIVER_DIR / driver).read_text()
        assert "ROLE_RESULT=NEEDS_DECISION" in body, \
            f"{driver}: needs-decision branch must emit ROLE_RESULT=NEEDS_DECISION"

    def test_emits_question_text(self, driver):
        body = (DRIVER_DIR / driver).read_text()
        assert "QUESTION_TEXT=" in body, \
            f"{driver}: needs-decision branch must emit QUESTION_TEXT="

    def test_needs_decision_before_blocked_or_at_same_level(self, driver):
        body = (DRIVER_DIR / driver).read_text()
        nd_idx = body.find("NEEDS_DECISION:")
        blocked_idx = body.find("^BLOCKED:")
        assert nd_idx != -1, f"{driver}: NEEDS_DECISION: branch missing"
        assert blocked_idx != -1, f"{driver}: BLOCKED: branch missing (should already exist)"

    def test_needs_decision_exits_zero(self, driver):
        body = (DRIVER_DIR / driver).read_text()
        # After the NEEDS_DECISION block we must see exit 0 (not exit 1).
        nd_idx = body.find("ROLE_RESULT=NEEDS_DECISION")
        assert nd_idx != -1
        segment = body[nd_idx: nd_idx + 300]
        assert "exit 0" in segment, \
            f"{driver}: needs-decision branch must exit 0"

    def test_no_sessions_close_in_needs_decision_branch(self, driver):
        body = (DRIVER_DIR / driver).read_text()
        # drivers must NOT call sessions close — that belongs to the watcher
        assert "sessions close" not in body, \
            f"{driver}: drivers must never call sessions close (watcher owns it)"
