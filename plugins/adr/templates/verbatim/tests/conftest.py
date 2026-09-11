"""Shared helpers for the vendored ADR test suite.

This file ships byte for byte into a target repo at tests/adr/conftest.py,
where the scripts live at <root>/scripts/adr/ rather than beside this
directory. Both layouts are resolved here so no test hard-codes either.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Register this conftest under a unique alias so tests can find it path-
# independently. In the plugin monorepo the plugin-side conftest sits
# beside this one and `from conftest import ...` in a test file resolves
# to whichever pytest put on sys.path first, which shadows the other
# suite whenever both collect in one run.
sys.modules.setdefault("adr_vendored_conftest", sys.modules[__name__])

HERE = Path(__file__).resolve().parent


def _find_scripts() -> Path:
    sibling = HERE.parent / "scripts"          # plugin tree
    if (sibling / "adr_lib.py").is_file():
        return sibling
    for parent in (HERE, *HERE.parents):       # target repo
        candidate = parent / "scripts" / "adr"
        if (candidate / "adr_lib.py").is_file():
            return candidate
    raise RuntimeError(f"no adr_lib.py found from {HERE}")


def _find_schemas() -> Path:
    """schemas/ sits beside scripts/ in the plugin tree (both under
    templates/verbatim/), but beside scripts/adr/ -- not inside it -- in a
    target repo, where the vendored trees are siblings at scripts/adr/,
    schemas/adr/, and tests/adr/."""
    sibling = HERE.parent / "schemas"           # plugin tree
    if (sibling / "adr.schema.json").is_file():
        return sibling
    for parent in (HERE, *HERE.parents):        # target repo
        candidate = parent / "schemas" / "adr"
        if (candidate / "adr.schema.json").is_file():
            return candidate
    raise RuntimeError(f"no adr.schema.json found from {HERE}")


SCRIPTS = _find_scripts()
SCHEMAS = _find_schemas()


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"adr_vendored_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_script(name: str, *args: str, cwd: Path = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *args],
        capture_output=True, text=True, cwd=str(cwd) if cwd else None, env=env,
    )


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def scripts_dir():
    return SCRIPTS


@pytest.fixture
def schemas_dir():
    return SCHEMAS
