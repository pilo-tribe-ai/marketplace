import importlib.util
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_V = PLUGIN_ROOT / "scripts" / "validate_l2_vocab.py"
_spec = importlib.util.spec_from_file_location("validate_l2_vocab", _V)
vl2 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(vl2)
L2_NAMES = vl2.L2_NAMES  # single source of truth — no duplicate literal [inferred]

_doc_path = PLUGIN_ROOT / "docs" / "language-reference.md"
if not _doc_path.exists():  # [inferred]
    import pytest; pytest.skip("language-reference.md absent — Phase 1 gate must be closed first", allow_module_level=True)  # [inferred]
DOC = _doc_path.read_text()  # [inferred]

# Load validate_language_reference for Phase-1 gate check below. [inferred]
_vlr_path = PLUGIN_ROOT / "scripts" / "validate_language_reference.py"  # [inferred]
_vlr_spec = importlib.util.spec_from_file_location("validate_language_reference", _vlr_path)  # [inferred]
_vlr = importlib.util.module_from_spec(_vlr_spec); _vlr_spec.loader.exec_module(_vlr)  # [inferred]

def test_phase1_gate_clean():
    """Guard: language-reference.md must be well-formed (L0+L1 tables parseable)
    before any vocab-resolution tests run.  A malformed doc would otherwise cause
    validate_l2_vocab to raise ValueError at import time — a collection ERROR
    rather than a test failure.  Running this first produces a clear FAILED line."""  # [inferred]
    errs = _vlr.check(DOC)  # [inferred]
    assert errs == [], (  # [inferred]
        f"language-reference.md failed Phase-1 validation — fix it before running "  # [inferred]
        f"vocab tests:\n" + "\n".join(errs)  # [inferred]
    )  # [inferred]

def test_real_skills_pass():
    # check_skill(skill_text) -> list[str] of violations; [] = pass [inferred]
    for name in L2_NAMES:  # uses vl2.L2_NAMES imported above — no duplicate literal [inferred]
        text = (PLUGIN_ROOT / "skills" / name / "SKILL.md").read_text()
        assert vl2.check_skill(text) == [], f"{name} should pass: {vl2.check_skill(text)}"  # [inferred]

def test_synthetic_unknown_token_fails():
    bad = (
        "---\nname: x\nuser-invocable: false\n---\n# x\n\n## Vocabulary\n\n"
        "```relay-vocab\nl1-shape: pipeline\nl0-deps: sequence, NOT_A_REAL_TOKEN\n"
        "acpx-leg-required: false\n```\n"
    )
    errs = vl2.check_skill(bad)  # [inferred]
    assert any("NOT_A_REAL_TOKEN" in e for e in errs), errs

def test_synthetic_unknown_l1_shape_fails():
    bad = (
        "---\nname: x\nuser-invocable: false\n---\n# x\n\n## Vocabulary\n\n"
        "```relay-vocab\nl1-shape: NOT_A_PATTERN\nl0-deps: sequence\n"
        "acpx-leg-required: false\n```\n"
    )
    assert any("NOT_A_PATTERN" in e for e in vl2.check_skill(bad))  # [inferred]

def test_synthetic_missing_required_key_fails():  # [inferred]
    bad = (  # [inferred]
        "---\nname: x\nuser-invocable: false\n---\n# x\n\n## Vocabulary\n\n"  # [inferred]
        "```relay-vocab\nl1-shape: pipeline\nl0-deps: sequence\n```\n"  # [inferred]
    )  # [inferred]
    errs = vl2.check_skill(bad)  # [inferred]
    assert errs, "missing acpx-leg-required should produce at least one violation"  # [inferred]
    assert any("acpx-leg-required" in e for e in errs), errs  # [inferred]

def test_synthetic_no_vocab_block_fails():  # [inferred]
    bad = "---\nname: x\nuser-invocable: false\n---\n# x\n\nNo vocab block here.\n"  # [inferred]
    errs = vl2.check_skill(bad)  # [inferred]
    assert errs, "skill with no relay-vocab block must produce violations"  # [inferred]
    assert any("no relay-vocab block" in e.lower() or "zero" in e.lower() for e in errs), errs  # [inferred]

def test_synthetic_multiple_vocab_blocks_fails():  # [inferred]
    bad = (  # [inferred]
        "---\nname: x\nuser-invocable: false\n---\n# x\n\n"  # [inferred]
        "```relay-vocab\nl1-shape: pipeline\nl0-deps: sequence\nacpx-leg-required: false\n```\n\n"  # [inferred]
        "```relay-vocab\nl1-shape: pipeline\nl0-deps: sequence\nacpx-leg-required: false\n```\n"  # [inferred]
    )  # [inferred]
    errs = vl2.check_skill(bad)  # [inferred]
    assert errs, "skill with multiple relay-vocab blocks must produce violations"  # [inferred]
    assert any("multiple" in e.lower() for e in errs), errs  # [inferred]
