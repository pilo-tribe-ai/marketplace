#!/usr/bin/env python3
"""Link, orphan, and encoding checker for an OKF bundle.

check_okf.py answers "is this bundle structurally conformant?". It reads a
link only far enough to see that one is present. This script answers the
question it deliberately leaves alone: "does every link actually resolve, is
every page reachable, and is the text plain ASCII?"

Exit 0 = clean, 1 = issues found, 2 = usage/internal error.
"""
import argparse
import json
import re
import sys
import traceback
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path

# Derived from this file's own location, so the checker works from any cwd.
DEFAULT_BUNDLE = Path(__file__).resolve().parent.parent / "bundle"

INDEX_FILE = "index.md"
LOG_FILE = "log.md"
SOURCES_DIR = "sources"
ERROR = "ERROR"
WARN = "WARN"
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
EXTERNAL_RE = re.compile(r"\A(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)


@dataclass
class Issue:
    file: str
    line: int
    level: str
    rule: str
    message: str


def bundle_key(path: Path, bundle_root: Path) -> str:
    """Canonical bundle-relative POSIX key, e.g. 'concepts/alpha.md'."""
    return path.relative_to(bundle_root).as_posix()


def check_links(text: str, path: Path, rel: str, bundle_root: Path, issues: list[Issue]) -> list[str]:
    """Append link issues for one file. Return outbound targets as bundle keys.

    Matches over the whole text, not line by line: bundle prose wraps at ~72
    characters, so a link's label routinely straddles a newline and a per-line
    scan silently misses it. Leading-slash links are rejected per schema.md §5.
    """
    resolved = []
    for m in LINK_RE.finditer(text):
        target = m.group(1)
        if target.startswith("#") or EXTERNAL_RE.match(target):
            continue
        base = target.split("#", 1)[0]
        if not base:
            continue
        lineno = text.count("\n", 0, m.start()) + 1
        if base.startswith("/"):
            issues.append(Issue(rel, lineno, ERROR, "root-absolute-link",
                                f"'{target}' resolves against the repository root, not "
                                f"the bundle; write it relative to this file "
                                f"(e.g. ../concepts/foo.md)"))
            continue
        dest = (path.parent / base).resolve()
        if not dest.is_relative_to(bundle_root):
            issues.append(Issue(rel, lineno, ERROR, "outside-bundle",
                                f"'{target}' resolves outside the bundle"))
            continue
        if not dest.exists():
            issues.append(Issue(rel, lineno, ERROR, "broken-link",
                                f"'{target}' does not resolve; the bundle has no "
                                f"'{bundle_key(dest, bundle_root)}'"))
            continue
        resolved.append(bundle_key(dest, bundle_root))
    return resolved


def check_encoding(text: str, rel: str, issues: list[Issue]):
    for lineno, line in enumerate(text.splitlines(), start=1):
        for ch in line:
            if ord(ch) > 127:
                issues.append(Issue(rel, lineno, WARN, "non-ascii",
                                    f"U+{ord(ch):04X} {unicodedata.name(ch, 'unnamed')} "
                                    f"({ch!r}); bundle prose is ASCII"))
                break


def is_narrative(path: Path) -> bool:
    """Indexes and Source pages link every page by construction, so they
    cannot rescue a page from being an orphan. Only prose counts."""
    return path.name != INDEX_FILE and path.parent.name != SOURCES_DIR


def walk_bundle(bundle_root: Path) -> tuple[list[Issue], int, int]:
    bundle_root = bundle_root.resolve()
    issues: list[Issue] = []
    pages = sorted(p for p in bundle_root.rglob("*.md"))
    inbound = {
        bundle_key(p, bundle_root): 0
        for p in pages
        if p.name not in (INDEX_FILE, LOG_FILE) and p.parent.name != SOURCES_DIR
    }
    links_checked = 0

    for path in pages:
        rel = str(path.relative_to(bundle_root.parent))
        self_ref = bundle_key(path, bundle_root)
        text = path.read_text(encoding="utf-8")
        resolved = check_links(text, path, rel, bundle_root, issues)
        links_checked += len(resolved)
        check_encoding(text, rel, issues)
        if is_narrative(path):
            for target in set(resolved):
                if target in inbound and target != self_ref:
                    inbound[target] += 1

    for target, count in sorted(inbound.items()):
        if count == 0:
            issues.append(Issue(target, 1, WARN, "orphan-page",
                                f"'{target}' has no inbound link from any page other "
                                f"than an index or a Source page"))
    return issues, len(pages), links_checked


def main() -> int:
    ap = argparse.ArgumentParser(description="Link/orphan/encoding checker for an OKF bundle")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    bundle_root = Path(args.bundle)
    if not bundle_root.is_dir():
        print(f"ERROR: bundle path '{bundle_root}' is not a directory", file=sys.stderr)
        return 2

    try:
        issues, files_checked, links_checked = walk_bundle(bundle_root)
    except Exception:
        print(f"ERROR: internal failure while checking bundle '{bundle_root}':", file=sys.stderr)
        traceback.print_exc()
        return 2

    errors = sum(1 for i in issues if i.level == ERROR)
    warnings = sum(1 for i in issues if i.level == WARN)

    if args.format == "json":
        print(json.dumps({
            "bundle": str(bundle_root),
            "files_checked": files_checked,
            "links_checked": links_checked,
            "errors": errors,
            "warnings": warnings,
            "issues": [asdict(i) for i in issues],
        }, indent=2))
    else:
        if not args.quiet:
            for i in issues:
                print(f"{i.level}: {i.file}:{i.line} [{i.rule}] {i.message}")
        print(f"{errors} errors, {warnings} warnings across {links_checked} links "
              f"in {files_checked} files")

    if errors > 0 or (args.strict and warnings > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
