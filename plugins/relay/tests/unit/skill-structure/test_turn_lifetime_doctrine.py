"""Cross-skill consistency guard — spec 2026-07-25 §1, the highest-value test.

The silent-failure bug was not a missing insight. Relay *already stated the correct
rule* and contradicted itself:

    skills/driving-to-done/SKILL.md — "A process launched *inside* a leaf dies when
    that leaf ends — so it cannot live there."   (same text in commands/drive.md)

while `delegate-and-watch` prescribed exactly the opposite: background a dispatch,
end the turn, wait for a notification. Four nodes across two runs died silently and
the run reported `completed`.

This file is what stops that recurring: no SKILL.md under plugins/relay/skills/ may
prescribe background-and-park.

SCOPE — read before widening it:

  * Only `skills/*/SKILL.md` is scanned. `docs/language-reference.md` legitimately
    DEFINES `park` ("Suspend at a resumable pause…") as an L0 Workflow-graph
    primitive; scanning docs/ would fail on the correct file.
  * The guard targets park-and-wait, never backgrounding. [CORRECTION] from the
    diagnosis: all four *successful* nodes also used `run_in_background`. A rule
    banning it would break the only pattern that works — see
    test_delegate_and_watch.py::TestTurnLifetimeRule::test_backgrounding_is_still_permitted.
  * KNOWN FLAGGED, NOT FIXED — deliberately not failed on here, and named so the next
    reader is not misled: `roles/server-runner.md:32-33` and
    `skills/running-web-apps/SKILL.md:134` both tell a leaf to launch a server as a
    background task inside the leaf, which driving-to-done says dies with it. The
    spec flagged both as "adjacent, not implicated in these failures; worth a
    separate look" and explicitly did not fix them. `roles/` is out of scope here,
    and the phrase "background task" is not itself an offense. If you fix them,
    tighten this guard at the same time.
"""
import re

import pytest

from conftest import PLUGIN_ROOT

SKILLS_DIR = PLUGIN_ROOT / "skills"
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))
SKILL_IDS = [p.parent.name for p in SKILL_FILES]


def _norm(text: str) -> str:
    """Lowercase, drop emphasis/code marks, collapse whitespace across newlines.

    Mandatory: the offending phrases were backticked and line-wrapped in the source,
    so an un-normalized substring check passes vacuously and proves nothing.
    """
    text = text.lower().replace("`", "").replace("*", "").replace("—", "-")
    return re.sub(r"\s+", " ", text)


# A paragraph that FORBIDS a phrasing necessarily quotes it. Scan block-by-block and
# skip blocks that carry a prohibition marker, so the turn-lifetime rule's own list of
# banned final-message phrasings is not read as prescribing them.
_PROHIBITION_MARKERS = (
    "never end a turn",
    "the node has already failed",
    "is not available",
    "not a wait mechanism",
    "never park",
    "must be gone",
)


def _prescriptive_blocks(text: str):
    """Normalized blank-line-separated blocks, minus the ones that state a prohibition."""
    for block in re.split(r"\n\s*\n", text):
        norm = _norm(block)
        if any(marker in norm for marker in _PROHIBITION_MARKERS):
            continue
        yield norm


# Prose that instructs an agent node to stop working and wait to be woken up.
# Each entry is a normalized substring.
BACKGROUND_AND_PARK_PHRASES = (
    # the four that literally prescribed the failure
    "no poll loop; no monitor action",
    "awaits the automatic completion notification",
    "the watcher issues zero tool calls during the wait",
    "park at a resumable pause",
    # the doctrine they belonged to
    "completion-notification path",
    "blocking-notification path",
    "the harness will notify me",
    "await the completion notification",
    "the runtime delivers exactly one system event",
)

# A `park`-family word used as an instruction. Matched case-sensitively so the Bash
# variable PARKED in delegate-and-watch's crash-cleanup trap is not swept up.
_PARK_WORD = re.compile(r"\bpark(s|ed|ing)?\b")

# Contexts in which a park-family word is a PROHIBITION or a description of detach
# semantics rather than an instruction to park. Anything else is a finding.
_PARK_EXEMPT = (
    "is not available",            # "`park` is not available to an agent node."
    "never park",                  # "On budget exhaustion … never park."
    "never end a turn",            # the banned-final-message bullet quoting "parking until"
    "not a wait mechanism",
    "deliberately parked",         # needs-decision session left open-but-detached
    "intentionally parked",
)


@pytest.mark.parametrize("path", SKILL_FILES, ids=SKILL_IDS)
@pytest.mark.parametrize("phrase", BACKGROUND_AND_PARK_PHRASES)
def test_no_skill_prescribes_background_and_park(path, phrase):
    offending = [b for b in _prescriptive_blocks(path.read_text()) if phrase in b]
    assert not offending, (
        f"{path.parent.name}/SKILL.md prescribes background-and-park ({phrase!r}). "
        "An agent node has exactly one turn: turn end is termination and no "
        "notification is delivered to a turn that has ended.\n"
        f"offending block: {offending[0][:300]}"
    )


@pytest.mark.parametrize("path", SKILL_FILES, ids=SKILL_IDS)
def test_no_skill_instructs_a_leaf_to_park(path):
    offenders = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if not _PARK_WORD.search(line):
            continue
        low = line.lower()
        if any(ex in low for ex in _PARK_EXEMPT):
            continue
        offenders.append(f"{lineno}: {line.strip()}")
    assert not offenders, (
        f"{path.parent.name}/SKILL.md uses a park-family word prescriptively:\n  "
        + "\n  ".join(offenders)
        + "\n`park` is Workflow-graph control flow only; a leaf has no resumable pause."
    )


class TestScanIsNotVacuous:
    """A doctrine scan that silently matched nothing would be worse than no test."""

    def test_glob_found_the_skills(self):
        assert len(SKILL_FILES) >= 15, \
            f"expected the full skill set, found {len(SKILL_FILES)}: {SKILL_IDS}"

    def test_delegate_and_watch_is_in_scope(self):
        assert "delegate-and-watch" in SKILL_IDS, \
            "the skill that carried the bug must be inside the scanned set"

    def test_correct_rule_still_stated(self):
        # The rule relay already had and contradicted. If this text ever disappears,
        # the guard above is defending a doctrine the plugin no longer states.
        body = _norm((SKILLS_DIR / "driving-to-done" / "SKILL.md").read_text())
        assert "dies when that leaf ends" in body, \
            "driving-to-done must keep stating that a process launched inside a leaf dies with it"

    def test_prohibition_filter_does_not_neuter_the_scan(self):
        # The block filter exists so the rule's own list of banned phrasings is not
        # read as prescribing them. It must not become a blanket amnesty: a block that
        # PRESCRIBES the phrasing still has to be caught.
        prescriptive = (
            "3. **Await the completion notification.** `park` at a resumable pause "
            "until the runtime's single completion-notification event arrives.\n"
            "   No poll loop; no Monitor action; the watcher issues zero tool calls "
            "during the wait."
        )
        blocks = list(_prescriptive_blocks(prescriptive))
        for phrase in ("park at a resumable pause", "no poll loop; no monitor action",
                       "the watcher issues zero tool calls during the wait"):
            assert any(phrase in b for b in blocks), \
                f"the filter swallowed a genuinely prescriptive block for {phrase!r}"

        forbidding = (
            "- **Never end a turn while waiting.** If the final message would say "
            '*"awaiting"* or *"the harness will notify me"*, the node has already failed.'
        )
        assert not list(_prescriptive_blocks(forbidding)), \
            "a block that forbids a phrasing must not be reported as prescribing it"

    def test_park_word_matcher_actually_matches(self):
        assert _PARK_WORD.search("park at a resumable pause")
        assert _PARK_WORD.search("parking until the child exits")
        assert not _PARK_WORD.search('PARKED=0'), \
            "the Bash trap variable PARKED must not be swept up by the prescriptive-park scan"
