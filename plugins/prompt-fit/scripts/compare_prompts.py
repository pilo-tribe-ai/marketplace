#!/usr/bin/env python3
"""Measure one prompt against its earlier form, and say whether the revision moved anything.

A revision that neither drops an instruction nor clears a finding changed the
wording and nothing else. Exit code 1 says so, so a revision loop cannot report
success on a rewrite that measures the same.

Exit codes:
  0  the instruction count went down, or the finding count went down
  1  neither count went down
  2  a file could not be read
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_lint import (  # noqa: E402
    PER_RULE_DEFAULT,
    ReadError,
    analyse,
    read_source,
)


def compare(before: dict, after: dict) -> dict:
    """Return the deltas between two analyses, and the verdict."""
    before_findings = len(before["findings"])
    after_findings = len(after["findings"])
    instruction_delta = after["instructions"] - before["instructions"]
    finding_delta = after_findings - before_findings

    kinds_before = _kinds(before)
    kinds_after = _kinds(after)
    cleared = sorted(kind for kind in kinds_before if kinds_after.get(kind, 0) < kinds_before[kind])
    added = sorted(kind for kind in kinds_after if kinds_after[kind] > kinds_before.get(kind, 0))

    moved = instruction_delta < 0 or finding_delta < 0
    return {
        "before": {
            "path": before["path"],
            "instructions": before["instructions"],
            "reference_lines": before["reference_lines"],
            "estimate": before["estimate"],
            "band": before["band"],
            "findings": before_findings,
        },
        "after": {
            "path": after["path"],
            "instructions": after["instructions"],
            "reference_lines": after["reference_lines"],
            "estimate": after["estimate"],
            "band": after["band"],
            "findings": after_findings,
        },
        "delta": {
            "instructions": instruction_delta,
            "reference_lines": after["reference_lines"] - before["reference_lines"],
            "estimate": round(after["estimate"] - before["estimate"], 4),
            "findings": finding_delta,
        },
        "cleared_kinds": cleared,
        "added_kinds": added,
        "moved": moved,
    }


def _kinds(report: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report["findings"]:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return counts


def signed(value: float, suffix: str = "") -> str:
    return f"{value:+g}{suffix}"


def render(result: dict) -> str:
    before, after, delta = result["before"], result["after"], result["delta"]
    rows = [
        ("instructions", before["instructions"], after["instructions"], signed(delta["instructions"])),
        ("reference lines", before["reference_lines"], after["reference_lines"], signed(delta["reference_lines"])),
        (
            "all-rules estimate",
            f"{before['estimate'] * 100:.0f}%",
            f"{after['estimate'] * 100:.0f}%",
            signed(round(delta["estimate"] * 100), "pp"),
        ),
        ("band", before["band"], after["band"], ""),
        ("findings", before["findings"], after["findings"], signed(delta["findings"])),
    ]
    out = [f"before  {before['path']}", f"after   {after['path']}", ""]
    out.append(f"  {'':<20}{'before':>10}{'after':>10}{'delta':>10}")
    for name, left, right, change in rows:
        out.append(f"  {name:<20}{str(left):>10}{str(right):>10}{change:>10}")
    out.append("")
    if result["cleared_kinds"]:
        out.append("  cleared: " + ", ".join(result["cleared_kinds"]))
    if result["added_kinds"]:
        out.append("  added:   " + ", ".join(result["added_kinds"]))
    out.append("")
    if result["moved"]:
        out.append("the revision moved at least one count down")
    else:
        out.append(
            "the revision moved no count down: same instruction count, same finding count"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure a revised prompt against its earlier form.",
    )
    parser.add_argument("before", help="the earlier file, or - for standard input")
    parser.add_argument("after", help="the revised file")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--per-rule", type=float, default=PER_RULE_DEFAULT)
    args = parser.parse_args(argv)

    if not 0.0 < args.per_rule <= 1.0:
        print("--per-rule takes a number above 0 and at or below 1", file=sys.stderr)
        return 2

    try:
        before_text = read_source(args.before)
        after_text = read_source(args.after)
    except ReadError as error:
        print(str(error), file=sys.stderr)
        return 2

    result = compare(
        analyse(before_text, args.before, args.per_rule),
        analyse(after_text, args.after, args.per_rule),
    )
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["moved"] else 1


if __name__ == "__main__":
    sys.exit(main())
