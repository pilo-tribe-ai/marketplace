"""Guard tests for improve-loop/SKILL.md — spec 2026-07-25 §2.1, the three-label set.

The skill used to classify critic verdicts against a *closed two-label* set: clean
versus findings. There was no label for "the critic did not answer", so generated
workflows folded no-answer into clean and a run whose verify phase returned `null`
reported success.

The closed set is now three labels. The load-bearing assertion in this file is the
routing one: `no-answer` must never reach the clean exit.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
SKILL = PLUGIN_ROOT / "skills" / "improve-loop" / "SKILL.md"
LANG_REF = PLUGIN_ROOT / "docs" / "language-reference.md"

LABELS = ("clean", "findings", "no-answer")


def _body():
    return SKILL.read_text()


def _description():
    body = _body()
    end = body.index("---", 3)
    return next(ln for ln in body[3:end].splitlines() if ln.startswith("description:"))


def _norm(text: str) -> str:
    text = text.lower().replace("`", "").replace("*", "").replace("—", "-")
    return re.sub(r"\s+", " ", text)


class TestThreeLabels:
    def test_skill_file_exists(self):
        assert SKILL.is_file()

    @pytest.mark.parametrize("label", LABELS)
    def test_label_present_as_a_token(self, label):
        # Backticked so each label is individually greppable and cannot be read as prose.
        assert f"`{label}`" in _body(), f"the closed label set must name `{label}`"

    @pytest.mark.parametrize("label", LABELS)
    def test_label_named_in_description(self, label):
        assert label in _description(), \
            f"the frontmatter description must name the {label!r} label — it is the skill's contract"

    def test_no_answer_is_defined(self):
        norm = _norm(_body())
        assert "no-answer" in norm and "null, empty, or unparseable" in norm, \
            "no-answer must be defined as null, empty, or unparseable — not left to interpretation"

    def test_set_is_declared_closed_and_three(self):
        norm = _norm(_body())
        assert "closed three-label set" in norm, \
            "the label set must be declared closed and three-valued"


class TestNoAnswerRoutesToFailure:
    """The assertion that actually encodes §2.1. Structural, not keyword soup."""

    def _lines_mentioning(self, needle):
        return [ln for ln in _body().splitlines() if needle in ln]

    def test_no_answer_is_named_a_dispatch_failure(self):
        lines = self._lines_mentioning("`no-answer`")
        assert lines, "no route mentions `no-answer`"
        joined = _norm(" ".join(lines))
        assert "dispatch failure" in joined or "never a pass" in joined, \
            "the no-answer route must state it is a dispatch failure and never a pass"

    def test_no_answer_never_reaches_the_clean_exit(self):
        exit_lines = self._lines_mentioning("exits the loop")
        assert exit_lines, "no line describes the loop exit"
        for line in exit_lines:
            assert "no-answer" not in line, \
                f"no-answer must not share the clean exit: {line.strip()!r}"
        assert any("clean" in ln for ln in exit_lines), \
            "the clean label is the one that exits the loop"

    def test_no_answer_forces_an_unverified_result(self):
        norm = _norm(_body())
        assert "unverified" in norm, \
            "a forced exit after no-answer must surface an explicitly unverified result"

    def test_forced_exit_distinguishes_unclean_from_unverified(self):
        # Step 4's bound: an unverified force-exit must not be reported as merely
        # "still unclean", or the two failure modes collapse again.
        norm = _norm(_body())
        assert "report neither as clean" in norm or "never with a silent pass" in norm, \
            "the bounded exit must refuse to report either outcome as clean"

    def test_missing_verdict_is_not_folded_into_clean(self):
        norm = _norm(_body())
        assert "never fold it into clean" in norm, \
            "the skill must say outright that a missing verdict is not a clean verdict"


class TestBinaryFramingGone:
    """Negative assertions — the two-label framing that caused the bug."""

    @pytest.mark.parametrize("phrase", [
        "closed clean-predicate label set",
        "as clean or not",
        "when it is not clean",
        "versus one that still carries findings",
    ])
    def test_binary_phrase_absent(self, phrase):
        assert phrase not in _norm(_body()), \
            f"{phrase!r} is the binary clean/not-clean framing §2.1 exists to kill"

    def test_description_no_longer_binary(self):
        assert "clean or not" not in _norm(_description()), \
            "the description must name the three labels, not a binary predicate"


class TestVocabBlockIntact:
    """Fixing the doctrine must not break the vocabulary gate."""

    def test_l1_shape_unchanged(self):
        assert "l1-shape: loop-until-clean" in _body()

    @pytest.mark.parametrize("dep", ["loop-until", "classify", "cap", "budget", "branch"])
    def test_l0_dep_survives(self, dep):
        line = next(ln for ln in _body().splitlines() if ln.startswith("l0-deps:"))
        deps = [d.strip() for d in line.split(":", 1)[1].split(",")]
        assert dep in deps, f"l0-dep {dep!r} must survive the doctrine fix"

    def test_validator_still_accepts_the_skill(self):
        script = PLUGIN_ROOT / "scripts" / "validate_l2_vocab.py"
        proc = subprocess.run([sys.executable, str(script)],
                              cwd=str(PLUGIN_ROOT), capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestCrossFileCoherence:
    """improve-loop realizes the `loop-until-clean` L1 pattern. If the pattern's own row
    still says "exit clean or iterate", the plugin disagrees with itself again — which is
    exactly the class of defect that produced this bug."""

    def _loop_until_clean_row(self):
        rows = [ln for ln in LANG_REF.read_text().splitlines()
                if ln.startswith("|") and "loop-until-clean" in ln]
        assert rows, "docs/language-reference.md must define the loop-until-clean L1 pattern"
        return rows[0]

    @pytest.mark.parametrize("label", LABELS)
    def test_pattern_row_names_the_same_labels(self, label):
        assert label in self._loop_until_clean_row(), (
            f"the loop-until-clean row must name {label!r} — the L1 pattern and the L2 "
            "skill that realizes it may not carry different doctrines"
        )

    def test_pattern_row_routes_no_answer_to_failure(self):
        # `clean` alone is weak evidence — it is a substring of the pattern's own name.
        # Pin the routing sentence instead.
        row = _norm(self._loop_until_clean_row())
        assert "clean exits" in row, "the row must say the clean label exits"
        assert "findings iterates" in row, "the row must say the findings label iterates"
        assert "no-answer is a dispatch failure" in row and "never a pass" in row, \
            "the row must route no-answer to failure, never to the exit"

    def test_pattern_row_no_longer_binary(self):
        assert "exit clean or iterate" not in _norm(self._loop_until_clean_row()), \
            "the row's old binary shape ('classify, exit clean or iterate') must be gone"

    def test_pattern_row_is_still_well_formed(self):
        # validate_language_reference.py parses these rows by splitting on '|'.
        row = self._loop_until_clean_row()
        assert row.count("\n") == 0 and len(row.split("|")) == 8, \
            f"row must stay a single 6-cell table line: {row!r}"
