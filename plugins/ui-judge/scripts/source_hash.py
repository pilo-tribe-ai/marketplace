#!/usr/bin/env python3
"""Find document drift before a browser opens.

A mission records the source it came from and the SHA-256 of that source at
the moment a person approved it:

    # grounded-in: docs/user-guide.md#buying-an-item
    # grounded-in-hash: 8f3c2a91...

If the source changed, the mission may no longer say what the project means.
This script finds that, and it needs no model to do it.

Usage:
    python3 source_hash.py hash FILE
    python3 source_hash.py check MISSION --root DIR

`check` exits 1 when any source changed, went missing, or has no recorded hash.
It also exits 1 when the mission names no source at all. A mission with no
`# grounded-in:` line is not a mission with nothing to check: it is a mission
nobody grounded, and a silent 0 would read exactly like a clean pass.

Both commands exit 2 when a file named on the command line cannot be read. That
is not drift, and it must not share drift's exit code. A source that a readable
mission names, and that is gone or cannot be opened, is still drift: it exits 1.

"Cannot be read" covers a file that is not valid UTF-8 as well as a file that is
not there. Both leave the run with nothing to compare, and a decode error that
escapes would end the process with code 1, which the caller reads as drift and
answers by marking the mission `needs review`.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import NamedTuple

# One pattern for both lines. `finditer` yields matches in document order, and
# the pairing rule below is "a hash belongs to the source above it", so reading
# in order is the whole job. Two patterns meant two passes and then a sort to
# put the results back into the order one pass never lost.
MARK = re.compile(r"^\s*#\s*grounded-in(-hash)?:\s*(\S+)", re.MULTILINE)


class Grounding(NamedTuple):
    source: str
    digest: str | None


class Drift(NamedTuple):
    source: str
    state: str
    digest: str


def why(error) -> str:
    """Say in plain words why a file could not be read.

    A file that is not valid UTF-8 raises `UnicodeDecodeError`, which carries no
    `strerror`. It still means the same thing to a caller: this run read
    nothing.
    """
    if isinstance(error, UnicodeDecodeError):
        return "the file is not valid UTF-8"
    return error.strerror


def hash_file(path) -> str:
    """Return the SHA-256 of the whole file, as hex."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_grounding(text: str) -> list[Grounding]:
    """Read every grounded-in and grounded-in-hash pair, in order.

    A hash belongs to the source above it. A source with no hash below it
    gets None, which `check` reports as unrecorded.
    """
    pairs: list[Grounding] = []
    for match in MARK.finditer(text):
        is_digest, value = match.group(1), match.group(2)
        if not is_digest:
            pairs.append(Grounding(value, None))
        elif pairs and pairs[-1].digest is None:
            pairs[-1] = Grounding(pairs[-1].source, value)
    return pairs


def check(mission_path, repo_root) -> list[Drift]:
    """Compare each recorded hash with the source as it is now."""
    text = Path(mission_path).read_text(encoding="utf-8")
    root = Path(repo_root)

    results: list[Drift] = []
    grounding = read_grounding(text)
    if not grounding:
        # No source named at all. Reporting nothing and exiting 0 would tell a
        # caller "no drift", and the mission would then be judged as if a
        # person had grounded and approved it.
        return [Drift(str(mission_path), "ungrounded", "")]

    for pair in grounding:
        # A source may carry a fragment, as in guide.md#checkout. The hash is
        # always of the whole file, so drop the fragment before opening it.
        name = pair.source.split("#", 1)[0]
        path = root / name

        if not path.is_file():
            results.append(Drift(pair.source, "missing", ""))
            continue
        try:
            now = hash_file(path)
        except OSError:
            # A source the mission names, that is there and cannot be opened,
            # is drift like a missing one: nobody can say the mission still
            # matches it. Exit code 2 is for the file named on the command
            # line, and letting this raise would hand the caller "the mission
            # could not be read" when the mission read fine.
            results.append(Drift(pair.source, "unreadable", ""))
            continue
        if pair.digest is None:
            results.append(Drift(pair.source, "unrecorded", now))
        elif pair.digest == now:
            results.append(Drift(pair.source, "ok", now))
        else:
            results.append(Drift(pair.source, "changed", now))
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    one = sub.add_parser("hash", help="print the SHA-256 of a file")
    one.add_argument("file")

    many = sub.add_parser("check", help="compare a mission against its sources")
    many.add_argument("mission")
    many.add_argument("--root", required=True, help="directory the sources sit in")

    args = parser.parse_args(argv[1:])

    # Exit code 1 means "a source drifted". A path that cannot be read is a
    # different thing, and it must not borrow that code. `error.filename` names
    # the file that actually failed, so the message stays true even when the
    # mission was readable and something under it was not.
    def unreadable(error, fallback) -> int:
        print(
            f"source_hash.py: cannot read "
            f"{getattr(error, 'filename', None) or fallback}: {why(error)}",
            file=sys.stderr,
        )
        return 2

    if args.command == "hash":
        try:
            digest = hash_file(args.file)
        except OSError as error:
            return unreadable(error, args.file)
        print(digest)
        return 0

    try:
        results = check(args.mission, args.root)
    except (OSError, UnicodeDecodeError) as error:
        return unreadable(error, args.mission)
    drifted = 0
    for result in results:
        print(f"{result.state}: {result.source}")
        if result.state != "ok":
            drifted += 1
            if result.state in ("changed", "unrecorded"):
                print(f"  the source is now {result.digest}")

    if drifted:
        print(f"\n{drifted} source(s) need review before this mission is trusted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
