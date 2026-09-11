"""
Guard tests for delegate_eligible field in bindings/presets.yaml (spec §5.1).

PRESETS-1: All roles declared eligible in the spec §5.1 table must have
           delegate_eligible: true.
PRESETS-2: All roles declared ineligible must have delegate_eligible: false.
PRESETS-3: Coverage guard — every role key in presets.yaml must appear in
           either the eligible or ineligible set so new roles cannot slip in
           without a deliberate eligibility decision.
"""
import pytest
import yaml

from conftest import PLUGIN_ROOT

PRESETS_PATH = PLUGIN_ROOT / "bindings" / "presets.yaml"

# Spec §5.1 eligibility table
ELIGIBLE_ROLES = {
    "scout",
    "spec-simulator",
    "plan-simulator",
    "plan-fixer",
    "plan-writer",
    "implementer",
    "fix-coder",
    "test-writer",
    "code-reviewer",
    "doc-reference-reviewer",
    # UI roles that need neither a browser nor screenshot vision.
    "ui-code-evaluator",
    "ui-generator",
}

INELIGIBLE_ROLES = {
    "panel-member",
    "panel-synthesizer",
    "panel-moderator",
    "spec-fixer",
    "spec-reviewer",
    "fix-planner",
    "scenario-writer",
    "navigator",
    "server-runner",
    # The three browser critics stay in-session: ui-visual-evaluator must READ
    # rendered screenshots to score design_quality/originality, and relay models
    # no vision capability, so a non-vision worker would score blind and silently
    # corrupt the scored-convergence loop. ux/accessibility drive a shared
    # Playwright browser alongside it.
    "ui-visual-evaluator",
    "ui-ux-evaluator",
    "ui-accessibility-evaluator",
}


def _load_roles():
    """Load and return the roles dict from presets.yaml."""
    assert PRESETS_PATH.is_file(), f"presets.yaml not found at {PRESETS_PATH}"
    with open(PRESETS_PATH) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict) and "roles" in data, (
        "presets.yaml must have a top-level 'roles' key"
    )
    return data["roles"]


@pytest.fixture(scope="module")
def roles():
    return _load_roles()


class TestDelegateEligiblePresent:
    """PRESETS-1 + PRESETS-2: delegate_eligible must be present and correctly set."""

    @pytest.mark.parametrize("slug", sorted(ELIGIBLE_ROLES))
    def test_eligible_role_is_true(self, roles, slug):
        assert slug in roles, f"Role '{slug}' is missing from presets.yaml roles"
        entry = roles[slug]
        assert "delegate_eligible" in entry, (
            f"Role '{slug}' is missing the 'delegate_eligible' field"
        )
        assert entry["delegate_eligible"] is True, (
            f"Role '{slug}' should have delegate_eligible: true (spec §5.1 eligible), "
            f"got: {entry['delegate_eligible']!r}"
        )

    @pytest.mark.parametrize("slug", sorted(INELIGIBLE_ROLES))
    def test_ineligible_role_is_false(self, roles, slug):
        assert slug in roles, f"Role '{slug}' is missing from presets.yaml roles"
        entry = roles[slug]
        assert "delegate_eligible" in entry, (
            f"Role '{slug}' is missing the 'delegate_eligible' field"
        )
        assert entry["delegate_eligible"] is False, (
            f"Role '{slug}' should have delegate_eligible: false (spec §5.1 ineligible), "
            f"got: {entry['delegate_eligible']!r}"
        )


class TestEligibilityCoverageGuard:
    """PRESETS-3: every role in presets.yaml must appear in the eligibility sets."""

    def test_all_roles_covered(self, roles):
        known = ELIGIBLE_ROLES | INELIGIBLE_ROLES
        uncovered = set(roles.keys()) - known
        assert not uncovered, (
            f"The following role(s) are not covered by the eligibility table "
            f"in test_presets_eligibility.py — add each to ELIGIBLE_ROLES or "
            f"INELIGIBLE_ROLES per spec §5.1: {sorted(uncovered)}"
        )

    def test_no_phantom_roles_in_eligible(self, roles):
        """Roles listed in ELIGIBLE_ROLES must actually exist in presets.yaml."""
        missing = ELIGIBLE_ROLES - set(roles.keys())
        assert not missing, (
            f"ELIGIBLE_ROLES references role(s) not found in presets.yaml: {sorted(missing)}"
        )

    def test_no_phantom_roles_in_ineligible(self, roles):
        """Roles listed in INELIGIBLE_ROLES must actually exist in presets.yaml."""
        missing = INELIGIBLE_ROLES - set(roles.keys())
        assert not missing, (
            f"INELIGIBLE_ROLES references role(s) not found in presets.yaml: {sorted(missing)}"
        )

    def test_eligible_and_ineligible_sets_disjoint(self):
        overlap = ELIGIBLE_ROLES & INELIGIBLE_ROLES
        assert not overlap, (
            f"The following role(s) appear in both ELIGIBLE_ROLES and INELIGIBLE_ROLES: "
            f"{sorted(overlap)}"
        )
