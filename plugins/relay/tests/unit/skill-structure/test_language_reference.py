"""Unit + gate tests for the relay language-reference validator.

Synthetic-fixture tests build a conformant doc from the validator's own
canonical sets, then mutate it to inject one violation at a time. The final
gate test runs the validator against the real shipped doc.
"""
import importlib.util
from pathlib import Path

# Load the validator module by file path (no package/conftest dependency).
_VALIDATOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts" / "validate_language_reference.py"
)
_spec = importlib.util.spec_from_file_location("validate_language_reference", _VALIDATOR_PATH)
vlr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vlr)


def build_valid_doc() -> str:
    """Emit a structurally-conformant language-reference doc from canonical sets."""
    lines = ["# Relay Language Reference", ""]

    # Authoring-guidelines preface (presence is all the gate checks).
    lines += ["## Authoring Guidelines", "", "1. Placeholder guideline.", ""]

    # L0 glossary table.
    lines += ["## L0 — Keyword Glossary", "", "| name | category | definition |", "|---|---|---|"]
    for name, category in vlr.L0_CATEGORY.items():
        lines.append(f"| {name} | {category} | definition of {name} |")
    lines.append("")

    # L1 pattern library table.
    lines += [
        "## L1 — Pattern Library",
        "",
        "| name | shape | l0-deps | when-to-use | acpx-leg-required | example |",
        "|---|---|---|---|---|---|",
    ]
    for name in vlr.CANONICAL_L1:
        acpx = "true" if name in vlr.L1_ACPX_REQUIRED else "false"
        lines.append(f"| {name} | shape of {name} | sequence | use {name} | {acpx} | |")
    lines.append("")
    return "\n".join(lines)


def test_valid_synthetic_doc_passes():
    assert vlr.check(build_valid_doc()) == []


def test_l0_missing_entry_flagged():
    doc = build_valid_doc()
    # Drop the `park` row from the L0 table.
    doc = "\n".join(l for l in doc.splitlines() if not l.startswith("| park |"))
    errors = vlr.check(doc)
    assert any("park" in e and "L0 missing keywords" in e for e in errors)


def test_l0_wrong_category_flagged():
    doc = build_valid_doc().replace(
        "| cap | bounds | definition of cap |",
        "| cap | control-flow | definition of cap |",
    )
    errors = vlr.check(doc)
    assert any("L0 'cap' category" in e for e in errors)


def test_l0_empty_definition_flagged():
    doc = build_valid_doc().replace(
        "| sequence | control-flow | definition of sequence |",
        "| sequence | control-flow |  |",
    )
    errors = vlr.check(doc)
    assert any("L0 'sequence' has empty definition" in e for e in errors)


def test_l1_missing_required_field_flagged():
    doc = build_valid_doc().replace(
        "| pipeline | shape of pipeline | sequence | use pipeline | false | |",
        "| pipeline | shape of pipeline | sequence |  | false | |",  # blank when-to-use
    )
    errors = vlr.check(doc)
    assert any("L1 'pipeline' missing required field 'when-to-use'" in e for e in errors)


def test_l1_unknown_l0_dep_flagged():
    doc = build_valid_doc().replace(
        "| gate | shape of gate | sequence | use gate | false | |",
        "| gate | shape of gate | sequence, bogus-keyword | use gate | false | |",
    )
    errors = vlr.check(doc)
    assert any("L1 'gate' l0-dep 'bogus-keyword'" in e for e in errors)


def test_l1_acpx_inconsistency_flagged():
    # router-loop is a §6.0 partial → must be true; flipping to false is a violation.
    doc = build_valid_doc().replace(
        "| router-loop | shape of router-loop | sequence | use router-loop | true | |",
        "| router-loop | shape of router-loop | sequence | use router-loop | false | |",
    )
    errors = vlr.check(doc)
    assert any("L1 'router-loop' acpx-leg-required" in e for e in errors)


def test_l1_missing_pattern_flagged():
    doc = "\n".join(
        l for l in build_valid_doc().splitlines() if not l.startswith("| quorum-decide |")
    )
    errors = vlr.check(doc)
    assert any("quorum-decide" in e and "L1 missing patterns" in e for e in errors)


def test_missing_guidelines_preface_flagged():
    doc = build_valid_doc().replace("## Authoring Guidelines", "## Something Else")
    errors = vlr.check(doc)
    assert any("Authoring Guidelines" in e for e in errors)


def test_l0_count_is_33():
    """CANONICAL_L0 must contain exactly 33 keywords (26 base + 7 driving-to-done)."""
    all_names = {n for names in vlr.CANONICAL_L0.values() for n in names}
    assert len(all_names) == 33, f"Expected 33 L0 keywords, got {len(all_names)}: {sorted(all_names)}"


# --- driving-to-done vocab durability (L1 drive-to-done + 7 new L0 keywords) ---

_DRIVE_L0_KEYWORDS = (
    "oracle", "done-criterion", "clean-streak", "fresh-seed-reset",
    "circuit-breaker", "evidence-before-assertion", "closeout",
)


def test_drive_to_done_in_canonical_l1():
    """The drive-to-done L1 pattern must be a canonical L1 vocabulary member."""
    assert "drive-to-done" in vlr.CANONICAL_L1, (
        "drive-to-done must be registered in CANONICAL_L1"
    )


def test_drive_to_done_is_native_not_acpx():
    """drive-to-done is acpx-leg-required: false — it must NOT be in L1_ACPX_REQUIRED."""
    assert "drive-to-done" not in vlr.L1_ACPX_REQUIRED, (
        "drive-to-done is a native pattern (acpx-leg-required: false)"
    )


def test_driving_to_done_l0_keywords_in_canonical():
    """Each of the 7 driving-to-done L0 keywords must be a canonical L0 member."""
    all_names = {n for names in vlr.CANONICAL_L0.values() for n in names}
    for kw in _DRIVE_L0_KEYWORDS:
        assert kw in all_names, f"{kw!r} must be a CANONICAL_L0 keyword"


def test_drive_to_done_in_real_doc_l1():
    """The shipped doc's L1 table must list drive-to-done as a native (false) pattern."""
    doc_path = (
        Path(__file__).resolve().parents[3] / "docs" / "language-reference.md"
    )
    (header, rows), err = vlr.extract_table(doc_path.read_text(encoding="utf-8"), "L1")
    assert err is None, err
    by_name = {r["name"]: r for r in rows}
    assert "drive-to-done" in by_name, "shipped L1 table must list drive-to-done"
    assert by_name["drive-to-done"]["acpx-leg-required"].strip().lower() == "false", (
        "drive-to-done must declare acpx-leg-required: false in the shipped doc"
    )


def test_driving_to_done_l0_keywords_in_real_doc():
    """The shipped doc's L0 table must list all 7 driving-to-done keywords."""
    doc_path = (
        Path(__file__).resolve().parents[3] / "docs" / "language-reference.md"
    )
    (header, rows), err = vlr.extract_table(doc_path.read_text(encoding="utf-8"), "L0")
    assert err is None, err
    names = {r["name"] for r in rows}
    for kw in _DRIVE_L0_KEYWORDS:
        assert kw in names, f"shipped L0 table must list {kw!r}"


def test_nudge_absent_from_canonical_l0():
    """nudge must not be a member of any CANONICAL_L0 category."""
    all_names = {n for names in vlr.CANONICAL_L0.values() for n in names}
    assert "nudge" not in all_names, "nudge must not appear in CANONICAL_L0"


def test_nudge_absent_from_synthetic_doc():
    """A freshly-built synthetic doc must not reference nudge in any L0 row."""
    doc = build_valid_doc()
    l0_section_start = doc.index("## L0")
    l1_section_start = doc.index("## L1")
    l0_section = doc[l0_section_start:l1_section_start]
    assert "nudge" not in l0_section, "nudge must not appear in the L0 table"


def test_nudge_absent_from_real_doc_l0():
    """The shipped doc must not list nudge as an L0 keyword."""
    doc_path = (
        Path(__file__).resolve().parents[3] / "docs" / "language-reference.md"
    )
    assert doc_path.exists(), f"language-reference doc missing: {doc_path}"
    text = doc_path.read_text(encoding="utf-8")
    l0_section_start = text.index("## L0")
    l1_section_start = text.index("## L1")
    l0_section = text[l0_section_start:l1_section_start]
    assert "nudge" not in l0_section, "nudge must not appear in the L0 section of the shipped doc"


def test_real_doc_passes_gate():
    """The shipped language-reference doc must pass every Phase-1 gate check."""
    doc_path = (
        Path(__file__).resolve().parents[3] / "docs" / "language-reference.md"
    )
    assert doc_path.exists(), f"language-reference doc missing: {doc_path}"
    errors = vlr.check(doc_path.read_text(encoding="utf-8"))
    assert errors == [], "Phase-1 gate violations:\n" + "\n".join(errors)
