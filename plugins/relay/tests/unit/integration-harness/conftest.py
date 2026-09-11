import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
ITEST = PLUGIN_ROOT / "tests" / "integration"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Under pytest's default (prepend) import mode every conftest.py is imported under the
# bare module name `conftest`, so this nested file and the top-level tests/conftest.py
# compete for `sys.modules["conftest"]`. The `tests/unit/skill-structure/` suite does
# `from conftest import PLUGIN_ROOT, parse_frontmatter, deps_ok_env, ...`; when this file
# wins the name those imports break. Re-export the top-level conftest's public helpers so
# the shadow is harmless. Fixtures are skipped — pytest discovers those per directory, not
# through the module name, so they never need re-exporting.
_ROOT_CONFTEST = _load("_relay_root_conftest", PLUGIN_ROOT / "tests" / "conftest.py")
for _name in dir(_ROOT_CONFTEST):
    if _name.startswith("_"):
        continue
    _obj = getattr(_ROOT_CONFTEST, _name)
    if hasattr(_obj, "_pytestfixturefunction"):
        continue
    globals().setdefault(_name, _obj)


@pytest.fixture(scope="session")
def itest_conftest():
    """Load tests/integration/conftest.py as a plain module (pure helpers only)."""
    return _load("_itest_conftest", ITEST / "conftest.py")


@pytest.fixture(scope="session")
def itest_contracts():
    return _load("_itest_contracts", ITEST / "contracts.py")


@pytest.fixture(scope="session")
def plugin_root():
    return PLUGIN_ROOT


@pytest.fixture
def write_stream():
    """Factory: write a one-line stream.jsonl with a final result event under `dir`."""
    def _write(dir, text):
        p = Path(dir) / "s.jsonl"
        p.write_text(json.dumps({"type": "result", "result": text}) + "\n")
        return p
    return _write


@pytest.fixture
def git_repo():
    """Factory: build a throwaway git repo at `dir`/sb with one commit on main."""
    def _repo(dir):
        sb = Path(dir) / "sb"
        sb.mkdir()

        def g(*a):
            subprocess.run(["git", "-C", str(sb), *a], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        g("init", "-q", "-b", "main")
        (sb / "f.txt").write_text("x\n")
        g("add", "-A")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
        return sb
    return _repo


@pytest.fixture
def collect_integration():
    """Factory: run `pytest <target> -m integration --collect-only` at PLUGIN_ROOT
    with RELAY_ITEST=1 — the harness's own collection contract, shared by the
    per-tier structure tests."""
    def _collect(target, *, extra_args=()):
        env = dict(os.environ)
        env["RELAY_ITEST"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "pytest", target,
             "-m", "integration", "--collect-only", "-q", *extra_args],
            cwd=str(PLUGIN_ROOT), capture_output=True, text=True, env=env)
    return _collect
