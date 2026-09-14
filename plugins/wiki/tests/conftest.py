import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/conftest.py is one level below the plugin root, so parent.parent == plugins/wiki/.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = PLUGIN_ROOT / "scripts" / "scaffold.py"


def _load_scaffold_module():
    spec = importlib.util.spec_from_file_location("wiki_plugin_scaffold", SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Loaded once at import so both test modules read the real scaffold.py
# constants from here rather than hand-copying lists that could silently
# drift from it.
SCAFFOLD_MODULE = _load_scaffold_module()

TOKEN_VALUES = {
    "subject": "Throwaway acceptance subject",
    "repo": "wiki-accept",
    "human_actor": "human:pilo",
    "agent_actor": "claude-code/opus-5",
    "today": "2026-08-05",
}


@pytest.fixture
def plugin_root():
    return PLUGIN_ROOT


@pytest.fixture
def plugin_json():
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    with open(path) as f:
        return json.load(f)


def _env():
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run_python(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run `python3 <args>` in cwd, isolated from the outer pytest run's own
    cache/rootdir (-p no:cacheprovider belongs to the caller when args is a
    pytest invocation) and from bytecode caching, so no .pytest_cache or
    __pycache__ pollutes a file count taken against the scaffolded tree."""
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True, text=True, cwd=str(cwd), env=_env(),
    )


def run_scaffold(target: Path, container: str, *extra: str) -> subprocess.CompletedProcess:
    return run_python(
        target, str(SCAFFOLD),
        "--target", str(target),
        "--container", container,
        "--subject", TOKEN_VALUES["subject"],
        "--repo", TOKEN_VALUES["repo"],
        "--human-actor", TOKEN_VALUES["human_actor"],
        "--agent-actor", TOKEN_VALUES["agent_actor"],
        "--today", TOKEN_VALUES["today"],
        *extra,
    )


def init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    return path
