"""Guard tests for the driving-to-done skill + the /relay:drive command.

Mirrors the substring-presence style of test_delegate_and_watch.py: assert the
load-bearing protocol content on the ACTUAL shipped files, robust to minor
wording changes (case-insensitive / structural substrings) but still verifying
the four invariants, the consecutive-clean-runs bar, the re-prove-from-step-0
rule, the circuit-breaker → blocked-items continue rule, the Vocabulary footer,
the templates.md envelope, and the drive command's thin-L3 frontmatter idioms.
"""
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "driving-to-done"
SKILL = _SKILL_DIR / "SKILL.md"
TEMPLATES = _SKILL_DIR / "templates.md"
DRIVE_CMD = Path(__file__).resolve().parent.parent.parent.parent / "commands" / "drive.md"


def _skill():
    return SKILL.read_text(encoding="utf-8")


def _templates():
    return TEMPLATES.read_text(encoding="utf-8")


def _drive():
    return DRIVE_CMD.read_text(encoding="utf-8")


class TestSkillFilesExist:
    def test_skill_file_exists(self):
        assert SKILL.is_file(), "skills/driving-to-done/SKILL.md missing"

    def test_templates_file_exists(self):
        assert TEMPLATES.is_file(), "skills/driving-to-done/templates.md missing"

    def test_drive_command_exists(self):
        assert DRIVE_CMD.is_file(), "commands/drive.md missing"


class TestSkillFrontmatter:
    def test_name_is_driving_to_done(self):
        body = _skill()
        assert "name: driving-to-done" in body, "frontmatter must declare name: driving-to-done"

    def test_user_invocable_false(self):
        body = _skill()
        assert "user-invocable: false" in body, (
            "driving-to-done is an internal skill — must set user-invocable: false"
        )


class TestFourInvariants:
    """The four invariants (two verbatim, two re-mapped to relay's hybrid substrate)."""

    def test_invariant_heading_present(self):
        assert "## The four invariants" in _skill()

    def test_binary_done_criterion_oracle(self):
        body = _skill().lower()
        # Invariant 1: a single, checkable done criterion (the oracle).
        assert "binary done criterion" in body and "oracle" in body, (
            "invariant 1 must define a binary done criterion / oracle"
        )

    def test_lean_orchestrator_main_owns_one_process(self):
        body = _skill()
        # Invariant 2 (re-mapped): MAIN owns at most ONE long-lived process.
        assert "MAIN owns" in body and "ONE long-lived process" in body, (
            "invariant 2 must state MAIN owns at most ONE long-lived process"
        )
        assert "lean orchestrator" in body.lower(), "invariant 2 is the lean-orchestrator rule"

    def test_real_working_only_evidence_before_assertion(self):
        body = _skill().lower()
        # Invariant 3: real-working-only, evidence before assertion.
        assert "evidence before assertion" in body, (
            "invariant 3 must require evidence before assertion"
        )
        assert "real-working-only" in body or "real working only" in body, (
            "invariant 3 must require real-working-only steps"
        )

    def test_durable_resumable_state(self):
        body = _skill().lower()
        # Invariant 4 (re-mapped to two layers): durable, resumable state.
        assert "durable" in body and "resumable" in body, (
            "invariant 4 must require durable, resumable state"
        )


class TestLoopDiscipline:
    def test_consecutive_clean_runs_bar_n_equals_2(self):
        body = _skill()
        # The clean-streak bar: prove done = N consecutive clean runs, N=2 default.
        assert "consecutive clean runs" in body.lower(), (
            "must prove done via consecutive clean runs"
        )
        assert "N=2" in body, "the consecutive-clean-runs bar must default to N=2"
        assert "clean_streak" in body, "must track clean_streak"

    def test_re_prove_from_step_0_after_fix(self):
        body = _skill().lower()
        # Any fix re-proves from step 0 (a fix can break an earlier step).
        assert "re-prove from step 0" in body, (
            "after a fix the loop must re-prove from step 0"
        )
        assert "any fix resets the streak to 0" in body, (
            "any fix must reset the clean streak to 0"
        )

    def test_circuit_breaker_writes_blocked_items_and_continues(self):
        body = _skill()
        lower = body.lower()
        # Circuit breaker: cap fix cycles, write to blocked-items.md, then continue.
        assert "circuit breaker" in lower, "must document the circuit breaker"
        assert "blocked-items.md" in body, "circuit breaker must write to blocked-items.md"
        assert "continue" in lower and "blocked step is not a stopped loop" in lower, (
            "a blocked step must continue the loop, not stop it"
        )

    def test_fresh_seed_reset_verify_pristine(self):
        body = _skill().lower()
        assert "fresh-seed reset" in body or "fresh seed reset" in body, (
            "must document the fresh-seed reset"
        )
        assert "pristine" in body, "the reset must be verified pristine, not assumed"


class TestVocabularyFooter:
    def test_vocabulary_section_present(self):
        assert "## Vocabulary" in _skill(), "SKILL.md must end with a ## Vocabulary footer"

    def test_l1_shape_drive_to_done(self):
        assert "l1-shape: drive-to-done" in _skill(), (
            "Vocabulary footer must declare l1-shape: drive-to-done"
        )

    def test_acpx_leg_required_false(self):
        assert "acpx-leg-required: false" in _skill(), (
            "Vocabulary footer must declare acpx-leg-required: false"
        )

    def test_relay_vocab_block_present(self):
        assert "```relay-vocab" in _skill(), (
            "Vocabulary footer must carry a fenced relay-vocab block (L2-vocab gate)"
        )


class TestTemplatesEnvelope:
    """The subagent return envelope (Appendix B) + the four state-file headings."""

    def test_envelope_tokens_present(self):
        body = _templates()
        for token in ("PHASE_A", "SEED", "STEP", "RESULT", "EVIDENCE", "NOTES"):
            assert token in body, f"return envelope must carry the {token} key"

    def test_envelope_result_terminal_values(self):
        body = _templates()
        assert "ALL_CLEAN" in body and "FAILED@STEP" in body, (
            "RESULT line must carry the ALL_CLEAN | FAILED@STEP<N> terminal values"
        )

    def test_four_state_file_headings(self):
        body = _templates()
        # The four durable state files: oracle is the caller's; the templates ship
        # loop-state, decision-log, blocked-items, plus the return envelope.
        for heading in ("loop-state.md", "decision-log.md", "blocked-items.md"):
            assert heading in body, f"templates must include the {heading} skeleton"
        assert "return envelope" in body.lower(), (
            "templates must include the subagent return envelope skeleton"
        )

    def test_loop_state_tracks_clean_streak(self):
        body = _templates()
        assert "clean_streak" in body, "loop-state.md template must track clean_streak"


class TestDriveCommandFrontmatter:
    def test_disable_model_invocation_true(self):
        assert "disable-model-invocation: true" in _drive(), (
            "drive.md must set disable-model-invocation: true"
        )

    def test_workflow_in_allowed_tools(self):
        body = _drive()
        # Parse the allowed-tools frontmatter line specifically.
        allowed_line = next(
            (ln for ln in body.splitlines() if ln.strip().startswith("allowed-tools:")),
            "",
        )
        assert "Workflow" in allowed_line, (
            "drive.md allowed-tools must declare Workflow (thin-L3 dispatch substrate)"
        )

    def test_argument_hint_has_resume(self):
        body = _drive()
        hint_line = next(
            (ln for ln in body.splitlines() if ln.strip().startswith("argument-hint:")),
            "",
        )
        assert "--resume" in hint_line, "drive.md argument-hint must expose --resume"
        assert "--engine" in hint_line, "drive.md argument-hint must expose --engine"
        assert "--agent" in hint_line, "drive.md argument-hint must expose --agent"
        assert "oracle" in hint_line.lower(), "drive.md argument-hint must take an <oracle-file>"

    def test_calls_workflow_tool_now(self):
        body = _drive()
        assert "Call the `Workflow` tool now" in body, (
            "drive.md must carry the verbatim 'Call the `Workflow` tool now' directive"
        )

    def test_one_workflow_self_check(self):
        body = _drive().lower()
        # Same one-Workflow completion self-check the other L3 commands carry.
        assert "exactly one" in body and "workflow" in body, (
            "drive.md must require exactly one Workflow run"
        )

    def test_loads_driving_to_done_skill(self):
        body = _drive()
        assert "relay:driving-to-done" in body, (
            "drive.md must load the relay:driving-to-done protocol skill"
        )
