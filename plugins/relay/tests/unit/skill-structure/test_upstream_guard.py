import re

from conftest import PLUGIN_ROOT

MANIFEST = PLUGIN_ROOT / "scripts" / "upstream-superpowers-skills.txt"
SUPERPOWERS_REF = re.compile(r"superpowers:([a-z][a-z0-9-]*)")
# only files UNDER the plugin are in scope (spec §7): the repo-root docs/superpowers tree
# is not under PLUGIN_ROOT and is never reached.
SCAN_DIRS = ("skills", "commands", "agents", "scripts", "bindings", "tests", "docs")


def obra_skill_set():
    names = set()
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "obra/superpowers":
            names.add(parts[0])
    return names


def _scan_files():
    for path in PLUGIN_ROOT.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        rel = path.relative_to(PLUGIN_ROOT)
        if not rel.parts or rel.parts[0] not in SCAN_DIRS:
            continue
        if rel.parts[:2] == ("tests", "e2e") and "runs" in rel.parts:
            continue
        if "__pycache__" in rel.parts:
            continue
        # Test files legitimately quote fork-only `superpowers:<name>` tokens inside
        # absence-assertions (e.g. `assert "superpowers:verify-spec" not in body`);
        # those are not relay references. relay ships no production .py under
        # PLUGIN_ROOT, so skipping .py loses no production coverage. [inferred]
        if rel.suffix == ".py":
            continue
        try:
            yield rel, path.read_text()
        except (UnicodeDecodeError, OSError):
            continue


class TestUpstreamCompatibilityGuard:
    def test_manifest_shipped_with_14_obra_skills(self):
        assert MANIFEST.is_file(), "shared upstream manifest must ship"
        assert len(obra_skill_set()) == 14

    def test_only_upstream_superpowers_skills_referenced(self):
        allowed = obra_skill_set()
        offenders = set()
        for rel, text in _scan_files():
            for name in set(SUPERPOWERS_REF.findall(text)):
                if name not in allowed:
                    offenders.add((str(rel), name))
        assert not offenders, f"fork-only superpowers:<name> references: {sorted(offenders)}"
