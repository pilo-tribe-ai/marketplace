"""
Guard tests for the fixer landing contract — relay v4.1.0.

Mirrors test_dispatch_contract.py pattern: text/structure guards on markdown files,
no subprocess invocations, no mocking.

Coverage:
  - EXPECTED_HEAD input slot in all three fixer roles.
  - base-mismatch abort text in all three fixer roles.
  - landing-verify contract sections in dispatching-in-session-agents,
    dispatching-acpx-agents, delegate-leaf, delegate-and-watch, refining/SKILL.md.
  - Persist destination clause in adapters/pr.md.
  - Stale "behaviorally unproven" banner gone from refining-prs/SKILL.md.
  - landing-verify present in dispatch-contract.md and refinement-contract.md.
"""
from pathlib import Path
import pytest

RELAY = Path(__file__).resolve().parent.parent.parent.parent

ROLES = RELAY / "roles"
SKILLS = RELAY / "skills"
DOCS = RELAY / "docs"

FIX_CODER = ROLES / "fix-coder.md"
SPEC_FIXER = ROLES / "spec-fixer.md"
PLAN_FIXER = ROLES / "plan-fixer.md"

DISPATCH_IN_SESSION = SKILLS / "dispatching-in-session-agents" / "SKILL.md"
DISPATCH_ACPX = SKILLS / "dispatching-acpx-agents" / "SKILL.md"
DELEGATE_LEAF = SKILLS / "delegate-leaf" / "SKILL.md"
DELEGATE_WATCH = SKILLS / "delegate-and-watch" / "SKILL.md"
REFINING = SKILLS / "refining" / "SKILL.md"
PR_ADAPTER = SKILLS / "refining" / "adapters" / "pr.md"
REFINING_PRS = SKILLS / "refining-prs" / "SKILL.md"

DISPATCH_CONTRACT = DOCS / "dispatch-contract.md"
REFINEMENT_CONTRACT = DOCS / "refinement-contract.md"


class TestFixerRolesExpectedHeadSlot:
    """EXPECTED_HEAD input slot present in all three fixer role files."""

    def test_fix_coder_expected_head_slot(self):
        body = FIX_CODER.read_text()
        assert "EXPECTED_HEAD" in body, \
            "fix-coder.md must declare EXPECTED_HEAD input slot"

    def test_spec_fixer_expected_head_slot(self):
        body = SPEC_FIXER.read_text()
        assert "EXPECTED_HEAD" in body, \
            "spec-fixer.md must declare EXPECTED_HEAD input slot"

    def test_plan_fixer_expected_head_slot(self):
        body = PLAN_FIXER.read_text()
        assert "EXPECTED_HEAD" in body, \
            "plan-fixer.md must declare EXPECTED_HEAD input slot"


class TestFixerRolesBaseMismatchAbort:
    """base-mismatch abort text present in all three fixer role files."""

    def test_fix_coder_base_mismatch(self):
        body = FIX_CODER.read_text()
        assert "base-mismatch" in body, \
            "fix-coder.md must include 'base-mismatch' abort text"

    def test_spec_fixer_base_mismatch(self):
        body = SPEC_FIXER.read_text()
        assert "base-mismatch" in body, \
            "spec-fixer.md must include 'base-mismatch' abort text"

    def test_plan_fixer_base_mismatch(self):
        body = PLAN_FIXER.read_text()
        assert "base-mismatch" in body, \
            "plan-fixer.md must include 'base-mismatch' abort text"

    def test_fix_coder_preflight_section(self):
        body = FIX_CODER.read_text()
        assert "Pre-Flight Base Pin" in body, \
            "fix-coder.md must have a 'Pre-Flight Base Pin' section"

    def test_spec_fixer_preflight_section(self):
        body = SPEC_FIXER.read_text()
        assert "Pre-Flight Base Pin" in body, \
            "spec-fixer.md must have a 'Pre-Flight Base Pin' section"

    def test_plan_fixer_preflight_section(self):
        body = PLAN_FIXER.read_text()
        assert "Pre-Flight Base Pin" in body, \
            "plan-fixer.md must have a 'Pre-Flight Base Pin' section"


class TestDispatchSkillsLandingVerify:
    """landing-verify contract sections present in dispatch and delegation skills."""

    def test_dispatching_in_session_landing_verify(self):
        body = DISPATCH_IN_SESSION.read_text()
        assert "landing-verify" in body, \
            "dispatching-in-session-agents/SKILL.md must include landing-verify contract"

    def test_dispatching_in_session_expected_head(self):
        body = DISPATCH_IN_SESSION.read_text()
        assert "EXPECTED_HEAD" in body, \
            "dispatching-in-session-agents/SKILL.md must reference EXPECTED_HEAD"

    def test_dispatching_in_session_worktree_path(self):
        body = DISPATCH_IN_SESSION.read_text()
        assert "WORKTREE_PATH" in body, \
            "dispatching-in-session-agents/SKILL.md must reference WORKTREE_PATH slot"

    def test_dispatching_acpx_landing_verify(self):
        body = DISPATCH_ACPX.read_text()
        assert "landing-verify" in body, \
            "dispatching-acpx-agents/SKILL.md must include landing-verify contract"

    def test_dispatching_acpx_slot_expected_head(self):
        body = DISPATCH_ACPX.read_text()
        assert "SLOT_EXPECTED_HEAD" in body, \
            "dispatching-acpx-agents/SKILL.md must reference SLOT_EXPECTED_HEAD materialization"

    def test_dispatching_acpx_slot_worktree_path(self):  # [inferred]
        body = DISPATCH_ACPX.read_text()  # [inferred]
        assert ("SLOT_WORKTREE_PATH" in body), (  # [inferred]
            "dispatching-acpx-agents/SKILL.md must reference SLOT_WORKTREE_PATH materialization")  # [inferred]

    def test_dispatching_acpx_worktree_path(self):  # [inferred]
        body = DISPATCH_ACPX.read_text()  # [inferred]
        assert ("WORKTREE_PATH" in body), (  # [inferred]
            "dispatching-acpx-agents/SKILL.md must reference WORKTREE_PATH slot")  # [inferred]

    def test_delegate_leaf_landing_verify(self):
        body = DELEGATE_LEAF.read_text()
        assert "landing-verify" in body, \
            "delegate-leaf/SKILL.md must include landing-verify sub-step in step 4"

    def test_delegate_and_watch_landing_verify(self):
        body = DELEGATE_WATCH.read_text()
        assert "landing-verify" in body, \
            "delegate-and-watch/SKILL.md must include landing-verify in done-gate"

    def test_delegate_and_watch_landing_verify_failed(self):
        body = DELEGATE_WATCH.read_text()
        assert "landing_verify_failed" in body, \
            "delegate-and-watch/SKILL.md must reference landing_verify_failed errored classification"


class TestRefiningLandingVerify:
    """landing-verify step present in refining/SKILL.md."""

    def test_refining_skill_landing_verify(self):
        body = REFINING.read_text()
        assert "landing-verify" in body, \
            "refining/SKILL.md must include landing-verify step between fixer.apply and adapter.post_fix"

    def test_refining_skill_landing_verify_contract_section(self):
        body = REFINING.read_text()
        assert "Landing Verify Contract" in body, \
            "refining/SKILL.md must have a 'Landing Verify Contract' section"


class TestPrAdapterPersistDestinationClause:
    """Persist destination clause present in adapters/pr.md."""

    def test_pr_adapter_landing_contract_integration(self):
        body = PR_ADAPTER.read_text()
        assert "landing-verify" in body, \
            "adapters/pr.md must include landing-verify integration"

    def test_pr_adapter_clean_tree_skip(self):
        body = PR_ADAPTER.read_text()
        assert "clean-tree skip" in body, \
            "adapters/pr.md must document the clean-tree skip for persist()"

    def test_pr_adapter_snapshot_sha_injection(self):
        body = PR_ADAPTER.read_text()
        assert "Landing Contract Integration" in body, \
            "adapters/pr.md must have a 'Landing Contract Integration' section"


class TestRefiningPrsBannerRefresh:
    """Stale 'behaviorally unproven' banner removed from refining-prs/SKILL.md."""

    def test_stale_behaviorally_unproven_removed(self):
        body = REFINING_PRS.read_text()
        assert "behaviorally unproven" not in body.lower(), \
            "refining-prs/SKILL.md must not contain the stale 'behaviorally unproven' claim"

    def test_refine4_label_retained(self):
        body = REFINING_PRS.read_text()
        assert "REFINE-4" in body, \
            "refining-prs/SKILL.md must retain the REFINE-4 label for discoverability"

    def test_proven_runs_referenced(self):
        body = REFINING_PRS.read_text()
        assert "PR #43" in body and "PR #44" in body, \
            "refining-prs/SKILL.md must reference the two successful live runs (#43, #44)"


class TestContractDocLandingVerify:
    """landing-verify sections present in dispatch-contract.md and refinement-contract.md."""

    def test_dispatch_contract_landing_verify(self):
        body = DISPATCH_CONTRACT.read_text()
        assert "landing-verify" in body, \
            "docs/dispatch-contract.md must include landing-verify contract"

    def test_dispatch_contract_writer_role_section(self):
        body = DISPATCH_CONTRACT.read_text()
        assert "Writer-Role Landing Contract" in body, \
            "docs/dispatch-contract.md must have 'Writer-Role Landing Contract' section"

    def test_dispatch_contract_slot_expected_head(self):
        body = DISPATCH_CONTRACT.read_text()
        assert "SLOT_EXPECTED_HEAD" in body, \
            "docs/dispatch-contract.md must reference SLOT_EXPECTED_HEAD"

    def test_refinement_contract_landing_verify(self):
        body = REFINEMENT_CONTRACT.read_text()
        assert "landing-verify" in body, \
            "docs/refinement-contract.md must include landing-verify for pr adapter"


class TestFixerRolesWorktreePath:
    """WORKTREE_PATH input slot declared in all three fixer role files.

    An undeclared slot means {{WORKTREE_PATH}} in the role body is NOT substituted at
    runtime — the literal template text reaches the leaf, which will misparse the git
    command. Every fixer role that references {{WORKTREE_PATH}} in its Pre-Flight Base
    Pin section must declare it in input-slots.
    """

    def test_fix_coder_worktree_path_slot(self):
        body = FIX_CODER.read_text()
        assert "WORKTREE_PATH" in body, \
            "fix-coder.md must declare WORKTREE_PATH in input-slots"

    def test_spec_fixer_worktree_path_slot(self):
        body = SPEC_FIXER.read_text()
        assert "WORKTREE_PATH" in body, \
            "spec-fixer.md must declare WORKTREE_PATH in input-slots"

    def test_plan_fixer_worktree_path_slot(self):
        body = PLAN_FIXER.read_text()
        assert "WORKTREE_PATH" in body, \
            "plan-fixer.md must declare WORKTREE_PATH in input-slots"
