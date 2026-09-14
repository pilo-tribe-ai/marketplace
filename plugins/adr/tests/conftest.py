"""Shared helpers for the plugin-side adr suite. No network, no git clone."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:                       # PyYAML is optional; the vendored
    yaml = None                           # parser handles the flat subset


# Register this conftest under a unique alias so tests can find it path-
# independently. The plugin ships two conftest.py files -- plugin-side
# (this one) and vendored -- and `from conftest import ...` in a test file
# resolves to whichever pytest put on sys.path first, which shadows the
# other suite whenever both collect in one run.
sys.modules.setdefault("adr_plugin_conftest", sys.modules[__name__])

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = PLUGIN_ROOT / "scripts" / "scaffold.py"
TEMPLATES = PLUGIN_ROOT / "templates"
VERBATIM = TEMPLATES / "verbatim"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_vendored(name: str):
    return load_module(f"adr_vendored_{name}", VERBATIM / "scripts" / f"{name}.py")


def frontmatter(text: str, name: str = "the file") -> dict:
    assert text.startswith("---\n"), f"{name} does not open with a fence"
    body = text.split("---\n", 2)[1]
    if yaml is not None:
        return yaml.safe_load(body)
    return load_vendored("adr_lib").parse_simple_yaml(body)


def run_python(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, *args], capture_output=True,
                          text=True, cwd=str(cwd), env=env)


def init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    return path


@pytest.fixture
def plugin_root():
    return PLUGIN_ROOT


@pytest.fixture
def plugin_json():
    return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
