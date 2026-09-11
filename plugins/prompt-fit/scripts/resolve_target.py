#!/usr/bin/env python3
"""Turn one target into the exact list of prompt files to review, with each file's role.

A target is a single file, a skill folder, a plugin folder, a project that holds
a .claude folder, or any other folder. The list this prints is the whole scope
of a review. Nothing is dropped in silence: a target that resolves to no file,
or to more files than the cap, ends the run and says so.

Exit codes:
  0  at least one file was found
  2  the path is missing, the target holds no prompt file, or the count is over the cap
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROMPT_SUFFIXES = {".md", ".mdx", ".txt", ".prompt"}

# Documentation about a plugin, not a prompt inside it.
SKIPPED_NAMES = {
    "readme.md",
    "changelog.md",
    "license.md",
    "license",
    "contributing.md",
    "code_of_conduct.md",
    # .txt is a prompt suffix, and these three carry no prompt.
    "requirements.txt",
    "robots.txt",
    "license.txt",
}

SKIPPED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "site-packages",
    ".pytest_cache",
    ".mypy_cache",
}

# A review over more files than this is too broad to act on in one pass. The run
# stops rather than reviewing the first hundred and reporting success.
FILE_CAP = 100


class ResolveError(Exception):
    """A target that cannot be turned into a file list."""


def role_of(path: Path, root: Path) -> str:
    """Name what the file is for, from where it sits."""
    name = path.name.lower()
    parts = [part.lower() for part in path.parts]

    if name == "skill.md":
        return "skill"
    if name in ("claude.md", "agents.md", "gemini.md", "memory.md"):
        return "memory"
    if "commands" in parts:
        return "command"
    if "agents" in parts:
        return "agent"
    if "skills" in parts:
        return "skill-reference"
    if "templates" in parts:
        return "template"
    if "reference" in parts or "references" in parts:
        return "skill-reference"
    return "prompt"


def is_prompt_file(path: Path) -> bool:
    if path.suffix.lower() not in PROMPT_SUFFIXES:
        return False
    if path.name.lower() in SKIPPED_NAMES:
        return False
    return not any(part in SKIPPED_DIRS for part in path.parts)


def walk(root: Path) -> list[Path]:
    found = [item for item in sorted(root.rglob("*")) if item.is_file() and is_prompt_file(item)]
    return found


def kind_of(path: Path) -> str:
    if path.is_file():
        return "file"
    if (path / ".claude-plugin" / "plugin.json").is_file():
        return "plugin"
    if (path / "SKILL.md").is_file():
        return "skill"
    if (path / ".claude").is_dir() or (path / "CLAUDE.md").is_file():
        return "project"
    return "directory"


def collect(path: Path, kind: str) -> list[Path]:
    """Return the prompt files that belong to a target of this kind."""
    if kind == "file":
        return [path]

    if kind == "plugin":
        found: list[Path] = []
        for folder in ("commands", "agents", "skills", "reference", "references", "templates"):
            sub = path / folder
            if sub.is_dir():
                found.extend(walk(sub))
        for name in ("CLAUDE.md", "AGENTS.md"):
            item = path / name
            if item.is_file():
                found.append(item)
        return sorted(set(found))

    if kind == "project":
        found = []
        for name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            item = path / name
            if item.is_file():
                found.append(item)
        claude = path / ".claude"
        if claude.is_dir():
            for folder in ("commands", "agents", "skills"):
                sub = claude / folder
                if sub.is_dir():
                    found.extend(walk(sub))
        return sorted(set(found))

    return walk(path)


def git_states(paths: list[Path]) -> dict[str, str]:
    """Map each path to tracked-clean, tracked-dirty, untracked, or not-in-git."""
    if not paths:
        return {}
    anchor = paths[0].parent
    try:
        top = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return {str(item): "not-in-git" for item in paths}
    if top.returncode != 0:
        return {str(item): "not-in-git" for item in paths}

    root = Path(top.stdout.strip())
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    tracked_set = {
        (root / item).resolve() for item in tracked.stdout.split("\0") if item
    }
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = set()
    for entry in status.stdout.split("\0"):
        if len(entry) > 3:
            dirty.add((root / entry[3:]).resolve())

    out = {}
    for item in paths:
        resolved = item.resolve()
        if resolved not in tracked_set:
            out[str(item)] = "untracked"
        elif resolved in dirty:
            out[str(item)] = "tracked-dirty"
        else:
            out[str(item)] = "tracked-clean"
    return out


def resolve(target: str) -> dict:
    path = Path(target)
    if not path.exists():
        raise ResolveError(f"{target} does not exist")

    kind = kind_of(path)
    files = collect(path, kind)
    if not files:
        raise ResolveError(
            f"{target} is a {kind} and holds no prompt file "
            f"(looked for {', '.join(sorted(PROMPT_SUFFIXES))})"
        )
    if len(files) > FILE_CAP:
        raise ResolveError(
            f"{target} holds {len(files)} prompt files, over the cap of {FILE_CAP}. "
            "Name a folder inside it, so that no file is reviewed in silence."
        )

    states = git_states(files)
    return {
        "target": target,
        "kind": kind,
        "count": len(files),
        "files": [
            {
                "path": str(item),
                "role": role_of(item, path),
                "git": states.get(str(item), "not-in-git"),
            }
            for item in files
        ],
    }


def render(result: dict) -> str:
    out = [f"{result['target']}  ({result['kind']}, {result['count']} files)", ""]
    out.append(f"  {'role':<16}{'git':<16}path")
    for item in result["files"]:
        out.append(f"  {item['role']:<16}{item['git']:<16}{item['path']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the prompt files that make up one review target.",
    )
    parser.add_argument("target", help="a file, a skill folder, a plugin folder, or a project")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)

    try:
        result = resolve(args.target)
    except ResolveError as error:
        print(str(error), file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
