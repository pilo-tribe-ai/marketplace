#!/usr/bin/env python3
"""Generate the ADR register between its markers. Standard library only.

The generator owns the link text, the grouping, and the status. The key is
the link href, and the hand-authored summary after the status cell survives
every regeneration.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adr_lib  # noqa: E402

SEP = " — "
BEGIN = "<!-- ADR-INDEX:BEGIN (generated — do not edit) -->"
END = "<!-- ADR-INDEX:END -->"
NOTE = ("> _Generated from each ADR's frontmatter. Do not hand-edit between the "
        "markers. Run `/adr:index`._")
TODO = "<!-- TODO: summary -->"
UNFILED = "unfiled"

ROW_RE = re.compile(r"^- \[(?P<label>[^\]]*)\]\((?P<href>[^)]*)\)(?P<rest>.*)$")
UNPARSED_HEADING = "### unparsed rows (left as written)"

BEGIN_RE = re.compile(r"^<!--\s*ADR-INDEX:BEGIN\b.*?-->[ \t]*$", re.MULTILINE)
END_RE = re.compile(r"^<!--\s*ADR-INDEX:END\s*-->[ \t]*$", re.MULTILINE)
SEED = "# Architecture decisions\n\n"


class DuplicateRow(Exception):
    pass


def status_cell(adr, corpus) -> str:
    replaced_by = adr_lib.refs(adr.meta, "superseded_by")
    if adr.status == "superseded" and replaced_by:
        names = [adr_lib.prefix_of(name, corpus.id_scheme) or name for name in replaced_by]
        return "superseded by " + ", ".join(names)
    return adr.status or "unknown"


def row_for(adr, corpus, href: str, summary: str) -> str:
    label = f"{adr.prefix}{SEP}{adr.title}" if adr.prefix else (adr.title or adr.filename)
    return f"- [{label}]({href}){SEP}{status_cell(adr, corpus)}{SEP}{summary}"


def build_block(corpus, summaries: dict, unparsed=(), *, adrs=None, archived_adrs=None) -> str:
    if adrs is None:
        adrs = [adr_lib.parse_adr(p, corpus.id_scheme) for p in adr_lib.discover(corpus)]
    groups = {}
    for adr in adrs:
        groups.setdefault(adr.area or UNFILED, []).append(adr)
    lines = [BEGIN, NOTE, ""]
    for area in sorted(groups, key=lambda name: (name == UNFILED, name.lower())):
        lines.append(f"### {area}")
        for adr in sorted(groups[area], key=lambda a: a.filename):
            href = f"./{adr.filename}"
            lines.append(row_for(adr, corpus, href, summaries.get(href, TODO)))
        lines.append("")
    if archived_adrs is None:
        archived_adrs = [adr_lib.parse_adr(p, corpus.id_scheme)
                         for p in adr_lib.discover_archived(corpus)]
    if archived_adrs:
        lines.append("### archived")
        for adr in archived_adrs:
            href = f"./{corpus.config['archive_dir']}/{adr.filename}"
            lines.append(row_for(adr, corpus, href, summaries.get(href, TODO)))
        lines.append("")
    if unparsed:
        lines.append(UNPARSED_HEADING)
        lines.extend(unparsed)
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def block_of(text: str):
    bounds = _bounds(text)
    return None if bounds is None else text[bounds[0]:bounds[1]]


def _bounds(text: str):
    begin, end = BEGIN_RE.search(text), END_RE.search(text)
    if not begin or not end or end.start() < begin.end():
        return None
    return begin.start(), end.end()


def read_rows(register_text: str):
    """Return (summaries_by_href, unparsed_rows).

    The href is the key, never row position. The summary is everything after
    the second SEP that follows the link, which is the last field boundary --
    so an em dash inside the label, inside the status cell, or inside the
    summary itself never miscounts a field. The "dropped row" receipt is
    computed by the caller against the live corpus, which read_rows does not
    know.
    """
    inner = block_of(register_text)
    if inner is None:
        return {}, []
    summaries, unparsed = {}, []
    for line in inner.splitlines():
        if not line.startswith("- "):
            continue
        match = ROW_RE.match(line)
        if not match or match.group("rest").count(SEP) < 2:
            unparsed.append(line)
            continue
        href = match.group("href").strip()
        summary = match.group("rest").split(SEP, 2)[2].strip()
        if href in summaries:
            raise DuplicateRow(href)
        summaries[href] = summary
    return summaries, unparsed


def inject(text: str, block: str) -> str:
    bounds = _bounds(text)
    if bounds is None:
        base = text.rstrip("\n")
        return (base + "\n\n" + block + "\n") if base else (SEED + block + "\n")
    return text[:bounds[0]] + block + text[bounds[1]:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate the ADR register")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--config")
    parser.add_argument("--repo-root")
    args = parser.parse_args()

    corpus = adr_lib.load_corpus(args.repo_root, args.config)
    current = corpus.register.read_text(encoding="utf-8") if corpus.register.is_file() else ""
    try:
        summaries, unparsed = read_rows(current)
    except DuplicateRow as duplicate:
        print(f"ERROR: duplicate register row for {duplicate}", file=sys.stderr)
        return 1

    live = {f"./{path.name}" for path in adr_lib.discover(corpus)}
    if corpus.config.get("archive_dir"):
        live |= {f"./{corpus.config['archive_dir']}/{path.name}"
                 for path in adr_lib.discover_archived(corpus)}
    dropped = {href: text for href, text in summaries.items()
               if href not in live and text != TODO}
    block = build_block(corpus, summaries, unparsed)

    if args.check:
        if block_of(current) == block:
            print("register up to date")
            return 0
        print("register is stale against the corpus", file=sys.stderr)
        return 1

    corpus.register.parent.mkdir(parents=True, exist_ok=True)
    fresh = inject(current, block)
    if fresh != current:
        corpus.register.write_text(fresh, encoding="utf-8")
    for href, text in sorted(dropped.items()):
        print(f"dropped row: {href}{SEP}{text}")
    for line in unparsed:
        print(f"unparsed row: {line}")
    print(f"wrote {corpus.register.relative_to(corpus.root).as_posix()} "
          f"({len(live)} ADRs indexed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
