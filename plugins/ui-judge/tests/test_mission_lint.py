import subprocess
import sys
from pathlib import Path

import pytest

from conftest import load_script

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN_ROOT / "scripts" / "mission_lint.py"


def load():
    return load_script("mission_lint")


GOOD = """\
# grounded-in: docs/user-guide.md#buying-an-item
# grounded-in-hash: 8f3c2a91
@shopper
Feature: Checkout

  Scenario: A shopper buys one item
    Given I am signed in as a shopper
    When I find where the site lists things for sale
    Then the basket shows one item
"""


def rules_for(text):
    return {finding.rule for finding in load().lint_text(text)}


def test_a_clean_mission_has_no_findings():
    assert load().lint_text(GOOD) == []


def test_a_grounded_in_comment_may_hold_a_file_path():
    # docs/user-guide.md#buying-an-item must not trip the url-path or css-id rule.
    assert load().lint_text("# grounded-in: docs/user-guide.md#buying-an-item\n") == []


def test_it_rejects_a_url_path():
    assert "url-path" in rules_for("    When I open /products\n")


def test_it_rejects_a_full_url():
    assert "url" in rules_for("    When I open https://example.com/cart\n")


def test_it_rejects_a_test_id():
    assert "test-id" in rules_for('    Then data-testid="cart-badge" shows one\n')


def test_it_rejects_an_aria_ref():
    assert "aria-ref" in rules_for("    When I click ref=e42\n")


def test_it_rejects_a_css_id_selector():
    assert "css-id" in rules_for("    When I click #checkout-button\n")


def test_it_rejects_a_selector_api_call():
    assert "selector-api" in rules_for("    When I click getByRole('button')\n")


def test_it_reports_every_match_on_a_line_not_only_the_first():
    """A writer who fixes one URL and runs the gate again must not meet the
    same line a second time."""
    findings = load().lint_text("    When I open /cart and then /checkout\n")
    assert [f.found for f in findings if f.rule == "url-path"] == ["/cart", "/checkout"]


def test_it_reports_the_line_number():
    findings = load().lint_text("Feature: X\n    When I open /cart\n")
    assert findings[0].line == 2


def test_cli_exits_zero_on_a_clean_file(tmp_path):
    path = tmp_path / "ok.feature"
    path.write_text(GOOD, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_cli_exits_one_and_names_the_rule_on_a_dirty_file(tmp_path):
    path = tmp_path / "bad.feature"
    path.write_text("Feature: X\n    When I open /cart\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert done.returncode == 1
    assert "url-path" in done.stdout
    assert "bad.feature" in done.stdout


# Exit code 1 means "a mission names implementation detail". A path that does not
# exist is a different thing, and it must not borrow that code: a CI step with a
# typo in a filename would otherwise read exactly like a mission that failed the
# gate, and no one could tell the two apart from the exit code.
def test_a_missing_file_does_not_use_the_finding_exit_code(tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.feature")],
        capture_output=True, text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr


def test_a_missing_file_says_so_plainly_and_shows_no_traceback(tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.feature")],
        capture_output=True, text=True,
    )
    assert "Traceback" not in done.stderr
    assert "nope.feature" in done.stderr
    assert "cannot read" in done.stderr


def test_a_missing_file_does_not_stop_the_files_after_it(tmp_path):
    """One bad path must not hide the findings in the files beside it."""
    good = tmp_path / "bad.feature"
    good.write_text("Feature: X\n    When I open /cart\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nope.feature"), str(good)],
        capture_output=True, text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "url-path" in done.stdout


def test_a_file_that_is_not_utf8_does_not_use_the_finding_exit_code(tmp_path):
    """`UnicodeDecodeError` is not an `OSError`. Uncaught it ends the process
    with code 1, and code 1 says a mission names implementation detail."""
    path = tmp_path / "bad.feature"
    path.write_bytes(b"Feature: \xff\xfe caf\xe9\n")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "not valid UTF-8" in done.stderr
