"""Unit tests for the naming grammar bg-launch.sh --check-name validates (bg dispatch
contract §1.2 — docs/bg-dispatch-contract.md).

Drives `bash scripts/bg-launch.sh --check-name <name>`. This mode starts no child.
"""

import subprocess

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "bg-launch.sh"
ROLES_DIR = PLUGIN_ROOT / "roles"


def _check(name):
    return subprocess.run(["bash", str(SCRIPT), "--check-name", name],
                           capture_output=True, text=True)


def _real_role():
    """One real role stem from roles/*.md, for building valid test names."""
    for f in sorted(ROLES_DIR.glob("*.md")):
        if f.stem != "README":
            return f.stem
    raise AssertionError("no roles found — fixture setup is broken")


def test_accepts_the_spec_example():
    result = _check("roi-dashboard-implementer-feature-a-7f3c")
    assert result.returncode == 0, result.stderr
    assert "RELAY_BG_NAME_OK=1" in result.stdout


def test_accepts_the_orchestrator_shape():
    role = _real_role()
    result = _check(f"myapp-{role}-7f3c")
    assert result.returncode == 0, result.stderr


def test_rejects_a_name_with_no_runid_suffix():
    role = _real_role()
    result = _check(f"myapp-{role}")
    assert result.returncode == 2


def test_rejects_a_runid_that_is_too_short_or_too_long():
    role = _real_role()
    assert _check(f"myapp-{role}-abc").returncode == 2      # 3 chars
    assert _check(f"myapp-{role}-abcdefghi").returncode == 2  # 9 chars


def test_rejects_uppercase_and_underscore():
    role = _real_role()
    assert _check(f"MyApp-{role}-7f3c").returncode == 2
    assert _check(f"myapp_{role}_7f3c").returncode == 2


def test_accepts_63_characters_and_rejects_64():
    role = "scout"
    # Build a name of exactly 63 characters ending in a valid runid.
    runid = "7f3c"
    suffix = f"-{role}-{runid}"
    pad_len = 63 - len(suffix)
    padded_63 = ("p" * pad_len) + suffix
    assert len(padded_63) == 63
    assert _check(padded_63).returncode == 0, _check(padded_63).stderr

    padded_64 = "p" + padded_63  # 64 characters, otherwise identical
    assert len(padded_64) == 64
    assert _check(padded_64).returncode == 2


def test_rejects_a_role_token_that_is_not_on_the_roster():
    result = _check("roi-dashboard-wizard-feature-a-7f3c")
    assert result.returncode == 2
    assert "roster" in result.stderr.lower()


def test_roster_source_is_not_empty():
    """A vacuous roster would accept everything. Confirm the roster the validator
    reads has more than ten real roles by checking that ten distinct real roles all
    validate at the same fixed position."""
    stems = sorted(f.stem for f in ROLES_DIR.glob("*.md") if f.stem != "README")
    assert len(stems) > 10, "fixture assumption broken: roles/*.md has too few roles"
    for role in stems[:10]:
        result = _check(f"someproduct-{role}-7f3c")
        assert result.returncode == 0, f"{role} should validate: {result.stderr}"


def test_validator_never_parses_product_or_goal():
    """A product slug that itself holds a role word is still accepted — the check is
    a roster hit at a fixed position, not a parse."""
    result = _check("implementer-tools-scout-feature-a-7f3c")
    assert result.returncode == 0, result.stderr
