#!/usr/bin/env python3
"""Deterministic scaffolder for the wiki plugin.

Writes the container skeleton (everything under the given --container path,
e.g. docs/wiki/ or wiki/) plus .claude/wiki.json, and appends a pointer
block to the target repo's CLAUDE.md. This is a mechanical write step only:
it never runs regen_indexes.py or the four verification gates. Those stay
explicit, separate commands, run by the caller -- the
scaffolding-okf-wikis skill, or this plugin's own test suite.

Never overwrites an existing page: if any manifest target already exists,
the whole run refuses and writes nothing. CLAUDE.md is the one exception --
it is appended, and the append is skipped when the marker line is already
present.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PLUGIN_ROOT / "templates"
VERBATIM = TEMPLATES / "verbatim"
RENDERED = TEMPLATES / "rendered"
CLAUDE_MD_BLOCK = TEMPLATES / "claude-md-block.md"

TOKEN_NAMES = ("CONTAINER", "SUBJECT", "REPO", "HUMAN_ACTOR", "AGENT_ACTOR", "TODAY")

TYPE_DIRS = ("sources", "entities", "concepts", "synthesis", "open-questions")

# Container-relative paths, copied byte-for-byte from templates/verbatim/.
VERBATIM_FILES = [
    "scripts/check_okf.py",
    "scripts/check_links.py",
    "scripts/regen_indexes.py",
    "requirements.txt",
    "tests/conftest.py",
    "tests/test_check_okf.py",
    "tests/test_check_links.py",
    "tests/test_regen_indexes.py",
    "tests/test_wiki_init.py",
    "tests/test_indexes_and_log.py",
    "tests/test_ingest_source.py",
    "bundle/index.md",
]

# Container-relative paths, rendered from templates/rendered/ with the six
# {{TOKEN}} placeholders substituted.
RENDERED_FILES = [
    "tests/test_agents_md.py",
    "AGENTS.md",
    "schema.md",
    "bundle/log.md",
]


class ScaffoldError(Exception):
    pass


def normalize_container(raw: str) -> str:
    """Repo-root-relative, always ends with '/', never starts with '/' or
    './'. Refuses an absolute path, a path that could escape the target,
    and the literal value 'bundle/' -- schema.md, raw/, scripts/, and
    tests/ must sit beside bundle/, never inside it (check_okf.py demands
    'type:' frontmatter on every .md under the bundle root)."""
    c = raw.strip()
    if not c:
        raise ScaffoldError("--container must not be empty")
    if c.startswith("/"):
        raise ScaffoldError(f"--container must be repo-root-relative, not absolute: {raw!r}")
    while c.startswith("./"):
        c = c[2:]
    if not c.endswith("/"):
        c = c + "/"
    parts = [p for p in c.split("/") if p]
    if not parts or any(p in ("..", ".") for p in parts):
        raise ScaffoldError(f"--container must not escape the target repo: {raw!r}")
    if c == "bundle/":
        raise ScaffoldError(
            "--container must not be 'bundle/' -- schema.md, raw/, scripts/, and "
            "tests/ must sit beside bundle/, never inside it"
        )
    return c


def render(text: str, tokens: dict[str, str]) -> str:
    for name, value in tokens.items():
        text = text.replace("{{" + name + "}}", value)
    return text


def container_manifest() -> list[str]:
    """Every container-relative path this script writes: the verbatim and
    rendered template files, raw/.gitkeep, and the five subdirectory index
    stubs -- so a freshly scaffolded bundle is fully initialized per
    AGENTS.md's Initialization operation, not left for a later step to
    finish."""
    manifest = list(VERBATIM_FILES) + list(RENDERED_FILES) + ["raw/.gitkeep"]
    manifest += [f"bundle/{name}/index.md" for name in TYPE_DIRS]
    return manifest


def plugin_version() -> str:
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    with open(path) as f:
        return json.load(f)["version"]


def write_wiki_json(path: Path, container: str) -> None:
    payload = {
        "container": container,
        "okf_version": "0.2",
        "plugin_version": plugin_version(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold an OKF v0.2 wiki into a target repo")
    ap.add_argument("--target", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--human-actor", required=True)
    ap.add_argument("--agent-actor", required=True)
    ap.add_argument("--today", required=True)
    ap.add_argument("--adopt", action="store_true", help="write .claude/wiki.json only")
    ap.add_argument("--dry-run", action="store_true", help="print the manifest, write nothing")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"ERROR: --target '{target}' is not a directory", file=sys.stderr)
        return 1

    try:
        container = normalize_container(args.container)
    except ScaffoldError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    container_root = (target / container).resolve()
    try:
        container_root.relative_to(target)
    except ValueError:
        print(f"ERROR: --container '{args.container}' escapes --target", file=sys.stderr)
        return 1

    tokens = {
        "CONTAINER": container,
        "SUBJECT": args.subject,
        "REPO": args.repo,
        "HUMAN_ACTOR": args.human_actor,
        "AGENT_ACTOR": args.agent_actor,
        "TODAY": args.today,
    }

    rel_files = container_manifest()
    full_manifest = [container + p for p in rel_files] + [".claude/wiki.json"]
    wiki_json_path = target / ".claude" / "wiki.json"
    claude_md_path = target / "CLAUDE.md"
    # Idempotency key: the container-specific AGENTS.md link. Matching the
    # link rather than surrounding prose keeps the append safe against later
    # edits to claude-md-block.md's wording.
    marker = f"[AGENTS.md](./{container}AGENTS.md)"

    if args.dry_run:
        print(f"Container: {container}")
        for rel in full_manifest:
            print(f"  {rel}")
        print("  CLAUDE.md  (append; skipped if the AGENTS.md marker is already present)")
        print(f"{len(full_manifest) + 1} manifest rows ({len(full_manifest)} files + 1 append)")
        return 0

    if args.adopt:
        if wiki_json_path.exists():
            print(f"ERROR: {wiki_json_path} already exists; refusing to overwrite", file=sys.stderr)
            return 1
        wiki_json_path.parent.mkdir(parents=True, exist_ok=True)
        write_wiki_json(wiki_json_path, container)
        print(f"adopted: wrote {wiki_json_path.relative_to(target).as_posix()}")
        return 0

    existing = [rel for rel in full_manifest if (target / rel).exists()]
    if existing:
        print("ERROR: refusing to overwrite existing files:", file=sys.stderr)
        for rel in existing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    for rel in VERBATIM_FILES:
        dst = container_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(VERBATIM / rel, dst)

    for rel in RENDERED_FILES:
        dst = container_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = render((RENDERED / rel).read_text(encoding="utf-8"), tokens)
        dst.write_text(text, encoding="utf-8")

    raw_gitkeep = container_root / "raw" / ".gitkeep"
    raw_gitkeep.parent.mkdir(parents=True, exist_ok=True)
    raw_gitkeep.write_text("", encoding="utf-8")

    for name in TYPE_DIRS:
        type_dir = container_root / "bundle" / name
        type_dir.mkdir(parents=True, exist_ok=True)
        # Empty-index stub, byte-identical to what regen_indexes.py's
        # heading_for() produces for a zero-page directory.
        heading = name.replace("-", " ").title()
        (type_dir / "index.md").write_text(f"# {heading}\n\n", encoding="utf-8")

    wiki_json_path.parent.mkdir(parents=True, exist_ok=True)
    write_wiki_json(wiki_json_path, container)

    block = render(CLAUDE_MD_BLOCK.read_text(encoding="utf-8"), tokens)
    appended = False
    if claude_md_path.exists():
        existing_text = claude_md_path.read_text(encoding="utf-8")
        if marker not in existing_text:
            # Separate the appended block by exactly one blank line, whatever
            # trailing newlines the existing file happens to end with.
            claude_md_path.write_text(existing_text.rstrip("\n") + "\n\n" + block, encoding="utf-8")
            appended = True
    else:
        claude_md_path.write_text(block, encoding="utf-8")
        appended = True

    missing = [rel for rel in full_manifest if not (target / rel).exists()]
    if missing:
        print("ERROR: scaffold finished but these manifest files are missing:", file=sys.stderr)
        for rel in missing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    leftover = []
    for rel in full_manifest:
        p = target / rel
        if p.is_file() and "{{" in p.read_text(encoding="utf-8", errors="replace"):
            leftover.append(rel)
    if "{{" in claude_md_path.read_text(encoding="utf-8"):
        leftover.append("CLAUDE.md")
    if leftover:
        print("ERROR: unrendered '{{...}}' token survives in:", file=sys.stderr)
        for rel in leftover:
            print(f"  {rel}", file=sys.stderr)
        return 1

    for rel in full_manifest:
        print(f"wrote {rel}")
    claude_note = "appended" if appended else "already up to date (marker present, not re-appended)"
    print(f"{len(full_manifest)} files written, CLAUDE.md {claude_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
