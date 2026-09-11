#!/usr/bin/env python3
"""Deterministic scaffolder for the adr plugin.

Writes the corpus directory (--dir, docs/adr by default), the vendored
scripts/schemas/tests trees beside it, .claude/adr.json, and appends a
pointer block to the target repo's CLAUDE.md. This is a mechanical write
step only: it never runs adr_index.py or adr_lint.py -- those stay
explicit, separate steps run by the caller, the scaffolding-adr-corpora
skill, or this plugin's own test suite.

Write safety. If any manifest target already exists, a fresh run refuses
and writes nothing, following wiki/scripts/scaffold.py. Four exceptions,
each idempotent, are reached only via --refresh or --adopt: the repo
CLAUDE.md append (skipped when its marker is present), <dir>/CLAUDE.md,
the vendored scripts/schemas/tests trees, and the register (seeded only
when absent; adr_index.py --write owns the generated block otherwise).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PLUGIN_ROOT / "templates"
VERBATIM = TEMPLATES / "verbatim"
TOKEN_NAMES = ("DIR", "REGISTER", "TODAY")

# Repo-root-relative destinations. The vendored trees sit beside {{DIR}}, never
# inside it, so Discovery's non-recursive glob never has to exclude them.
VENDOR_DEST = {"scripts": "scripts/adr", "schemas": "schemas/adr", "tests": "tests/adr"}

VERBATIM_FILES = [
    "scripts/adr_lib.py", "scripts/adr_new.py", "scripts/adr_index.py",
    "scripts/adr_lint.py", "scripts/adr_migrate.py", "requirements.txt",
    "schemas/adr.schema.json",
    "tests/conftest.py", "tests/test_adr_lib.py", "tests/test_adr_new.py",
    "tests/test_adr_index.py", "tests/test_adr_lint.py", "tests/test_adr_migrate.py",
]
RENDERED_FILES = {"{{DIR}}/CLAUDE.md": "claude-md-corpus.md",
                  "{{DIR}}/README.md": "register-seed.md"}

DEFAULT_GATE = {"deterministic": False, "model": False, "proposed_verdict": "error"}
GATE_TEMPLATE = TEMPLATES / "gate" / "adr-gate.yml"
GATE_DEST = ".github/workflows/adr-gate.yml"
GATE_JOB_MARKERS = {
    "deterministic": ("# ADR-GATE:DETERMINISTIC:BEGIN", "# ADR-GATE:DETERMINISTIC:END"),
    "model": ("# ADR-GATE:MODEL:BEGIN", "# ADR-GATE:MODEL:END"),
}


class ScaffoldError(Exception):
    pass


def dest_for(rel: str) -> str:
    """Map a VERBATIM_FILES entry to its repo-root-relative destination.

    scripts/x -> scripts/adr/x, requirements.txt -> scripts/adr/requirements.txt,
    schemas/x -> schemas/adr/x, tests/x -> tests/adr/x.
    """
    if "/" in rel:
        top, rest = rel.split("/", 1)
        if top in VENDOR_DEST:
            return f"{VENDOR_DEST[top]}/{rest}"
        return rel
    # a bare top-level file, e.g. requirements.txt, lands beside the scripts
    return f"{VENDOR_DEST['scripts']}/{rel}"


def render(text: str, tokens: dict) -> str:
    for name, value in tokens.items():
        text = text.replace("{{" + name + "}}", value)
    return text


def normalize_dir(raw: str) -> str:
    """Repo-root-relative, never absolute, never escaping the target."""
    d = raw.strip().strip("/")
    if not d:
        raise ScaffoldError("--dir must not be empty")
    parts = [p for p in d.split("/") if p]
    if any(p in ("..", ".") for p in parts):
        raise ScaffoldError(f"--dir must not escape the target repo: {raw!r}")
    return "/".join(parts)


def manifest(dir_: str, register: str, gate: dict = None) -> list:
    """Every repo-relative path this script writes for a fresh (non-refresh,
    non-adopt) run. Includes the CI gate workflow only when the config asks
    for at least one tier, so an unrelated project's adr-gate.yml is never
    silently clobbered."""
    rows = [dest_for(rel) for rel in VERBATIM_FILES]
    rows += [dir_ + "/CLAUDE.md", register]
    rows.append(".claude/adr.json")
    if gate and (gate.get("deterministic") or gate.get("model")):
        rows.append(GATE_DEST)
    return rows


def plugin_version() -> str:
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    with open(path) as f:
        return json.load(f)["version"]


def write_config(path: Path, dir_: str, register: str, id_scheme: str, gate: dict) -> None:
    payload = {
        "version": 1,
        "dir": dir_,
        "register": register,
        "id_scheme": id_scheme,
        "gate": dict(gate),
        "archive_dir": None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_if_changed(path: Path, text: str) -> bool:
    """Write text only when it differs from what is already on disk. Returns
    True when the file was written. A file with non-UTF-8 bytes counts as
    different, so a corrupted or hand-edited file gets rewritten cleanly
    instead of raising."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except UnicodeDecodeError:
            pass
    path.write_text(text, encoding="utf-8")
    return True


def build_gate_workflow(gate: dict, tokens: dict):
    """Render adr-gate.yml with only the job(s) `gate` asks for. Returns None
    when neither tier is requested, so the caller writes nothing."""
    wanted = [name for name in ("deterministic", "model") if (gate or {}).get(name)]
    if not wanted:
        return None
    lines = render(GATE_TEMPLATE.read_text(encoding="utf-8"), tokens).splitlines()
    header_end = next(i for i, line in enumerate(lines) if line.strip() == "jobs:")
    body = []
    for name in wanted:
        begin, end = GATE_JOB_MARKERS[name]
        start = next(i for i, line in enumerate(lines) if begin in line)
        stop = next(i for i, line in enumerate(lines) if end in line)
        body.extend(lines[start:stop + 1])
    return "\n".join(lines[:header_end + 1] + body) + "\n"


def write_gate_workflow(target: Path, gate: dict, tokens: dict):
    """Write .github/workflows/adr-gate.yml when the config asks for at least
    one tier. Returns the repo-relative path when the file was written or
    changed, or None when the config asked for no tier or the file is already
    current."""
    text = build_gate_workflow(gate, tokens)
    if text is None:
        return None
    if write_if_changed(target / GATE_DEST, text):
        return GATE_DEST
    return None


def copy_vendored(target: Path) -> list:
    """Copy every VERBATIM_FILES entry whose bytes differ from what is on
    disk. Returns the list of repo-relative destinations actually written."""
    written = []
    for rel in VERBATIM_FILES:
        src = VERBATIM / rel
        dst = target / dest_for(rel)
        src_bytes = src.read_bytes()
        if dst.is_file() and dst.read_bytes() == src_bytes:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src_bytes)
        written.append(dest_for(rel))
    return written


def append_root_block(target: Path, dir_: str, register: str, tokens: dict) -> str:
    """Append the rendered root block to the repo CLAUDE.md. Skips the append
    when the rendered corpus-CLAUDE.md link -- the idempotency key -- is
    already present. Returns 'appended', 'already present', or 'wrote'
    (a fresh CLAUDE.md had to be created)."""
    claude_md_path = target / "CLAUDE.md"
    block = render((TEMPLATES / "claude-md-root-block.md").read_text(encoding="utf-8"), tokens)
    marker = f"[`{dir_}/CLAUDE.md`]({dir_}/CLAUDE.md)"
    if not claude_md_path.exists():
        claude_md_path.write_text(block, encoding="utf-8")
        return "wrote"
    existing_text = claude_md_path.read_text(encoding="utf-8")
    if marker in existing_text:
        return "already present"
    claude_md_path.write_text(existing_text.rstrip("\n") + "\n\n" + block, encoding="utf-8")
    return "appended"


def gate_flags_passed(args) -> list:
    """Return the gate flags the user explicitly passed. --refresh reads the
    gate from the config, so any of these on the command line is a conflict."""
    passed = []
    if args.gate_deterministic:
        passed.append("--gate-deterministic")
    if args.gate_model:
        passed.append("--gate-model")
    if args.proposed_verdict != "error":
        passed.append("--proposed-verdict")
    return passed


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False so `--gate-mo` is not silently accepted for --gate-model,
    # which would slip past gate_flags_passed() and get dropped in --refresh.
    parser = argparse.ArgumentParser(description="Scaffold an ADR corpus into a target repo",
                                     allow_abbrev=False)
    parser.add_argument("--target", required=True)
    parser.add_argument("--dir", default="docs/adr")
    parser.add_argument("--register")
    parser.add_argument("--id-scheme", default="sequential", choices=("sequential", "date"))
    parser.add_argument("--today")
    parser.add_argument("--adopt", action="store_true",
                        help="write config + vendored tooling, touch no existing ADR")
    parser.add_argument("--refresh", action="store_true",
                        help="idempotently refresh the four write-safety exceptions")
    parser.add_argument("--dry-run", action="store_true", help="print the manifest, write nothing")
    parser.add_argument("--gate-deterministic", action="store_true",
                        help="write the deterministic-tier CI gate job")
    parser.add_argument("--gate-model", action="store_true",
                        help="write the model-tier CI gate job")
    parser.add_argument("--proposed-verdict", default="error",
                        choices=("error", "warning", "off"),
                        help="how the gate treats an ADR still `proposed` in a changed file")
    return parser


def stage_corpus_files(target: Path, dir_: str, register: str, tokens: dict,
                       gate: dict, verb: str) -> list:
    """Copy vendored files, write the corpus CLAUDE.md, seed the register when
    absent, and render the CI gate workflow. Returns the repo-relative paths
    that were actually written this run."""
    written = copy_vendored(target)
    for rel in written:
        print(f"{verb} {rel}")

    corpus_claude_md_text = (TEMPLATES / "claude-md-corpus.md").read_text(encoding="utf-8")
    if write_if_changed(target / dir_ / "CLAUDE.md", corpus_claude_md_text):
        print(f"{verb} {dir_}/CLAUDE.md")
        written.append(f"{dir_}/CLAUDE.md")

    register_path = target / register
    if register_path.is_file():
        print(f"already present: {register}")
    else:
        register_path.parent.mkdir(parents=True, exist_ok=True)
        register_path.write_text(
            render((TEMPLATES / "register-seed.md").read_text(encoding="utf-8"), tokens),
            encoding="utf-8")
        print(f"{verb} {register}")
        written.append(register)

    gate_result = write_gate_workflow(target, gate, tokens)
    if gate_result:
        print(f"{verb} {gate_result}")
        written.append(gate_result)
    return written


def sweep_leftover_tokens(target: Path, rendered_paths) -> list:
    """The rendered rows are the only files a token can survive in -- the
    vendored files are copied byte for byte and may legitimately mention a
    token name, e.g. adr_lib.py's own docstring describing '{{DIR}}/*.md'
    Discovery."""
    leftover = []
    for rel in rendered_paths:
        path = target / rel
        if path.is_file() and "{{" in path.read_text(encoding="utf-8", errors="replace"):
            leftover.append(rel)
    return leftover


def main() -> int:
    args = build_parser().parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"ERROR: --target '{target}' is not a directory", file=sys.stderr)
        return 1

    try:
        dir_ = normalize_dir(args.dir)
    except ScaffoldError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    register = args.register or f"{dir_}/README.md"
    today = args.today

    tokens = {"DIR": dir_, "REGISTER": register, "TODAY": today or ""}
    config_path = target / ".claude" / "adr.json"
    gate = {"deterministic": args.gate_deterministic, "model": args.gate_model,
            "proposed_verdict": args.proposed_verdict}

    if args.dry_run:
        rows = manifest(dir_, register, gate)
        for rel in rows:
            print(f"  {rel}")
        print("  CLAUDE.md  (append; skipped when the marker is present)")
        print(f"{len(rows) + 1} manifest rows ({len(rows)} files + 1 append)")
        return 0

    if args.refresh:
        stray = gate_flags_passed(args)
        if stray:
            print(f"ERROR: --refresh reads the gate from .claude/adr.json; drop {', '.join(stray)}",
                  file=sys.stderr)
            return 1
        if not config_path.is_file():
            print(f"ERROR: {config_path} does not exist; run without --refresh first",
                 file=sys.stderr)
            return 1
        config = json.loads(config_path.read_text(encoding="utf-8"))
        dir_ = config["dir"]
        register = config["register"]
        tokens = {"DIR": dir_, "REGISTER": register, "TODAY": today or ""}
        stage_corpus_files(target, dir_, register, tokens, config.get("gate"), verb="refreshed")
        root_result = append_root_block(target, dir_, register, tokens)
        print(f"CLAUDE.md {root_result}")
        return 0

    if args.adopt:
        if config_path.exists():
            print(f"ERROR: {config_path} already exists; refusing to overwrite", file=sys.stderr)
            return 1
        write_config(config_path, dir_, register, args.id_scheme, gate)
        print(f"wrote {config_path.relative_to(target).as_posix()}")
        stage_corpus_files(target, dir_, register, tokens, gate, verb="wrote")
        root_result = append_root_block(target, dir_, register, tokens)
        print(f"CLAUDE.md {root_result}")
        print("adopted: no existing ADR was modified")
        return 0

    # Fresh, greenfield run.
    rows = manifest(dir_, register, gate)
    existing = [rel for rel in rows if (target / rel).exists()]
    if existing:
        print("ERROR: refusing to overwrite existing files:", file=sys.stderr)
        for rel in existing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    if not today:
        print("ERROR: --today is required for a fresh run", file=sys.stderr)
        return 1

    (target / dir_).mkdir(parents=True, exist_ok=True)
    written = stage_corpus_files(target, dir_, register, tokens, gate, verb="wrote")
    write_config(config_path, dir_, register, args.id_scheme, gate)
    print("wrote .claude/adr.json")
    written.append(".claude/adr.json")
    root_result = append_root_block(target, dir_, register, tokens)

    missing = [rel for rel in rows if not (target / rel).exists()]
    if missing:
        print("ERROR: scaffold finished but these manifest files are missing:", file=sys.stderr)
        for rel in missing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    rendered_paths = [f"{dir_}/CLAUDE.md", register, "CLAUDE.md"]
    if (target / GATE_DEST).is_file():
        rendered_paths.append(GATE_DEST)
    leftover = sweep_leftover_tokens(target, rendered_paths)
    if leftover:
        print("ERROR: unrendered '{{...}}' token survives in:", file=sys.stderr)
        for rel in leftover:
            print(f"  {rel}", file=sys.stderr)
        return 1

    print(f"CLAUDE.md {root_result}")
    print(f"{len(written)} files written, CLAUDE.md {root_result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
