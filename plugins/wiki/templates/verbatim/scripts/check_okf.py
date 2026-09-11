#!/usr/bin/env python3
"""OKF v0.2 conformance checker for wiki/.

Validates OKF section 11's three conformance rules against every markdown
file in a bundle:
  1. Every non-reserved .md file has a parseable YAML frontmatter block.
  2. Every such frontmatter block has a non-empty 'type' field.
  3. Every index.md / log.md follows OKF 8/9 structure when present.

Exit 0 = conformant, 1 = non-conformant, 2 = usage/internal error.
"""
import argparse
import json
import re
import sys
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

# Derived from this file's own location, so the checker works from any cwd.
DEFAULT_BUNDLE = Path(__file__).resolve().parent.parent / "bundle"

INDEX_FILE = "index.md"
LOG_FILE = "log.md"
RESERVED = {INDEX_FILE, LOG_FILE}
VALID_STATUSES = ("draft", "stable", "deprecated")
ERROR = "ERROR"
WARN = "WARN"
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
DATE_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$")
HEADING_RE = re.compile(r"^#{1,6}\s+\S")
LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*)$")
LIST_ITEM_LINK_RE = re.compile(r"\[.+?\]\(.+?\)")


@dataclass
class Issue:
    file: str
    line: int
    level: str
    rule: str
    message: str


def split_frontmatter(text: str):
    """Return (frontmatter_str_or_None, body, body_offset). body_offset is the
    byte offset in `text` where body starts (0 if no frontmatter)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text, 0
    return m.group(1), text[m.end():], m.end()


def parse_frontmatter_mapping(fm_text: str, rel: str, issues: list[Issue]):
    """Parse fm_text into a dict. Appends ERROR issues and returns None on
    parse failure or non-mapping so callers can skip downstream key checks."""
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        issues.append(Issue(rel, 1, ERROR, "unparseable-frontmatter", str(e)))
        return None
    if not isinstance(data, dict):
        issues.append(Issue(rel, 1, ERROR, "frontmatter-not-a-mapping",
                             "frontmatter must be a YAML mapping"))
        return None
    return data


def check_page_file(path: Path, rel: str, issues: list[Issue]):
    text = path.read_text(encoding="utf-8")
    fm_text, _, _ = split_frontmatter(text)
    if fm_text is None:
        issues.append(Issue(rel, 1, ERROR, "missing-frontmatter",
                             "file does not start with a '---' frontmatter block"))
        return
    data = parse_frontmatter_mapping(fm_text, rel, issues)
    if data is None:
        return
    type_val = data.get("type")
    if type_val is None or not str(type_val).strip():
        issues.append(Issue(rel, 1, ERROR, "missing-type",
                             "frontmatter has no non-empty 'type' field"))

    if "sources" in data:
        srcs = data["sources"]
        srcs = [srcs] if isinstance(srcs, dict) else (srcs or [])
        for i, s in enumerate(srcs):
            if not isinstance(s, dict) or not s.get("resource"):
                issues.append(Issue(rel, 1, WARN, "sources-missing-resource",
                                     f"sources[{i}] has no 'resource'"))
    if str(type_val).strip() == "Source" and not data.get("resource"):
        issues.append(Issue(rel, 1, WARN, "source-missing-resource",
                             "type: Source page has no 'resource' field"))
    if "generated" in data:
        gen = data["generated"]
        if not isinstance(gen, dict) or not gen.get("by"):
            issues.append(Issue(rel, 1, WARN, "generated-missing-by",
                                 "'generated' present but missing required 'by'"))
    if "status" in data and data["status"] not in VALID_STATUSES:
        issues.append(Issue(rel, 1, WARN, "status-invalid",
                             f"'status: {data['status']}' not one of "
                             f"{'|'.join(VALID_STATUSES)}"))


def check_index_file(path: Path, rel: str, is_bundle_root: bool, issues: list[Issue]):
    text = path.read_text(encoding="utf-8")
    fm_text, body, body_offset = split_frontmatter(text)
    matched = fm_text is not None

    if matched and not is_bundle_root:
        issues.append(Issue(rel, 1, ERROR, "index-frontmatter-not-root",
                             "index.md frontmatter is only permitted at bundle root"))
    elif matched and is_bundle_root:
        data = parse_frontmatter_mapping(fm_text, rel, issues)
        if data is not None:
            extra = set(data.keys()) - {"okf_version"}
            if extra:
                issues.append(Issue(rel, 1, ERROR, "index-frontmatter-extra-keys",
                                     f"bundle-root index.md frontmatter may only "
                                     f"contain 'okf_version', found: {sorted(extra)}"))
            if not data.get("okf_version"):
                issues.append(Issue(rel, 1, WARN, "missing-okf-version",
                                     "bundle-root index.md has no 'okf_version'"))
    elif is_bundle_root:
        issues.append(Issue(rel, 1, WARN, "missing-okf-version",
                             "bundle-root index.md has no frontmatter, so no "
                             "'okf_version' is declared"))

    body_lines = body.splitlines()
    if not any(HEADING_RE.match(line) for line in body_lines):
        issues.append(Issue(rel, 1, ERROR, "index-no-headings",
                             "index.md has no section headings"))
    line_offset = text.count("\n", 0, body_offset)
    for lineno, line in enumerate(body_lines, start=1):
        m = LIST_ITEM_RE.match(line)
        if m and not LIST_ITEM_LINK_RE.search(m.group(1)):
            issues.append(Issue(rel, lineno + line_offset, WARN, "index-item-no-link",
                                 "list item has no markdown link"))


def check_log_file(path: Path, rel: str, issues: list[Issue]):
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("---"):
        issues.append(Issue(rel, 1, ERROR, "log-has-frontmatter",
                             "log.md must not contain a frontmatter block"))
    dates = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            m = DATE_HEADING_RE.match(line)
            if not m:
                issues.append(Issue(rel, lineno, ERROR, "log-bad-date-heading",
                                     f"heading '{line}' is not '## YYYY-MM-DD'"))
            else:
                dates.append((lineno, m.group(1)))
    for (_, a), (_, b) in zip(dates, dates[1:]):
        if a < b:
            issues.append(Issue(rel, 1, ERROR, "log-not-newest-first",
                                 f"date heading '{a}' appears before '{b}' "
                                 f"(log.md must be newest-first)"))
            break


def walk_bundle(bundle_root: Path) -> tuple[list[Issue], int]:
    issues: list[Issue] = []
    files_checked = 0
    for path in sorted(bundle_root.rglob("*.md")):
        files_checked += 1
        rel = str(path.relative_to(bundle_root.parent))
        name = path.name
        if name not in RESERVED:
            check_page_file(path, rel, issues)
        elif name == INDEX_FILE:
            check_index_file(path, rel, path.parent == bundle_root, issues)
        else:  # name == LOG_FILE
            if path.parent != bundle_root:
                issues.append(Issue(rel, 1, WARN, "log-below-root",
                                     "this bundle uses a single bundle-root log.md; "
                                     "a log.md elsewhere is unexpected"))
            check_log_file(path, rel, issues)
    return issues, files_checked


def main() -> int:
    ap = argparse.ArgumentParser(description="OKF v0.2 conformance checker")
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
        issues, files_checked = walk_bundle(bundle_root)
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
            "errors": errors,
            "warnings": warnings,
            "issues": [asdict(i) for i in issues],
        }, indent=2))
    else:
        if not args.quiet:
            for i in issues:
                print(f"{i.level}: {i.file}:{i.line} [{i.rule}] {i.message}")
        print(f"{errors} errors, {warnings} warnings across {files_checked} files")

    if errors > 0 or (args.strict and warnings > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
