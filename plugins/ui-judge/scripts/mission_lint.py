#!/usr/bin/env python3
"""Reject a mission that names implementation detail.

A mission says what a person wants. It never says where to click. This script
is the gate that keeps it that way.

Usage:
    python3 mission_lint.py FILE...

Exit code 0 means every file is clean. Exit code 1 means at least one file
names implementation detail, and each finding is printed on its own line.
Exit code 2 means this run did not check every file it was given: no file was
named, or a file could not be read. "Could not be read" covers a file that is
not valid UTF-8 as well as a file that is not there. Code 2 outranks code 1, so
a job never reads a typo in a filename as a mission that failed the gate.

The rule list is closed and deliberately small. A gate that blocks honest
prose is worse than a gate that misses a case.
"""

import re
import sys
from typing import NamedTuple


class Finding(NamedTuple):
    line: int
    rule: str
    found: str


# A `# grounded-in:` comment names a source file, so a file path and a `#`
# fragment are correct there. Every other line is prose that a person reads.
COMMENT = re.compile(r"^\s*#")

# The third field says whether a comment line is exempt from the rule. It sits
# on the rule itself because the exemption used to be a second list of rule
# names, held somewhere else, that had to agree with this one by hand. Renaming
# a rule then left the exemption pointing at a name that no longer existed, and
# the gate began to reject the `# grounded-in:` comments it is meant to allow.
# A false finding on every mission is easy to miss, because nothing crashes.
RULES = [
    ("url", re.compile(r"https?://\S+"), True),
    ("url-path", re.compile(r"(?<![\w.])/[A-Za-z0-9][\w.\-]*(?:/[\w.\-]+)*"), True),
    ("test-id", re.compile(r"data-test(?:id)?\b"), False),
    ("aria-ref", re.compile(r"\bref\s*=\s*e\d+|\baria-ref\b"), False),
    ("css-id", re.compile(r"(?<![\w#])#[A-Za-z][\w-]*"), True),
    (
        "selector-api",
        re.compile(
            r"\b(?:getBy[A-Z]\w*|locator|querySelector(?:All)?|xpath|css=)\b"
        ),
        False,
    ),
]


def lint_text(text: str) -> list[Finding]:
    """Return every place the text names implementation detail."""
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        is_comment = bool(COMMENT.match(line))
        for rule, pattern, comment_exempt in RULES:
            if is_comment and comment_exempt:
                continue
            # Every match, not only the first. A line that names two URLs must
            # report both, or the writer fixes one, runs the gate again, and
            # meets the same line a second time.
            for match in pattern.finditer(line):
                findings.append(Finding(number, rule, match.group(0)))
    return findings


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print("usage: mission_lint.py FILE...", file=sys.stderr)
        return 2

    total = 0
    unreadable = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as error:
            # Keep going. One bad path must not hide the findings in the files
            # beside it.
            #
            # A file that is not valid UTF-8 raises `UnicodeDecodeError`, which
            # is not an `OSError`. Left uncaught it ends the process with code 1
            # and a traceback, and code 1 says "a mission names implementation
            # detail" — a different fault with a different fix.
            reason = (
                "the file is not valid UTF-8"
                if isinstance(error, UnicodeDecodeError)
                else error.strerror
            )
            unreadable += 1
            print(
                f"mission_lint.py: cannot read {path}: {reason}",
                file=sys.stderr,
            )
            continue
        for finding in lint_text(text):
            total += 1
            print(
                f"{path}:{finding.line}: {finding.rule}: "
                f"a mission must not name {finding.found!r}"
            )

    if total:
        print(f"\n{total} finding(s). A mission says what a person wants, "
              f"never where to click.")

    # A file that could not be read outranks a finding. Exit code 1 means "a
    # mission names implementation detail", and a path that does not exist must
    # not borrow that code: a job with a typo in a filename would read exactly
    # like a mission that failed the gate. It also means the run was incomplete,
    # so neither a clean answer nor a finding count covers every file asked for.
    if unreadable:
        print(
            f"mission_lint.py: {unreadable} file(s) could not be read, "
            f"so this run did not check every file it was given.",
            file=sys.stderr,
        )
        return 2
    if total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
