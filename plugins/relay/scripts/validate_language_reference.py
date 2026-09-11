#!/usr/bin/env python3
"""Validate the relay language-reference doc against the DSL design Phase-1 gate.

Usage:
    python validate_language_reference.py [path-to-language-reference.md]

Exit code 0 = all gate checks pass; 1 = one or more violations (printed).
Importable: `check(text) -> list[str]` returns violation strings ([] = pass).
"""
import re
import sys
from pathlib import Path

# Default path to the shipped doc, relative to this script.
DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "language-reference.md"

# --- Canonical vocabulary (DSL design §3.1 / §3.2 / §6.0) ---
CANONICAL_L0 = {
    "control-flow": ["sequence", "for-each", "loop-until", "parallel",
                     "branch", "abort", "skip", "park"],
    "bounds": ["cap", "budget", "done-criterion", "clean-streak", "circuit-breaker"],
    "actors": ["role", "mechanism-resolve", "capability-validate", "delegate",
               "session-grounding", "leaf-constraint"],
    "work": ["compute", "classify", "join-by-key", "typed-output", "freshness-verify",
             "evidence-before-assertion"],
    "state": ["produce", "read", "checkpoint", "marker", "mutate-in-place",
              "oracle", "fresh-seed-reset", "closeout"],
}
L0_NAMES = {n for names in CANONICAL_L0.values() for n in names}
L0_CATEGORY = {n: cat for cat, names in CANONICAL_L0.items() for n in names}

CANONICAL_L1 = [
    "pipeline", "loop-until-clean", "multi-turn-dispatch", "router-loop",
    "fan-out-aggregate", "quorum-decide", "gate", "delegate-and-verify",
    "resume-from-checkpoint", "normalize-and-rollup", "drive-to-done",
]
# §6.0 partition: the two L1 partials require the acpx leg; the other eight are native.
L1_ACPX_REQUIRED = {"multi-turn-dispatch", "router-loop"}
L1_REQUIRED_FIELDS = ["name", "shape", "l0-deps", "when-to-use", "acpx-leg-required"]


# --- Markdown pipe-table parsing ---
def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def extract_table(text: str, section_marker: str):
    """Return ((header, rows), None) for the first pipe-table under a `## …<marker>…`
    heading, or (None, error_message) if the section or its table is absent.
    `rows` is a list of dicts keyed by the header cells.
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("## ") and section_marker in ln:
            start = i
            break
    if start is None:
        return None, f"section heading containing '{section_marker}' not found"

    j = start + 1
    while j < len(lines) and not lines[j].lstrip().startswith("|"):
        if lines[j].strip().startswith("## "):
            return None, f"no table found in section '{section_marker}'"
        j += 1
    if j >= len(lines):
        return None, f"no table found in section '{section_marker}'"

    header = _split_row(lines[j])
    rows = []
    k = j + 2  # skip the |---|---| separator row
    while k < len(lines) and lines[k].lstrip().startswith("|"):
        cells = _split_row(lines[k])
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
        k += 1
    return (header, rows), None


# --- Gate checks ---
def _check_l0(text: str) -> list[str]:
    errors: list[str] = []
    res, err = extract_table(text, "L0")
    if err:
        return [err]
    header, rows = res
    for f in ("name", "category", "definition"):
        if f not in header:
            errors.append(f"L0 table missing column '{f}'")
    if errors:
        return errors

    names = [r.get("name", "") for r in rows]
    if len(rows) != 33:
        errors.append(f"L0 expected 33 entries, found {len(rows)}")
    if set(names) != L0_NAMES:
        missing = sorted(L0_NAMES - set(names))
        extra = sorted(set(names) - L0_NAMES)
        if missing:
            errors.append(f"L0 missing keywords: {missing}")
        if extra:
            errors.append(f"L0 unknown keywords: {extra}")
    for r in rows:
        n = r.get("name", "")
        if not r.get("definition", "").strip():
            errors.append(f"L0 '{n}' has empty definition")
        cat = r.get("category", "")
        if n in L0_CATEGORY and cat != L0_CATEGORY[n]:
            errors.append(f"L0 '{n}' category '{cat}' != expected '{L0_CATEGORY[n]}'")
    return errors


def _check_l1(text: str) -> list[str]:
    errors: list[str] = []
    res, err = extract_table(text, "L1")
    if err:
        return [err]
    header, rows = res
    for f in L1_REQUIRED_FIELDS:
        if f not in header:
            errors.append(f"L1 table missing column '{f}'")
    if errors:
        return errors

    names = [r.get("name", "") for r in rows]
    if len(rows) != 11:
        errors.append(f"L1 expected 11 entries, found {len(rows)}")
    if set(names) != set(CANONICAL_L1):
        missing = sorted(set(CANONICAL_L1) - set(names))
        extra = sorted(set(names) - set(CANONICAL_L1))
        if missing:
            errors.append(f"L1 missing patterns: {missing}")
        if extra:
            errors.append(f"L1 unknown patterns: {extra}")

    for r in rows:
        n = r.get("name", "")
        for f in L1_REQUIRED_FIELDS:
            if not r.get(f, "").strip():
                errors.append(f"L1 '{n}' missing required field '{f}'")
        for dep in (d for d in re.split(r"[,\s]+", r.get("l0-deps", "")) if d):
            if dep not in L0_NAMES:
                errors.append(f"L1 '{n}' l0-dep '{dep}' is not a known L0 keyword")
        val = r.get("acpx-leg-required", "").strip().lower()
        if val not in ("true", "false"):
            errors.append(f"L1 '{n}' acpx-leg-required must be true/false, got '{val}'")
        elif (val == "true") != (n in L1_ACPX_REQUIRED):
            expected = str(n in L1_ACPX_REQUIRED).lower()
            errors.append(
                f"L1 '{n}' acpx-leg-required={val} inconsistent with §6 partition "
                f"(expected {expected})"
            )
    return errors


def check(text: str) -> list[str]:
    """Return a list of gate violations ([] = the doc passes the Phase-1 gate)."""
    errors: list[str] = []
    errors += _check_l0(text)
    errors += _check_l1(text)
    if "## Authoring Guidelines" not in text:
        errors.append("missing '## Authoring Guidelines' preface section")
    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DOC_PATH
    if not path.exists():
        print(f"ERROR: language-reference doc not found: {path}", file=sys.stderr)
        return 1
    errors = check(path.read_text(encoding="utf-8"))
    if errors:
        print(f"FAIL: {len(errors)} gate violation(s) in {path}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: {path} passes the Phase-1 language-reference gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
