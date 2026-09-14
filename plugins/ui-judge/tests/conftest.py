import importlib.util
import json
from pathlib import Path

import pytest
import yaml

# tests/conftest.py sits one level below the plugin root.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def load_script(name):
    """Import one of the plugin's scripts as a module, by file path.

    The scripts are standalone command line tools, not an installed package,
    so a test reaches them by path and not by name. Five test files each held
    their own copy of these four lines. One copy means that a change to how a
    script is loaded is made once, and that a sixth test file cannot quietly
    load a script a different way.
    """
    path = PLUGIN_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frontmatter(text, name="the file"):
    """Return the YAML frontmatter of a markdown file, as a dict.

    The fence check is part of the helper on purpose. Three of the four call
    sites did not make it, so a file that lost its opening fence failed with
    an IndexError that names nothing, instead of saying which file is wrong.
    """
    assert text.startswith("---\n"), f"{name} does not open with a fence"
    return yaml.safe_load(text.split("---\n", 2)[1])


@pytest.fixture
def plugin_root():
    return PLUGIN_ROOT


@pytest.fixture
def plugin_json():
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))
