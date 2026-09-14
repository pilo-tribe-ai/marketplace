"""Static capability gate over every role (4.20.0).

A role declares `requires:` in a capability namespace — read_files, run_bash,
write_files — and what satisfies it is the tool set of the leaf its `role-class`
derives. `write_files` bound to a reader is the mismatch worth catching: the
relay:leaf-reader agent has no Write or Edit tool, so the dispatch cannot succeed.

This was documented in `skills/delegate-leaf/SKILL.md` and never enforced anywhere.
Worse, the documented helper call paired `requires:` against the binding's
`provides:` — capabilities against envelope tokens, two disjoint namespaces — so a
coordinator that actually ran it would have rejected every dispatch. It only looked
harmless because `scripts/capability-validate.js` had no runtime caller at all.

Dispatch itself is prose an LLM follows, so a runtime gate can always be skipped.
A static gate cannot: a mismatched role fails the suite before it can ever be
dispatched. That is strictly stronger, and it is the same reasoning that makes
`agents/` inventory tests worth more than a runtime registration check.
"""


import re

from pathlib import Path

import pytest

from conftest import parse_frontmatter

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
ROLES_DIR = PLUGIN_ROOT / "roles"
AGENTS_DIR = PLUGIN_ROOT / "agents"
VALIDATOR = PLUGIN_ROOT / "scripts" / "capability-validate.js"

CAPABILITY_TOOLS = {
    "read_files": {"Read"},
    "run_bash": {"Bash"},
    "write_files": {"Write", "Edit"},
}

ROLE_CLASS_TO_LEAF = {"writer": "leaf-worker", "reader": "leaf-reader"}


def _role_files():
    return sorted(p for p in ROLES_DIR.glob("*.md") if p.name != "README.md")


def _leaf_tools(slug: str) -> set:
    fm, _ = parse_frontmatter(AGENTS_DIR / f"{slug}.md")
    tools = fm.get("tools", [])
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",")]
    return set(tools)


class TestEveryRoleIsSatisfiableByItsLeaf:
    def test_there_are_roles(self):
        assert _role_files(), "no role files found — guard has gone vacuous"

    @pytest.mark.parametrize("path", _role_files(), ids=lambda p: p.stem)
    def test_requires_is_satisfied_by_the_derived_leaf(self, path):
        fm, _ = parse_frontmatter(path)
        role_class = fm.get("role-class")
        leaf = ROLE_CLASS_TO_LEAF.get(role_class)
        assert leaf, f"{path.stem}: unexpected role-class {role_class!r}"

        tools = _leaf_tools(leaf)
        assert tools, f"{leaf}.md declares no tools — cannot evaluate the gate"

        unsatisfied = []
        for cap in fm.get("requires", []) or []:
            needed = CAPABILITY_TOOLS.get(cap)
            assert needed, (
                f"{path.stem}: unmapped capability {cap!r}. Add it to CAPABILITY_TOOLS "
                f"in scripts/capability-validate.js and here, or fix the typo — an "
                f"unknown capability must never read as satisfied."
            )
            if not needed <= tools:
                unsatisfied.append((cap, sorted(needed - tools)))

        assert not unsatisfied, (
            f"{path.stem} (role-class: {role_class} → relay:{leaf}) declares "
            f"capabilities its leaf cannot satisfy: {unsatisfied}"
        )

    def test_a_writer_capability_on_a_reader_would_be_caught(self):
        """Guards the gate against going vacuous: it must be able to fail."""
        reader_tools = _leaf_tools("leaf-reader")
        assert not CAPABILITY_TOOLS["write_files"] <= reader_tools, (
            "leaf-reader has gained Write/Edit — the capability gate can no longer "
            "distinguish a writer role bound to a reader, and this suite would pass "
            "a mismatch it exists to catch"
        )


class TestValidatorMatchesThisTable:
    """The JS helper and this module must not drift apart."""

    def test_validator_ships_and_exposes_the_gate(self):
        assert VALIDATOR.is_file(), "scripts/capability-validate.js missing"
        src = VALIDATOR.read_text()
        assert "validateRoleAgainstTools" in src, (
            "capability-validate.js must export the role-vs-tools gate"
        )

    def test_capability_map_agrees_with_the_validator(self):
        src = VALIDATOR.read_text()
        block = re.search(r"CAPABILITY_TOOLS = \{(.*?)\};", src, re.S)
        assert block, "could not locate CAPABILITY_TOOLS in capability-validate.js"
        js_caps = set(re.findall(r"^\s*(\w+):", block.group(1), re.M))
        assert js_caps == set(CAPABILITY_TOOLS), (
            f"capability map drift — validator has {sorted(js_caps)}, "
            f"this module has {sorted(CAPABILITY_TOOLS)}"
        )

    def test_validator_test_suite_exercises_real_namespaces(self):
        """The pre-4.20.0 JS tests used abstract "a"/"b" strings, which is how the
        namespace mismatch stayed invisible. `node --test` on the suite itself is run
        by test_capability_validate.py; this asserts the suite is worth running."""
        tests = (VALIDATOR.parent / "capability-validate.test.js").read_text()
        for token in ("write_files", "READER_TOOLS", "ROLE_DONE"):
            assert token in tests, (
                f"capability-validate.test.js must exercise {token!r} — a suite over "
                f"abstract strings cannot catch a namespace error"
            )


class TestDelegateLeafDocumentsTheCorrectPairing:
    SKILL = PLUGIN_ROOT / "skills" / "delegate-leaf" / "SKILL.md"

    def test_does_not_document_the_requires_vs_provides_pairing(self):
        text = self.SKILL.read_text()
        assert "validate(roleRequires, bindingProvides)" not in text, (
            "delegate-leaf/SKILL.md still documents pairing `requires:` against the "
            "binding's `provides:`. Those are disjoint namespaces — capabilities vs "
            "envelope tokens — so that check rejects every dispatch."
        )

    def test_documents_the_tool_set_pairing(self):
        text = self.SKILL.read_text()
        assert "validateRoleAgainstTools" in text, (
            "delegate-leaf/SKILL.md must name the gate that is actually correct"
        )
