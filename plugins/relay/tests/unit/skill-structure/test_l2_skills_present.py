import pytest
import importlib.util
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]

# Load parse_frontmatter via importlib.util (same path-explicit pattern used by
# test_language_reference.py for its validator) so collection succeeds regardless of
# invocation CWD — do NOT use "from conftest import parse_frontmatter" which relies
# on pytest injecting tests/ into sys.path and breaks when pytest is run from a
# subdirectory directly. [inferred]
_conftest_path = PLUGIN_ROOT / "tests" / "conftest.py"  # [inferred]
_cf_spec = importlib.util.spec_from_file_location("conftest", _conftest_path)  # [inferred]
_cf = importlib.util.module_from_spec(_cf_spec); _cf_spec.loader.exec_module(_cf)  # [inferred]
parse_frontmatter = _cf.parse_frontmatter  # [inferred]

L2_NAMES = ["panel", "delegate-leaf", "improve-loop",
            "brainstorm-decide", "parallel-gather", "staged-run", "delegate-and-watch"]


@pytest.mark.parametrize("name", L2_NAMES)
def test_l2_skill_frontmatter(name):
    path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
    assert path.is_file(), f"missing L2 skill {path}"
    fm, body = parse_frontmatter(path)  # [inferred] unpack body to check vocab block
    assert fm.get("name") == name
    assert fm.get("user-invocable") is False
    assert (fm.get("description") or "").strip()
    assert "```relay-vocab" in body, f"{name} SKILL.md is missing the relay-vocab block"  # [inferred]


def test_brainstorm_decide_acpx_interface_documented():
    """brainstorm-decide is the only skill with acpx-leg-required: true;
    its body must document the §6.4.1 continuation token interface."""
    path = PLUGIN_ROOT / "skills" / "brainstorm-decide" / "SKILL.md"
    _, body = parse_frontmatter(path)
    assert "continuation token" in body or "§6.4.1" in body, (
        "brainstorm-decide SKILL.md must reference the §6.4.1 acpx-leaf "
        "continuation token interface (phrase 'continuation token' or '§6.4.1')"
    )


# ---------------------------------------------------------------------------
# Resolution/policy skills — routing-work-to-agents, selecting-the-right-model
# These are NOT L2 pattern skills: no relay-vocab block, not in L2_NAMES.
# ---------------------------------------------------------------------------

RESOLUTION_POLICY_SKILLS = ["routing-work-to-agents", "selecting-the-right-model"]


@pytest.mark.parametrize("name", RESOLUTION_POLICY_SKILLS)
def test_resolution_policy_skill_exists(name):
    path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
    assert path.is_file(), f"missing resolution/policy skill {path}"


@pytest.mark.parametrize("name", RESOLUTION_POLICY_SKILLS)
def test_resolution_policy_skill_frontmatter(name):
    path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
    fm, _ = parse_frontmatter(path)
    assert fm.get("name") == name, f"{name} frontmatter 'name' must equal '{name}'"
    assert fm.get("user-invocable") is False, f"{name} must have user-invocable: false"
    assert (fm.get("description") or "").strip(), f"{name} must have a non-empty description"


@pytest.mark.parametrize("name", RESOLUTION_POLICY_SKILLS)
def test_resolution_policy_skill_no_relay_vocab(name):
    """Resolution/policy skills are not L2 pattern skills and must not carry a relay-vocab block."""
    path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
    _, body = parse_frontmatter(path)
    assert "```relay-vocab" not in body, (
        f"{name} SKILL.md must NOT contain a relay-vocab block "
        "(resolution/policy skills are not L2 pattern skills)"
    )


@pytest.mark.parametrize("name", RESOLUTION_POLICY_SKILLS)
def test_resolution_policy_skill_not_in_l2_names(name):
    assert name not in L2_NAMES, (
        f"{name} must not appear in L2_NAMES — it is a resolution/policy skill, not an L2 pattern"
    )


def test_routing_work_to_agents_documents_providers():
    """routing-work-to-agents must document both claude and codex routing policies."""
    path = PLUGIN_ROOT / "skills" / "routing-work-to-agents" / "SKILL.md"
    _, body = parse_frontmatter(path)
    assert "claude" in body.lower(), "routing-work-to-agents must document claude routing"
    assert "codex" in body.lower(), "routing-work-to-agents must document codex routing"
    assert "typed-output" in body, "routing-work-to-agents must document its typed-output shape"


def test_selecting_the_right_model_documents_three_layers():
    """selecting-the-right-model must document all three required layers."""
    path = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"
    _, body = parse_frontmatter(path)
    assert "POLICY" in body, "selecting-the-right-model must document the POLICY layer"
    assert "INVENTORY" in body, "selecting-the-right-model must document the INVENTORY layer"
    assert "RESOLUTION" in body, "selecting-the-right-model must document the RESOLUTION layer"


def test_selecting_the_right_model_documents_anthropic_classes():
    """The in-session ladder has four rungs; `inherit` is the never-downshift rung."""
    path = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"
    _, body = parse_frontmatter(path)
    for cls in ("opus", "sonnet", "haiku", "inherit"):
        assert cls in body, (
            f"selecting-the-right-model must document Anthropic class '{cls}'"
        )


def test_selecting_the_right_model_documents_openai_classes():
    """The codex ladder is the two GPT-5.6 tiers actually pinned in presets.yaml."""
    path = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"
    _, body = parse_frontmatter(path)
    for cls in ("gpt-5.6-sol", "gpt-5.6-terra"):
        assert cls in body, (
            f"selecting-the-right-model must document codex tier '{cls}'"
        )
    for retired in ("gpt-5.6-luna", "opencode-go/minimax-m3"):
        assert retired not in body, (
            f"selecting-the-right-model still documents retired tier '{retired}'. "
            "The ladder here is a reader's map of what presets.yaml pins; a tier "
            "no role pins sends a reader to a slot that no longer exists."
        )


def test_selecting_the_right_model_names_the_real_resolvers():
    """The skill must point at the two scripts that actually resolve a tier, so it
    cannot drift back into describing a resolution path that does not exist."""
    path = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"
    _, body = parse_frontmatter(path)
    assert "resolve-tier.sh" in body, "must name the in-session resolver"
    assert "acpx-dispatch.sh" in body, "must name the acpx resolver"
    assert "in_session_tiers" in body, "must document the gate"


def test_selecting_the_right_model_documents_inventory_stub():
    """selecting-the-right-model must document the inventory stub for deterministic tests."""
    path = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"
    _, body = parse_frontmatter(path)
    assert "stub" in body.lower(), (
        "selecting-the-right-model must document the inventory stub for deterministic tests"
    )
    assert "staleness" in body.lower(), (
        "selecting-the-right-model must document the staleness detector"
    )


def test_preamble_has_flip_selectable_autonomy_clause():
    """dispatching-acpx-agents/preamble.md must document both autonomy modes:
    fire-and-forget ('decide, never ask') and interactive (AUTONOMY=interactive).
    """
    preamble = (
        PLUGIN_ROOT
        / "skills"
        / "dispatching-acpx-agents"
        / "preamble.md"
    )
    assert preamble.is_file(), f"preamble not found at {preamble}"
    text = preamble.read_text()
    assert "decide, never ask" in text, (
        "preamble.md must document the fire-and-forget mode with phrase 'decide, never ask'"
    )
    assert "AUTONOMY=interactive" in text, (
        "preamble.md must document the interactive mode with phrase "
        "'AUTONOMY=interactive'"
    )
