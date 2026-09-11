import json
import os
import re
from pathlib import Path

import pytest
import yaml


# tests/conftest.py is one level below the plugin root, so parents[1] == plugins/relay/.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# The report template line that the built-in /verify prompt carries. It holds four verdict
# tokens, so the parser's one-token rule must reject it. Kept here because both verify-loop
# test modules assert against it, and a second copy could disagree with the first.
TEMPLATE_LINE = "**Verdict:** PASS | FAIL | BLOCKED | SKIP"


def fenced(body):
    """The child-reply protocol that `run-claude-command.sh` prints around its output.

    One definition, because the markers and the trailing rc line are a contract owned by
    that helper. A stub that spells the fence out by hand can drift from the helper and
    then the tests pass against a protocol the script no longer emits.
    """
    return "POLISH_CMD_OUTPUT_BEGIN\n" + body + "\nPOLISH_CMD_OUTPUT_END\nPOLISH_CMD_RC=0\n"


def fenced_stub(body):
    """A stub child-helper body that prints `body` inside the fence."""
    return "cat <<'EOF'\n" + fenced(body) + "EOF"


def verify_check_command():
    """The verdict contract that `verify-loop-node.sh` sends with `/verify`.

    Read from the script itself so the tests cannot assert against a copy that has drifted
    from what a run actually sends.
    """
    script = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
    m = re.search(r"check_command='(.*?)'\n", script, re.S)
    assert m, "no check_command contract found in verify-loop-node.sh"
    return m.group(1)


def deps_ok_env(tmp_path):
    """A hermetic env where `check-deps.sh` deterministically PASSES.

    Every test that runs `scripts/l3-preflight.sh` by subprocess must use this. The
    script opens with the dependency gate, which probes
    `$CLAUDE_PROJECT_DIR/.claude/plugins/superpowers/` and then `$HOME/...`. A test that
    inherits the real environment passes on a developer machine that has superpowers
    installed and fails on CI, which has none — the gate blocks first and the assertion
    reads the gate's message instead of the behavior under test.

    Build the probe file under a throwaway `CLAUDE_PROJECT_DIR`, point `HOME` at an empty
    directory so this machine's own install cannot answer, and drop every inherited
    `RELAY_*` variable so a caller's shell cannot preset the axis.
    """
    deps_root = tmp_path / "deps"
    probe = deps_root / ".claude" / "plugins" / "superpowers" / "skills" / "brainstorming"
    probe.mkdir(parents=True, exist_ok=True)
    (probe / "SKILL.md").write_text("# brainstorming\n")
    empty_home = tmp_path / "home"
    empty_home.mkdir(parents=True, exist_ok=True)
    return _relay_clean_env(str(deps_root), str(empty_home), _acpx_at_the_floor(tmp_path))


def deps_missing_env(tmp_path):
    """A hermetic env where `check-deps.sh` deterministically BLOCKS — empty
    `CLAUDE_PROJECT_DIR` and `HOME`, so no superpowers install is found."""
    empty_project = tmp_path / "no-project"
    empty_project.mkdir(parents=True, exist_ok=True)
    empty_home = tmp_path / "no-home"
    empty_home.mkdir(parents=True, exist_ok=True)
    return _relay_clean_env(
        str(empty_project), str(empty_home), _acpx_at_the_floor(tmp_path)
    )


def _acpx_at_the_floor(tmp_path):
    """A directory holding a fake `acpx` that reports exactly the shipped floor.

    `l3-preflight.sh` refuses the acpx engine when the acpx CLI is absent or below
    the floor, and acpx is the default engine for the L3 commands. Without this the
    suite passes on a developer machine that has acpx installed and fails on CI,
    which has none — the same trap the dependency probe above avoids.

    The version comes from `scripts/acpx-floor.sh`, which is the single site that
    states the floor, so a future bump does not have to touch this file.
    """
    floor = re.search(
        r"^RELAY_ACPX_MIN=(\S+)",
        (PLUGIN_ROOT / "scripts" / "acpx-floor.sh").read_text(),
        re.M,
    )
    assert floor, "no RELAY_ACPX_MIN found in scripts/acpx-floor.sh"
    binaries = tmp_path / "acpx-floor-bin"
    binaries.mkdir(parents=True, exist_ok=True)
    fake = binaries / "acpx"
    fake.write_text("#!/bin/sh\necho %s\n" % floor.group(1))
    fake.chmod(0o755)
    return binaries


def _relay_clean_env(project_dir, home, acpx_bin=None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = project_dir
    env["HOME"] = home
    if acpx_bin is not None:
        env["PATH"] = "%s:%s" % (acpx_bin, env.get("PATH", ""))
    for key in [k for k in env if k.startswith("RELAY_")]:
        del env[key]
    return env


@pytest.fixture
def plugin_root():
    return PLUGIN_ROOT


@pytest.fixture
def plugin_json():
    path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    with open(path) as f:
        return json.load(f)


def parse_frontmatter(path: Path):
    """Parse YAML frontmatter from a Markdown file. Returns (frontmatter_dict, body)."""
    content = path.read_text()
    if not content.startswith("---"):
        return {}, content
    end = content.index("---", 3)
    fm = yaml.safe_load(content[3:end])
    body = content[end + 3:].strip()
    return fm, body
