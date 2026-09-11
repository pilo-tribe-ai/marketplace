"""
Guard tests for agent parity invariants (AGENT-1, AGENT-2).

AGENT-1: the LOAD-BEARING "One-Shot Execution Contract" block must be byte-identical
         (slot-token-normalized) across the fixer roles (spec-fixer, plan-fixer).
AGENT-2: the REVIEW Output Contract block + envelope_tokens must stay in lockstep
         across the three reviewer roles/agents (spec-reviewer, code-reviewer,
         doc-reference-reviewer).

Post-PR3 §7: spec-fixer, plan-fixer, spec-reviewer, and doc-reference-reviewer have
been moved from agents/<slug>.md to roles/<slug>.md. The parity invariants are
preserved by looking up each slug in agents/ first, then falling back to roles/.

These guards validate the already-correct tree. A future regression that drifts a fixer's
one-shot contract, or a reviewer's REVIEW contract / envelope tokens, will fail here.
"""
import re

import pytest

from conftest import PLUGIN_ROOT, parse_frontmatter


def _agent_or_role_body(slug):
    """Return the markdown body for a slug, checking agents/ first then roles/."""
    agent_path = PLUGIN_ROOT / "agents" / f"{slug}.md"
    if agent_path.is_file():
        _, body = parse_frontmatter(agent_path)
        return body
    role_path = PLUGIN_ROOT / "roles" / f"{slug}.md"
    assert role_path.is_file(), f"neither agents/{slug}.md nor roles/{slug}.md found"
    _, body = parse_frontmatter(role_path)
    return body


def _agent_body(slug):
    """Return the markdown body (frontmatter stripped) for agents/<slug>.md."""
    path = PLUGIN_ROOT / "agents" / f"{slug}.md"
    assert path.is_file(), f"agents/{slug}.md missing"
    _, body = parse_frontmatter(path)
    return body


# ---------------------------------------------------------------------------
# AGENT-1: fixer One-Shot Execution Contract block parity
# ---------------------------------------------------------------------------

FIXER_SLUGS = ["spec-fixer", "plan-fixer"]

# Normalize slot tokens so spec-fixer's {{SPEC_FILE_PATH}} and plan-fixer's {{PLAN_PATH}}
# are treated as equivalent, and the SPEC_PATH= / PLAN_PATH= output tokens are equivalent.
_SLOT_NORM_PATTERNS = [
    (re.compile(r"\{\{SPEC_FILE_PATH\}\}|\{\{PLAN_PATH\}\}"), "{{SUBJECT_PATH}}"),
    (re.compile(r"\bSPEC_PATH=|\bPLAN_PATH="), "SUBJECT_PATH="),
]


def _normalize_slot_tokens(text):
    for pattern, replacement in _SLOT_NORM_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _extract_section(body, marker):
    """Extract the section starting at `marker` up to the next H2/H3 heading (or EOF)."""
    idx = body.find(marker)
    assert idx != -1, f"could not find {marker!r} in agent body"
    block = body[idx:]
    end_match = re.search(r"\n#{2,3} ", block[len(marker):])
    if end_match:
        block = block[: len(marker) + end_match.start()]
    return block.strip()


class TestFixerOneShot:
    """AGENT-1: One-Shot block must be byte-identical after slot-token normalization."""

    MARKER = "One-Shot Execution Contract"

    def test_both_fixer_files_exist(self):
        for slug in FIXER_SLUGS:
            agent_path = PLUGIN_ROOT / "agents" / f"{slug}.md"
            role_path = PLUGIN_ROOT / "roles" / f"{slug}.md"
            assert agent_path.is_file() or role_path.is_file(), (
                f"neither agents/{slug}.md nor roles/{slug}.md found"
            )

    def test_one_shot_blocks_are_identical(self):
        blocks = {}
        for slug in FIXER_SLUGS:
            raw_block = _extract_section(_agent_or_role_body(slug), self.MARKER)
            blocks[slug] = _normalize_slot_tokens(raw_block)

        slugs = list(blocks)
        first = blocks[slugs[0]]
        for slug in slugs[1:]:
            assert blocks[slug] == first, (
                f"One-Shot Execution Contract block differs between {slugs[0]} and {slug} "
                f"(after slot-token normalization).\n"
                f"--- {slugs[0]} ---\n{first[:600]}\n\n"
                f"--- {slug} ---\n{blocks[slug][:600]}"
            )


# ---------------------------------------------------------------------------
# AGENT-2: reviewer REVIEW Output Contract parity
# ---------------------------------------------------------------------------

REVIEWER_SLUGS = ["spec-reviewer", "code-reviewer", "doc-reference-reviewer"]

REQUIRED_ENVELOPE_TOKENS = ["ROLE_DONE", "REVIEW"]


def _normalize_review_contract(block):
    """Collapse reviewer-specific placeholder lines (`<...>`) to a sentinel so the
    load-bearing REVIEW contract skeleton can be compared across reviewers in lockstep.
    The pass/fail token skeleton is shared; only the FAIL-block placeholder text is
    legitimately reviewer-specific."""
    out = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("<"):
            out.append("<PLACEHOLDER>")
        else:
            out.append(stripped)
    return "\n".join(out)


class TestReviewerOutputContract:
    """AGENT-2: REVIEW-contract block + envelope_tokens must be in lockstep across reviewers.

    Post-PR3 §7: spec-reviewer and doc-reference-reviewer moved to roles/<slug>.md.
    code-reviewer remains in agents/<slug>.md and still carries relay.envelope_tokens.
    For collapsed reviewers, output-tokens in role frontmatter replaces envelope_tokens.
    """

    MARKER = "## Output Contract"

    def test_all_reviewer_files_exist(self):
        for slug in REVIEWER_SLUGS:
            agent_path = PLUGIN_ROOT / "agents" / f"{slug}.md"
            role_path = PLUGIN_ROOT / "roles" / f"{slug}.md"
            assert agent_path.is_file() or role_path.is_file(), (
                f"neither agents/{slug}.md nor roles/{slug}.md found"
            )

    @pytest.mark.parametrize("slug", REVIEWER_SLUGS)
    def test_envelope_tokens_in_lockstep(self, slug):
        agent_path = PLUGIN_ROOT / "agents" / f"{slug}.md"
        if agent_path.is_file():
            # Kept registered agent: read relay.envelope_tokens
            fm, _ = parse_frontmatter(agent_path)
            relay = fm.get("relay") or {}
            tokens = relay.get("envelope_tokens")
            assert tokens == REQUIRED_ENVELOPE_TOKENS, (
                f"{slug}: relay.envelope_tokens must be exactly {REQUIRED_ENVELOPE_TOKENS}, got {tokens}"
            )
        else:
            # Collapsed role: read output-tokens from role frontmatter
            import yaml as _yaml
            role_path = PLUGIN_ROOT / "roles" / f"{slug}.md"
            assert role_path.is_file(), f"roles/{slug}.md missing"
            text = role_path.read_text()
            end = text.index("---", 3)
            rfm = _yaml.safe_load(text[3:end]) or {}
            tokens = rfm.get("output-tokens") or []
            assert sorted(tokens) == sorted(REQUIRED_ENVELOPE_TOKENS), (
                f"{slug}: role output-tokens must be exactly {REQUIRED_ENVELOPE_TOKENS}, got {tokens}"
            )

    @pytest.mark.parametrize("slug", REVIEWER_SLUGS)
    def test_body_has_review_pass_fail_end_and_role_done(self, slug):
        body = _agent_or_role_body(slug)
        for token in ("REVIEW=PASS", "REVIEW=FAIL", "REVIEW_END", "ROLE_DONE"):
            assert token in body, f"{slug}: body must contain {token}"

    def test_review_output_contract_blocks_are_identical(self):
        """The REVIEW Output Contract skeleton (modulo reviewer-specific placeholder lines)
        must be byte-identical across all three reviewers."""
        blocks = {}
        for slug in REVIEWER_SLUGS:
            raw_block = _extract_section(_agent_or_role_body(slug), self.MARKER)
            blocks[slug] = _normalize_review_contract(raw_block)

        first = blocks[REVIEWER_SLUGS[0]]
        for slug in REVIEWER_SLUGS[1:]:
            assert blocks[slug] == first, (
                f"REVIEW Output Contract block differs between {REVIEWER_SLUGS[0]} and {slug} "
                f"(after placeholder normalization).\n"
                f"--- {REVIEWER_SLUGS[0]} ---\n{first[:600]}\n\n"
                f"--- {slug} ---\n{blocks[slug][:600]}"
            )
