"""Guard tests for delegate-and-watch/SKILL.md: five-bucket table, conditional trap,
turn-lifetime rule (spec 2026-07-25 §1)."""
import re
from pathlib import Path
import pytest

SKILL = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "delegate-and-watch" / "SKILL.md"


def _body():
    return SKILL.read_text()


def _norm(text: str) -> str:
    """Lowercase, drop Markdown emphasis/code marks, collapse whitespace across newlines.

    Required for the negative assertions below. The stale phrases were rendered with
    backticks (``park`` at a resumable pause) and wrapped across lines in the source
    file, so a naive `phrase in body` check passes VACUOUSLY against the unfixed file
    and proves nothing.
    """
    text = text.lower().replace("`", "").replace("*", "").replace("—", "-")
    return re.sub(r"\s+", " ", text)


class TestDelegateAndWatchFiveBuckets:
    def test_skill_file_exists(self):
        assert SKILL.is_file()

    def test_needs_decision_row_present(self):
        body = _body()
        assert "needs-decision" in body, "bucket table must include needs-decision row"

    def test_five_bucket_rows(self):
        body = _body()
        for bucket in ("done", "not-done", "blocked", "needs-decision", "errored"):
            assert f"`{bucket}`" in body or f"| `{bucket}`" in body or f"| {bucket} |" in body or bucket in body, \
                f"bucket table must include {bucket!r} row"

    def test_parked_variable_initialized(self):
        body = _body()
        assert "PARKED=0" in body, "scaffolding must initialize PARKED=0 before the main loop"

    def test_conditional_trap_gates_on_parked(self):
        body = _body()
        assert '"$PARKED" != "1"' in body or '"$PARKED" != \'1\'' in body, \
            "crash-cleanup trap must gate on PARKED != 1"

    def test_trap_does_not_close_on_needs_decision(self):
        body = _body()
        # The exact conditional form must be present (not the old unconditional form).
        # A bare "PARKED" occurrence anywhere is not sufficient — the guard block itself
        # must appear in the scaffolding so generated code will include it.
        assert 'if [[ "$PARKED" != "1" ]]; then' in body, \
            "trap body must be conditional on PARKED — exact form 'if [[ \"$PARKED\" != \"1\" ]]; then' required"

    def test_needs_decision_route_sets_parked_1(self):
        body = _body()
        assert "PARKED=1" in body, "needs-decision route must set PARKED=1 before exit"

    def test_needs_decision_surfaces_role_result(self):
        body = _body()
        assert "ROLE_RESULT=NEEDS_DECISION" in body, \
            "needs-decision route must surface ROLE_RESULT=NEEDS_DECISION"

    def test_needs_decision_surfaces_question_text(self):
        body = _body()
        assert "QUESTION_TEXT" in body, \
            "needs-decision route must surface QUESTION_TEXT"

    def test_needs_decision_detaches_not_closes(self):
        body = _body()
        assert "detach" in body, \
            "needs-decision route must call sessions detach (not close) before exiting"

    def test_relay_max_turns_sidecar_line(self):
        body = _body()
        assert "RELAY_MAX_TURNS" in body, \
            "sidecar write must append RELAY_MAX_TURNS so drivers receive the cap"

    def test_dangling_section_reference_fixed(self):
        body = _body()
        assert "§4.3" not in body, \
            "dangling §4.3 retry bound reference must be replaced with 'turn cap'"

    def test_turn_cap_description_present(self):
        body = _body()
        assert "turn cap" in body or "RELAY_MAX_TURNS" in body, \
            "not-done loop must reference the turn cap"

    def test_unparseable_envelope_guard_documented(self):
        body = _body()
        assert "unparseable" in body or "unparseable_envelope" in body, \
            "watcher SKILL.md must document the unparseable-envelope guard (spec §9 PR1 item 1: typed terminal error, never not-done)"  # [inferred]


# --- spec 2026-07-25 §1 — turn-lifetime rule -------------------------------------
#
# Root cause of four dead nodes across two runs: this skill told the watcher to end
# its turn while a dispatch was outstanding. An agent node has exactly one turn, so
# turn end is termination and no notification is ever delivered.


# The four phrases that PRESCRIBED the failure. Normalized form — see _norm().
STALE_PHRASES = (
    "no poll loop; no monitor action",
    "awaits the automatic completion notification",
    "the watcher issues zero tool calls during the wait",
    "park at a resumable pause",
)


class TestTurnLifetimeRule:
    def test_rule_section_present(self):
        assert "## TURN-LIFETIME RULE" in _body(), \
            "delegate-and-watch must carry the '## TURN-LIFETIME RULE (non-negotiable)' section"

    def test_turn_end_is_termination_stated(self):
        assert "Turn end IS termination" in _body(), \
            "the rule must state 'Turn end IS termination' verbatim — it is the whole doctrine"

    def test_park_explicitly_excluded(self):
        norm = _norm(_body())
        assert "park is not available to an agent node" in norm, \
            "the rule must exclude park explicitly: a leaf has no resumable pause"

    def test_monitor_explicitly_excluded(self):
        norm = _norm(_body())
        assert "monitor is not a wait mechanism" in norm, \
            "the rule must exclude Monitor explicitly: its event lands in a turn that never comes"

    @pytest.mark.parametrize("token", [
        'timeout "${WATCH_BUDGET:-580}"',
        "until grep -qE",
        "sleep 10",
        'pgrep -f "[a]cpx-dispatch.sh"',
    ])
    def test_blocking_poll_scaffold_present(self, token):
        assert token in _body(), \
            f"the mandated blocking in-turn poll must be spelled out; missing {token!r}"

    def test_liveness_probe_cannot_match_itself(self):
        """`pgrep -f` matches whole command lines, including the poll's own `bash -c`.

        Spelled plainly, `pgrep -f acpx-dispatch.sh` always matches itself, so the
        `! pgrep` escape never fires and a dead worker burns the entire WATCH_BUDGET
        instead of being detected. The bracket makes the pattern not match its own text.
        """
        body = _body()
        assert "pgrep -f acpx-dispatch.sh" not in body, \
            "the liveness probe must not use a pattern that matches its own command line"

    def test_budget_exhaustion_is_a_typed_failure(self):
        body = _body()
        assert "watcher_budget_exhausted" in body, \
            "budget exhaustion must surface ERRORED_REASON=watcher_budget_exhausted, never a park"
        assert "ROLE_RESULT=ERRORED" in body, \
            "budget exhaustion must surface ROLE_RESULT=ERRORED"

    def test_backgrounding_is_still_permitted(self):
        # [CORRECTION] from the diagnosis: all four SUCCESSFUL nodes also used
        # run_in_background. Backgrounding is not the fault — ending the turn is.
        # A test that banned run_in_background would enshrine the wrong rule and
        # break the only pattern that works.
        assert "run_in_background" in _body(), \
            "run_in_background must survive — the rule targets turn-end, not backgrounding"

    def test_execution_path_comment_still_names_blocking(self):
        # Belt-and-braces against a regression of
        # test_plugin.py::TestDelegateAndWatchSkill::test_execution_path_comment_at_top.
        # The spec said to delete this comment; deleting it breaks that test, so it was
        # rewritten in place instead.
        line = next(ln for ln in _body().splitlines() if "EXECUTION PATH:" in ln)
        assert "blocking" in line, \
            "the EXECUTION PATH comment must still name the blocking in-turn poll"
        assert "notification" not in line.lower(), \
            "the EXECUTION PATH comment must no longer promise an exit-event notification"


class TestStalePhrasesRemoved:
    @pytest.mark.parametrize("phrase", STALE_PHRASES)
    def test_stale_phrase_absent(self, phrase):
        assert phrase not in _norm(_body()), \
            f"{phrase!r} prescribed the silent-failure bug and must be gone"

    @pytest.mark.parametrize("phrase", [
        "completion notification",
        "notification path",
        "o(polls)",
        "park/router-loop",
    ])
    def test_notification_doctrine_absent(self, phrase):
        # The frontmatter description and the intro summary carried the same defect as
        # the body: they promised a native completion-notification path.
        assert phrase not in _norm(_body()), \
            f"{phrase!r} restates the removed notification doctrine"

    def test_router_loop_survives(self):
        # `router-loop` is a real L1 pattern and the declared l1-shape family — only the
        # `park/` prefix was wrong.
        assert "router-loop" in _body(), "the router-loop route must survive the park/ removal"

    def test_park_dropped_from_l0_deps(self):
        line = next(ln for ln in _body().splitlines() if ln.startswith("l0-deps:"))
        deps = [d.strip() for d in line.split(":", 1)[1].split(",")]
        assert "park" not in deps, \
            "park must not be an l0-dep of multi-turn-dispatch — a leaf cannot park"


class TestBgSessionsLeg:
    """Guard tests for the '## The bg-sessions leg' section (spec §Deliverable 2,
    Completion) — the two poll-target/liveness-escape substitutions and the
    TURN-discipline rule, layered on top of the unchanged acpx leg."""

    def test_bg_leg_section_present(self):
        assert "## The bg-sessions leg" in _body()

    def test_bg_leg_sources_the_bg_sidecar(self):
        assert "~/.claude/relay/bg/" in _body()

    def test_bg_leg_polls_the_handoff_file(self):
        assert "RELAY_BG_HANDOFF" in _body()

    def test_bg_liveness_is_the_escape(self):
        body = _body()
        assert "bg-liveness.sh" in body
        assert "stopped" in body

    def test_bg_escape_fires_on_rc_1_only(self):
        norm = _norm(_body())
        assert "fires on rc 1 only" in norm
        assert "does not fire the escape" in norm

    def test_acpx_bracketed_pgrep_unchanged(self):
        # Regression check: the new bg-sessions section must not have displaced the
        # existing acpx liveness-probe guard.
        assert 'pgrep -f "[a]cpx-dispatch.sh"' in _body()
        assert "pgrep -f acpx-dispatch.sh" not in _body()

    def test_turn_lifetime_rule_unchanged(self):
        body = _body()
        assert "## TURN-LIFETIME RULE" in body
        assert "Turn end IS termination" in body
        norm = _norm(body)
        assert "park is not available to an agent node" in norm
        assert "monitor is not a wait mechanism" in norm
