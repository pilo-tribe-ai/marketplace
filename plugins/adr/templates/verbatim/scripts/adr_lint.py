#!/usr/bin/env python3
"""Deterministic ADR corpus lint. Standard library only, no install step.

Hand-checks the rules adr.schema.json documents -- the required keys, the
status enum, and a parseable date -- because jsonschema is a third-party
package and this tier must run in any CI with no key and no install.
"""
import argparse
import datetime as _dt
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adr_lib  # noqa: E402
import adr_index  # noqa: E402

ERROR, WARN = "ERROR", "WARN"


@dataclass
class Issue:
    level: str
    file: str
    rule: str
    message: str


def check_file(adr, issues):
    if adr.source == "legacy":
        issues.append(Issue(WARN, adr.filename, "legacy-metadata",
                            "legacy bold-key metadata; run /adr:migrate when ready"))
        return
    for key in ("status", "date"):
        if not adr.meta.get(key):
            issues.append(Issue(ERROR, adr.filename, "required-frontmatter",
                                f"frontmatter is missing `{key}`"))
    if not adr.title:
        issues.append(Issue(ERROR, adr.filename, "required-frontmatter",
                            "no `title` and no `# ` heading to fall back to"))
    if adr.status and adr.status not in adr_lib.STATUSES:
        issues.append(Issue(ERROR, adr.filename, "status-enum",
                            f"status `{adr.status}` is outside "
                            f"{', '.join(adr_lib.STATUSES)}"))
    if adr.date:
        try:
            _dt.date.fromisoformat(str(adr.date))
        except ValueError:
            issues.append(Issue(ERROR, adr.filename, "date-parse",
                                f"date `{adr.date}` is not YYYY-MM-DD"))


def lint(corpus, changed=None):
    issues = []
    adrs = [adr_lib.parse_adr(path, corpus.id_scheme) for path in adr_lib.discover(corpus)]
    for adr in adrs:
        check_file(adr, issues)
    if not adr_lib.HAVE_YAML:
        issues.append(Issue(WARN, "-", "pyyaml-absent",
                            "PyYAML is not installed; the minimal reader handles "
                            "the flat subset only"))

    seen = {}
    for adr in adrs:
        key = adr.prefix if corpus.id_scheme == "sequential" else adr.filename
        if key is None:
            continue
        if key in seen:
            issues.append(Issue(ERROR, adr.filename, "duplicate-identity",
                                f"`{key}` is already used by {seen[key]}"))
        else:
            seen[key] = adr.filename

    known = {adr.filename for adr in adrs}
    known |= {path.name for path in adr_lib.discover_archived(corpus)}
    by_name = {adr.filename: adr for adr in adrs}
    for adr in adrs:
        for key in adr_lib.LIST_KEYS:
            for ref in adr_lib.refs(adr.meta, key):
                target = Path(ref).name
                if target not in known:
                    issues.append(Issue(ERROR, adr.filename, "missing-reference",
                                        f"`{key}` names {ref}, which is not in the corpus"))
                    continue
                # A supersede link is checked from both sides. A names B in
                # `superseded_by`, so B must name A in `supersedes`, and the
                # reverse, or the link is one-sided.
                mirror = {"superseded_by": "supersedes",
                          "supersedes": "superseded_by"}.get(key)
                if mirror:
                    other = by_name.get(target)
                    if other and adr.filename not in [
                            Path(name).name for name in adr_lib.refs(other.meta, mirror)]:
                        issues.append(Issue(ERROR, adr.filename, "one-sided-supersede",
                                            f"{target} does not name this file in `{mirror}`"))
        replaced_by = adr_lib.refs(adr.meta, "superseded_by")
        if adr.status == "superseded" and not replaced_by:
            issues.append(Issue(ERROR, adr.filename, "supersede-pairing",
                                "status is `superseded` with no `superseded_by`"))
        if replaced_by and adr.status != "superseded":
            issues.append(Issue(ERROR, adr.filename, "supersede-pairing",
                                "`superseded_by` is set but status is not `superseded`"))

    current = corpus.register.read_text(encoding="utf-8") if corpus.register.is_file() else ""
    try:
        summaries, unparsed = adr_index.read_rows(current)
        fresh = adr_index.build_block(corpus, summaries, unparsed, adrs=adrs)
        if adr_index.block_of(current) != fresh:
            issues.append(Issue(ERROR, corpus.register.name, "register-stale",
                                "the register is stale; run /adr:index"))
    except adr_index.DuplicateRow as duplicate:
        issues.append(Issue(ERROR, corpus.register.name, "register-duplicate-row",
                            f"two rows are keyed to {duplicate}"))

    if changed is not None:
        verdict = (corpus.config["gate"] or {}).get("proposed_verdict", "error")
        if verdict != "off":
            names = {Path(name).name for name in changed}
            for adr in adrs:
                if adr.filename in names and adr.status == "proposed":
                    issues.append(Issue(ERROR if verdict == "error" else WARN,
                                        adr.filename, "still-proposed",
                                        "this ADR is still `proposed` in a changed file"))

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint the ADR corpus")
    parser.add_argument("--changed", nargs="*", default=None)
    parser.add_argument("--config")
    parser.add_argument("--repo-root")
    args = parser.parse_args()
    corpus = adr_lib.load_corpus(args.repo_root, args.config)
    if not corpus.dir.is_dir():
        print(f"ERROR: corpus directory {corpus.dir} does not exist", file=sys.stderr)
        return 2
    issues = lint(corpus, args.changed)
    for issue in issues:
        print(f"{issue.level}: {issue.file}: {issue.rule}: {issue.message}")
    errors = sum(1 for issue in issues if issue.level == ERROR)
    print(f"{errors} error(s), {len(issues) - errors} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
