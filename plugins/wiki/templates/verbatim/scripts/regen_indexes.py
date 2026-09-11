#!/usr/bin/env python3
"""Regenerate an OKF bundle's derived indexes.

Two things in the bundle restate facts that already live in page
frontmatter: every subdirectory index.md, and each Source page's list of the
pages it fed. Hand-maintaining them is how a bundle drifts -- a page gets
added and an index does not. This script derives both from the pages.

The bundle-root index.md is hand-written (it carries okf_version and points
at directories, not pages) and is never touched. Emitted links follow the
schema.md section 5 rule: relative to the file that holds them.

Exit 0 = up to date or rewritten, 1 = --check found drift, 2 = usage error.
"""
import argparse
import re
import sys
import traceback
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

# Derived from this file's own location, so the script works from any cwd.
DEFAULT_BUNDLE = Path(__file__).resolve().parent.parent / "bundle"

INDEX_FILE = "index.md"
SOURCES_DIR = "sources"
FED_HEADING = "## Pages this source fed"
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)

# Page directories, in the order a Source page lists them.
PAGE_DIRS = ["entities", "concepts", "synthesis", "open-questions"]
HEADINGS = {
    "entities": "Entities",
    "concepts": "Concepts",
    "synthesis": "Synthesis",
    "open-questions": "Open Questions",
    "sources": "Sources",
}


def heading_for(name: str) -> str:
    return HEADINGS.get(name, name.replace("-", " ").title())


def frontmatter(path: Path) -> dict:
    m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path}: no frontmatter block")
    data = yaml.safe_load(m.group(1))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter is not a YAML mapping")
    return data


def oneline(value) -> str:
    """Collapse a folded YAML scalar to the single line an index entry needs."""
    return " ".join(str(value).split())


def pages_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.name != INDEX_FILE)


def render_index(pages: list[Path], name: str, fm: dict[Path, dict]) -> str:
    lines = [f"# {heading_for(name)}", ""]
    for page in pages:
        data = fm[page]
        entry = f"* [{oneline(data['title'])}]({page.name})"
        description = oneline(data.get("description", ""))
        lines.append(f"{entry} - {description}" if description else entry)
    return "\n".join(lines) + "\n"


def source_of(data: dict) -> str | None:
    """The Source page a page's first sources[] entry points at."""
    entries = data.get("sources") or []
    if isinstance(entries, dict):
        entries = [entries]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("resource"):
            return str(entry["resource"])
    return None


def render_source_page(source: Path, pages_by_dir: dict[str, list[Path]], fm: dict[Path, dict]) -> str:
    text = source.read_text(encoding="utf-8")
    head, sep, _ = text.partition(FED_HEADING)
    if not sep:
        head = text.rstrip() + "\n\n"
    # Frontmatter 'resource' deliberately keeps OKF's bundle-relative form --
    # it is not a rendered link. See schema.md section 5.
    self_ref = f"/{SOURCES_DIR}/{source.name}"

    body = [head.rstrip(), "", FED_HEADING, ""]
    for name in PAGE_DIRS:
        fed = [p for p in pages_by_dir.get(name, []) if source_of(fm[p]) == self_ref]
        if not fed:
            continue
        body += [f"### {heading_for(name)}", ""]
        body += [f"- [{oneline(fm[p]['title'])}](../{name}/{p.name})" for p in fed]
        body.append("")
    return "\n".join(body).rstrip() + "\n"


def intended(bundle_root: Path) -> dict[Path, str]:
    """Map every generated file to the content it should hold."""
    pages_by_dir = {name: pages_in(bundle_root / name) for name in PAGE_DIRS + [SOURCES_DIR]}
    fm = {p: frontmatter(p) for pages in pages_by_dir.values() for p in pages}
    plan = {}
    for name in PAGE_DIRS + [SOURCES_DIR]:
        if (bundle_root / name).is_dir():
            plan[bundle_root / name / INDEX_FILE] = render_index(pages_by_dir[name], name, fm)
    for source in pages_by_dir[SOURCES_DIR]:
        plan[source] = render_source_page(source, pages_by_dir, fm)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate an OKF bundle's derived indexes")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 without writing anything")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    bundle_root = Path(args.bundle)
    if not bundle_root.is_dir():
        print(f"ERROR: bundle path '{bundle_root}' is not a directory", file=sys.stderr)
        return 2

    try:
        plan = intended(bundle_root)
    except Exception:
        print(f"ERROR: internal failure while reading bundle '{bundle_root}':", file=sys.stderr)
        traceback.print_exc()
        return 2

    drifted = [p for p, content in plan.items()
               if not p.is_file() or p.read_text(encoding="utf-8") != content]

    if args.check:
        if not args.quiet:
            for p in sorted(drifted):
                print(f"DRIFT: {p} is not what the pages say it should be")
            print(f"{len(drifted)} of {len(plan)} generated files are out of date")
        return 1 if drifted else 0

    for p in sorted(drifted):
        p.write_text(plan[p], encoding="utf-8")
        if not args.quiet:
            print(f"wrote {p}")
    if not args.quiet:
        print(f"{len(drifted)} of {len(plan)} generated files rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
