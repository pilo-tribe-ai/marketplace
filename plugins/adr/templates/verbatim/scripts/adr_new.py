#!/usr/bin/env python3
"""Create one ADR. Standard library only.

The filename is the identity: this writes no `id` field. Under
'sequential' the next four-digit prefix is one above the highest in use,
counting archived files, so a retired prefix is never reused.
"""
import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adr_lib  # noqa: E402

BODY_HEADINGS = ("## Context", "## Decision", "## Why",
                 "## Alternatives considered", "## Consequences")


def next_id(corpus, today=None, *, paths=None) -> str:
    if corpus.id_scheme == "date":
        return today or _dt.date.today().isoformat()
    if paths is None:
        paths = list(adr_lib.discover(corpus)) + list(adr_lib.discover_archived(corpus))
    used = []
    for path in paths:
        prefix = adr_lib.prefix_of(path.name, "sequential")
        if prefix is not None:
            used.append(int(prefix))
    return f"{(max(used) + 1) if used else 1:04d}"


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > 60:
        slug = slug[:60].rsplit("-", 1)[0]
    return slug or "untitled"


def body_for(prefix: str, title: str) -> str:
    lines = [f"# ADR-{prefix}: {title}", ""]
    for heading in BODY_HEADINGS:
        lines += [heading, "", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one ADR")
    parser.add_argument("--title", required=True)
    parser.add_argument("--area")
    parser.add_argument("--status", default="proposed", choices=list(adr_lib.STATUSES))
    parser.add_argument("--date")
    parser.add_argument("--id", help="override the allocated prefix")
    parser.add_argument("--supersedes", action="append", default=[])
    parser.add_argument("--related", action="append", default=[])
    parser.add_argument("--config")
    parser.add_argument("--repo-root")
    args = parser.parse_args()

    corpus = adr_lib.load_corpus(args.repo_root, args.config)
    if not corpus.dir.is_dir():
        print(f"ERROR: corpus directory {corpus.dir} does not exist", file=sys.stderr)
        return 2
    today = args.date or _dt.date.today().isoformat()
    paths = list(adr_lib.discover(corpus)) + list(adr_lib.discover_archived(corpus))
    prefix = args.id or next_id(corpus, today=today, paths=paths)

    if corpus.id_scheme == "sequential":
        taken = {adr_lib.prefix_of(p.name, "sequential") for p in paths}
        if prefix in taken:
            print(f"ERROR: prefix {prefix} is already in use", file=sys.stderr)
            return 1

    path = corpus.dir / f"{prefix}-{slugify(args.title)}.md"
    if path.exists():
        print(f"ERROR: {path.name} already exists", file=sys.stderr)
        return 1

    meta = {"type": "adr", "status": args.status, "date": today,
            "title": args.title, "area": args.area,
            "supersedes": args.supersedes, "superseded_by": [],
            "related": args.related}
    path.write_text("---\n" + adr_lib.dump_frontmatter(meta) + "---\n\n"
                    + body_for(prefix, args.title), encoding="utf-8")
    print(path.relative_to(corpus.root).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
