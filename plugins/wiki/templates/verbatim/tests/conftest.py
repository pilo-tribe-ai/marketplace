"""Shared test helpers for the wiki test suite."""
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import yaml

# The wiki subsystem is self-contained under the container directory (e.g.
# docs/wiki/ or wiki/). WIKI_ROOT is that directory; REPO_ROOT is the
# repository root, found by walking up from WIKI_ROOT to the nearest '.git'
# rather than assuming a fixed container depth, so this file vendors
# byte-for-byte at any container depth. Needed only for the files that stay
# at the repo root (CLAUDE.md).
WIKI_ROOT = Path(__file__).resolve().parent.parent


def _repo_root(start: Path) -> Path:
    for p in (start, *start.parents):
        # '.git' is a directory in a normal clone and a file in a git
        # worktree, so check existence, never is_dir().
        if (p / ".git").exists():
            return p
    raise RuntimeError(
        f"no .git at or above {start}: the wiki test suite needs the repository root"
    )


REPO_ROOT = _repo_root(WIKI_ROOT)
CHECKER = WIKI_ROOT / "scripts" / "check_okf.py"
WIKI = WIKI_ROOT / "bundle"

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def _list_pages(subdir: str) -> list[str]:
    return sorted(p.name for p in (WIKI / subdir).glob("*.md") if p.name != "index.md")


CONCEPT_FILES = _list_pages("concepts")
ENTITY_FILES = _list_pages("entities")
OPEN_QUESTION_FILES = _list_pages("open-questions")
SYNTHESIS_FILES = _list_pages("synthesis")
SOURCE_FILES = _list_pages("sources")

# Every value a page's `sources[].resource` may legally hold. Tests assert
# against this set rather than one hard-coded id, so a second Ingest of a
# different source does not fail the suite.
SOURCE_RESOURCES = {f"/sources/{name}" for name in SOURCE_FILES}


@lru_cache(maxsize=None)
def read_frontmatter(path: Path) -> dict:
    m = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    assert m is not None, f"{path} has no '---' frontmatter block"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), f"{path} frontmatter is not a YAML mapping"
    return data


def run_checker(bundle: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--bundle", str(bundle), *extra_args],
        capture_output=True,
        text=True,
    )
