#!/usr/bin/env python3
"""Convert a legacy bold-key corpus to frontmatter. Standard library only.

Two levers, because one of them breaks links: --frontmatter (the default)
folds the bold keys and leaves every filename alone; --rename also normalises
the filename and carries the register summary to the new key. Every change is
staged for review; this commits nothing.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adr_lib  # noqa: E402

RENAME_RE = re.compile(r"^(?:ADR-)?0*([0-9]+)-(.+)\.md$", re.IGNORECASE)


def normalized_name(filename: str, id_scheme: str) -> str:
    """ADR-002-slug.md -> 0002-slug.md, under the sequential scheme only.
    Under the date scheme nothing needs normalising, so the name is
    returned unchanged. [inferred]"""
    if id_scheme != "sequential":
        return filename
    match = RENAME_RE.match(filename)
    if not match:
        return filename
    number, slug = match.groups()
    return f"{int(number):04d}-{slug}.md"


def fold(path: Path, corpus, *, text=None, known=None) -> tuple:
    """Return (changed, unresolved_refs). A file that already carries
    frontmatter is left exactly as it is. A legacy bold-key line whose
    reference cannot be resolved against the known corpus is left in the
    body, unchanged, so the lint can report it; every other bold-key line
    folds into frontmatter and is dropped from the body. [inferred]"""
    if text is None:
        text = path.read_text(encoding="utf-8")
    if adr_lib.split_frontmatter(text)[0] is not None:
        return False, []
    adr = adr_lib.parse_adr(path, corpus.id_scheme)
    if known is None:
        known = {p.name for p in adr_lib.discover(corpus)}
    unresolved, meta = [], {"type": "adr", "status": adr.status, "date": adr.date,
                            "title": adr.title, "area": adr.meta.get("area")}
    keys_with_unresolved = set()  # [inferred]
    for key in adr_lib.LIST_KEYS:
        keep = []
        for ref in adr_lib.refs(adr.meta, key):
            if Path(ref).name in known:
                keep.append(Path(ref).name)
            else:
                unresolved.append((path.name, key, ref))
                keys_with_unresolved.add(key)  # [inferred]
        meta[key] = keep

    # Bound to the exact same window parse_legacy read metadata from. A
    # bold-key-shaped line past that window was never folded into `meta`,
    # so it must never be dropped from the body either -- and within the
    # window, only the line whose value actually won (parse_legacy keeps
    # the last match per key) is dropped; an earlier same-key line that
    # was overwritten stays in the body instead of being silently lost.
    lines = text.splitlines()
    winners = {}  # key -> index of the line whose value parse_legacy kept
    for index, raw in enumerate(lines[:adr_lib.LEGACY_HEADER_WINDOW]):
        match = adr_lib.LEGACY_RE.match(raw.strip())
        if not match:
            continue
        key = match.group(1).strip().lower().replace(" ", "_")
        winners[key] = index
    drop_indices = {index for key, index in winners.items()
                    if key not in keys_with_unresolved}

    body = "\n".join(line for index, line in enumerate(lines)
                     if index not in drop_indices)
    path.write_text("---\n" + adr_lib.dump_frontmatter(meta) + "---\n\n"
                    + body.lstrip("\n"), encoding="utf-8")
    return True, unresolved


def plan_renames(paths, id_scheme: str):
    """Compute every rename this run would perform, and refuse the whole plan
    -- writing nothing -- if any target name collides with a file that is not
    itself part of the rename. [inferred]"""
    live_names = {path.name for path in paths}
    renames = {}
    for path in paths:
        new_name = normalized_name(path.name, id_scheme)
        if new_name != path.name:
            renames[path.name] = new_name
    targets = list(renames.values())
    if len(set(targets)) != len(targets):
        return renames, "two files would rename to the same target"
    for new_name in targets:
        if new_name in live_names and new_name not in renames:
            return renames, f"rename target {new_name} already exists"
    return renames, None


def apply_renames(corpus, renames: dict) -> None:
    """Rename each file, rewrite the register's hrefs so the hand-authored
    summary survives the next regeneration, and repair every inbound
    cross-reference across the corpus."""
    register_text = None
    if corpus.register.is_file():
        register_text = corpus.register.read_text(encoding="utf-8")

    for old_name, new_name in renames.items():
        (corpus.dir / old_name).rename(corpus.dir / new_name)
        print(f"renamed: {old_name} -> {new_name}")
        if register_text is not None:
            register_text = register_text.replace(f"(./{old_name})", f"(./{new_name})")

    if register_text is not None:
        corpus.register.write_text(register_text, encoding="utf-8")

    for path in adr_lib.discover(corpus):
        text = path.read_text(encoding="utf-8")
        front, body = adr_lib.split_frontmatter(text)
        if front is None:
            continue
        adr = adr_lib.parse_adr(path, corpus.id_scheme)
        meta, touched = dict(adr.meta), False
        for key in adr_lib.LIST_KEYS:
            items = adr_lib.refs(meta, key)
            new_items = [renames.get(Path(item).name, item) for item in items]
            if new_items != items:
                meta[key], touched = new_items, True
        if touched:
            path.write_text("---\n" + adr_lib.dump_frontmatter(meta) + "---\n\n"
                            + body.lstrip("\n"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a legacy ADR corpus to frontmatter")
    parser.add_argument("--frontmatter", action="store_true",
                        help="fold bold-key headers into frontmatter (the default)")
    parser.add_argument("--rename", action="store_true",
                        help="also normalise ADR-NNN-slug.md to NNNN-slug.md")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument("--config")
    parser.add_argument("--repo-root")
    args = parser.parse_args()

    corpus = adr_lib.load_corpus(args.repo_root, args.config)
    if not corpus.dir.is_dir():
        print(f"ERROR: corpus directory {corpus.dir} does not exist", file=sys.stderr)
        return 2

    paths = list(adr_lib.discover(corpus))
    texts = {path: path.read_text(encoding="utf-8") for path in paths}
    known = {path.name for path in paths}

    renames = {}
    if args.rename:
        renames, refusal = plan_renames(paths, corpus.id_scheme)
        if refusal:
            print(f"ERROR: {refusal}", file=sys.stderr)
            return 1

    if args.dry_run:
        for path in paths:
            front, _ = adr_lib.split_frontmatter(texts[path])
            if front is None:
                print(f"fold: {path.name}")
            new_name = renames.get(path.name)
            if new_name:
                print(f"rename: {path.name} -> {new_name}")
        return 0

    for path in paths:
        changed, unresolved = fold(path, corpus, text=texts[path], known=known)
        if changed:
            print(f"folded: {path.name}")
        for filename, key, ref in unresolved:
            print(f"unresolved reference: {filename}: {key}: {ref}")

    if renames:
        apply_renames(corpus, renames)

    return 0


if __name__ == "__main__":
    sys.exit(main())
