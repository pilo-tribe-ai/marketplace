#!/usr/bin/env python3
"""Validate L2 skill ```relay-vocab``` blocks against the language-reference doc.

Each L2 skill declares its vocabulary in a single fenced ```relay-vocab``` block:

    ```relay-vocab
    l1-shape: <one L1 pattern name>
    l0-deps: <comma/space-separated L0 keyword names>
    acpx-leg-required: true|false
    ```

This gate enforces that `l1-shape` resolves to a known L1 pattern, every `l0-deps`
token resolves to a known L0 keyword, `acpx-leg-required` is true/false, and exactly
one block is present.  The L0/L1 name sets are derived once at module-load time from
`docs/language-reference.md` via `validate_language_reference.extract_table` — that
doc is the single source of truth.

Usage:
    python validate_l2_vocab.py

Exit code 0 = all L2 skills pass; 1 = one or more violations (printed).
Importable: `check_skill(skill_text) -> list[str]` returns violation strings ([] = pass).
"""
import importlib.util
import re
import sys
from pathlib import Path

_VLR_PATH = Path(__file__).resolve().parent / "validate_language_reference.py"
_spec = importlib.util.spec_from_file_location("validate_language_reference", _VLR_PATH)
_vlr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vlr)

DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "language-reference.md"
_doc_text = DOC_PATH.read_text(encoding="utf-8")

(_l0_header, _l0_rows), _err = _vlr.extract_table(_doc_text, "L0")
if _err:
    raise ValueError(f"L0 table parse failed: {_err}")
(_l1_header, _l1_rows), _err = _vlr.extract_table(_doc_text, "L1")
if _err:
    raise ValueError(f"L1 table parse failed: {_err}")
_L0_NAMES = {r["name"] for r in _l0_rows}
_L1_NAMES = {r["name"] for r in _l1_rows}

# Single source of truth for the L2 skill roster (Tasks 2–7).
L2_NAMES = ["panel", "delegate-leaf", "improve-loop", "brainstorm-decide",
            "parallel-gather", "staged-run", "delegate-and-watch"]

_REQUIRED_KEYS = ("l1-shape", "l0-deps", "acpx-leg-required")


def parse_vocab_block(skill_text: str) -> dict:
    """Find the single ```relay-vocab``` fenced block and parse its `key: tokens`
    lines into a dict (token lists split on `[,\\s]+`).

    Raise ValueError if zero blocks are found ("no relay-vocab block found") or if
    multiple blocks are found ("multiple relay-vocab blocks found: N").
    """
    blocks = re.findall(r"```relay-vocab\n(.*?)```", skill_text, re.DOTALL)
    if len(blocks) == 0:
        raise ValueError("no relay-vocab block found")
    if len(blocks) > 1:
        raise ValueError(f"multiple relay-vocab blocks found: {len(blocks)}")
    parsed: dict = {}
    for line in blocks[0].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        tokens = [t for t in re.split(r"[,\s]+", rest.strip()) if t]
        parsed[key] = tokens
    return parsed


def check_skill(skill_text: str) -> list[str]:
    """Return a list of vocab violations ([] = the skill passes the L2-vocab gate).

    Pure list-return — never propagates exceptions to callers.
    """
    violations: list[str] = []
    try:
        block = parse_vocab_block(skill_text)
    except ValueError as exc:
        violations.append(str(exc))
        return violations

    missing = [k for k in _REQUIRED_KEYS if k not in block]
    if missing:
        violations.append(f"missing required key(s): {', '.join(missing)}")

    if "l1-shape" in block:
        shape_tokens = block["l1-shape"]
        if len(shape_tokens) != 1:
            violations.append(
                f"l1-shape must be a single token, got {shape_tokens}"
            )
        for tok in shape_tokens:
            if tok not in _L1_NAMES:
                violations.append(f"l1-shape '{tok}' is not a known L1 pattern")

    if "l0-deps" in block:
        for tok in block["l0-deps"]:
            if tok not in _L0_NAMES:
                violations.append(f"l0-deps token '{tok}' is not a known L0 keyword")

    if "acpx-leg-required" in block:
        vals = block["acpx-leg-required"]
        val = vals[0].lower() if vals else ""
        if val not in ("true", "false"):
            violations.append(
                f"acpx-leg-required must be true/false, got '{' '.join(vals)}'"
            )

    return violations


def main(argv: list[str]) -> int:
    skill_root = Path(__file__).resolve().parent.parent / "skills"
    failed = False
    for name in L2_NAMES:
        path = skill_root / name / "SKILL.md"
        if not path.exists():
            print(f"FAIL: {name}: SKILL.md not found at {path}", file=sys.stderr)
            failed = True
            continue
        errors = check_skill(path.read_text(encoding="utf-8"))
        if errors:
            failed = True
            print(f"FAIL: {name}: {len(errors)} violation(s):", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
        else:
            print(f"OK: {name} passes the L2-vocab gate.")
    if not DOC_PATH.exists():
        print(f"ERROR: language-reference doc not found: {DOC_PATH}", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
