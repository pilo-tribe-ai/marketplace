"""Registration-surface invariants for plugins/relay/agents/ (4.18.0).

Every other agent test in this suite asserts what a *source file says*. These
assert what the loader will actually *register*, which is where two shipped bugs
lived undetected from v4.0.0 (2f9cbd1) to v4.17.0:

  1. `agents/leaf-worker.md` declared `name: relay:leaf-worker`. The loader
     prefixes the plugin namespace, so it registered as `relay:relay:leaf-worker`.
     All 88 dispatch references in the plugin name `relay:leaf-worker`, which
     resolved to nothing — a hard "Agent type not found" on the path all 22 roles
     route through.

  2. `agents/README.md` carried no frontmatter but still registered, as
     `relay:README` with an unrestricted tool grant. That silently violated the
     depth-1 invariant the very same file documents: leaves withhold `Agent` and
     `Skill` so a subagent cannot spawn subagents, and `relay:README` had both.

The rule both bugs break: *the registered name is derived, not declared, and
`agents/` is a registration directory rather than a documentation directory.*
"""

import re
from pathlib import Path

import pytest

from conftest import parse_frontmatter

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = PLUGIN_ROOT / "agents"
PLUGIN_NAMESPACE = "relay"

EXPECTED_AGENT_SLUGS = {
    "analyst",
    "code-reviewer",
    "gatherer",
    "leaf-reader",
    "leaf-worker",
    "scout",
    "strategist",
}

# Directories whose markdown may reference a leaf by its registered name.
DISPATCH_REF_DIRS = ("skills", "commands", "docs", "roles")


def _agent_files():
    return sorted(AGENTS_DIR.glob("*.md"))


def registered_name(slug: str) -> str:
    """The agentType the loader exposes for `agents/<slug>.md`."""
    return f"{PLUGIN_NAMESPACE}:{slug}"


class TestAgentDirectoryIsRegistrationOnly:
    """Every file in agents/ becomes an agent. Nothing else may live there."""

    def test_agent_dir_contains_only_expected_slugs(self):
        found = {p.stem for p in _agent_files()}
        assert found == EXPECTED_AGENT_SLUGS, (
            f"agents/ must contain exactly the 7 agent files. Found: {sorted(found)}. "
            f"Every *.md in this directory registers as an agent — documentation "
            f"belongs in docs/ (see docs/agent-roster.md)."
        )

    def test_no_readme_in_agents_dir(self):
        """A README here registers as `relay:README` with all tools granted."""
        for name in ("README.md", "readme.md", "Readme.md"):
            assert not (AGENTS_DIR / name).exists(), (
                f"agents/{name} would register as an agent with an unrestricted "
                f"tool grant, breaking the depth-1 invariant. Put it in docs/."
            )

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
    def test_every_agent_file_has_frontmatter(self, path):
        """A file with no frontmatter still registers — with ALL tools."""
        fm, _ = parse_frontmatter(path)
        assert fm, (
            f"{path.name}: no YAML frontmatter. The loader still registers the file, "
            f"and an agent with no `tools:` key receives every tool."
        )
        for field in ("name", "description", "tools"):
            assert field in fm, f"{path.name}: missing required frontmatter field `{field}`"


class TestNameIsNeverSelfNamespaced:
    """`name:` is the bare slug; the loader supplies the namespace."""

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
    def test_name_has_no_colon(self, path):
        fm, _ = parse_frontmatter(path)
        name = fm.get("name", "")
        assert ":" not in name, (
            f"{path.name}: frontmatter name {name!r} contains a namespace separator. "
            f"The loader prefixes `{PLUGIN_NAMESPACE}:` itself, so this registers as "
            f"`{PLUGIN_NAMESPACE}:{name}` — a type no dispatch site references."
        )

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
    def test_name_equals_filename(self, path):
        fm, _ = parse_frontmatter(path)
        assert fm.get("name") == path.stem, (
            f"{path.name}: frontmatter name {fm.get('name')!r} must equal the filename "
            f"stem {path.stem!r} so the registered type is predictable from the path."
        )

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENT_SLUGS))
    def test_registered_name_is_single_namespaced(self, slug):
        assert registered_name(slug).count(":") == 1, (
            f"{slug}: registered agentType must carry exactly one namespace segment."
        )


class TestDispatchSitesNameRegisteredTypes:
    """The strings the plugin tells coordinators to dispatch must resolve."""

    LEAF_SLUGS = ("leaf-worker", "leaf-reader")

    @pytest.mark.parametrize("slug", LEAF_SLUGS)
    def test_docs_reference_the_registered_leaf_name(self, slug):
        """Docs say `relay:leaf-worker`; the file must therefore register as that."""
        fm, _ = parse_frontmatter(AGENTS_DIR / f"{slug}.md")
        assert registered_name(fm["name"]) == f"{PLUGIN_NAMESPACE}:{slug}", (
            f"{slug}: dispatch sites reference `{PLUGIN_NAMESPACE}:{slug}`, but this "
            f"file registers as `{registered_name(fm['name'])}`."
        )

    @pytest.mark.parametrize("slug", LEAF_SLUGS)
    def test_no_double_namespaced_refs_in_tree(self, slug):
        """Nothing should have been 'fixed' by writing the doubled form into docs."""
        doubled = f"{PLUGIN_NAMESPACE}:{PLUGIN_NAMESPACE}:{slug}"
        offenders = []
        for d in DISPATCH_REF_DIRS:
            for path in (PLUGIN_ROOT / d).rglob("*.md"):
                if doubled in path.read_text():
                    offenders.append(str(path.relative_to(PLUGIN_ROOT)))
        assert not offenders, (
            f"{doubled} appears in {offenders}. The registration is the thing to fix, "
            f"not the references."
        )

    def test_leaf_refs_exist_and_are_singly_namespaced(self):
        """Guards the fix from going vacuous: the references must still be there."""
        pattern = re.compile(rf"(?<!{PLUGIN_NAMESPACE}:)\b{PLUGIN_NAMESPACE}:leaf-(worker|reader)\b")
        hits = 0
        for d in DISPATCH_REF_DIRS:
            for path in (PLUGIN_ROOT / d).rglob("*.md"):
                hits += len(pattern.findall(path.read_text()))
        assert hits >= 10, (
            f"expected the leaf agentTypes to be referenced across dispatch docs; "
            f"found {hits}. If these were renamed, this guard must be updated too."
        )
