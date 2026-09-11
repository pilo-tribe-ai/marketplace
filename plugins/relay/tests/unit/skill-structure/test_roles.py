"""CI validators for plugins/relay/roles/*.md (spec §10)."""
import re
from pathlib import Path

import pytest
import yaml

from conftest import PLUGIN_ROOT

ROLES_DIR = PLUGIN_ROOT / "roles"

VALID_ROLE_CLASSES = {"writer", "reader"}
FORBIDDEN_ROLE_KEYS = {"name", "tools", "model"}

# The 22 role slugs that must exist
EXPECTED_ROLE_SLUGS = {
    "fix-coder", "fix-planner", "implementer", "navigator",
    "panel-member", "panel-moderator", "panel-synthesizer",
    "plan-fixer", "plan-simulator", "plan-writer", "scenario-writer",
    "server-runner", "spec-fixer", "spec-reviewer", "spec-simulator",
    "test-writer", "ui-accessibility-evaluator", "ui-code-evaluator",
    "ui-generator", "ui-ux-evaluator", "ui-visual-evaluator",
    "doc-reference-reviewer",
}

WRITER_ROLE_SLUGS = {
    "fix-coder", "fix-planner", "implementer", "navigator",
    "panel-member", "panel-moderator", "panel-synthesizer",
    "plan-fixer", "plan-writer", "scenario-writer",
    "spec-fixer", "test-writer", "ui-generator",
}

READER_ROLE_SLUGS = {
    "doc-reference-reviewer", "plan-simulator", "spec-reviewer",
    "server-runner", "spec-simulator", "ui-code-evaluator",
    "ui-visual-evaluator", "ui-ux-evaluator", "ui-accessibility-evaluator",
}

VERIFY_ARTIFACT_ROLES = {"implementer", "test-writer", "fix-coder", "plan-writer"}


def _parse_role_fm(path):
    text = path.read_text()
    if not text.startswith("---"):
        return {}, text
    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end])
    body = text[end + 3:].strip()
    return fm or {}, body


class TestRolesDirectoryExists:
    def test_roles_dir_exists(self):
        assert ROLES_DIR.is_dir(), "plugins/relay/roles/ directory missing"

    def test_all_expected_role_files_exist(self):
        missing = [s for s in EXPECTED_ROLE_SLUGS
                   if not (ROLES_DIR / f"{s}.md").is_file()]
        assert not missing, f"missing role files: {missing}"


class TestRolesFrontmatterValidity:
    """§10.1: every roles/*.md parses and carries required keys; forbidden keys absent."""

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_role_version_present(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert "role-version" in fm, f"{slug}: missing role-version"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_description_present(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert "description" in fm and fm["description"], f"{slug}: missing description"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_role_class_valid(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert fm.get("role-class") in VALID_ROLE_CLASSES, \
            f"{slug}: role-class must be 'writer' or 'reader', got {fm.get('role-class')!r}"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_output_tokens_nonempty(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        tokens = fm.get("output-tokens")
        assert isinstance(tokens, list) and tokens, f"{slug}: output-tokens must be non-empty list"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_terminal_token_in_output_tokens(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        tokens = fm.get("output-tokens") or []
        tt = fm.get("terminal_token")
        assert tt in tokens, f"{slug}: terminal_token {tt!r} must be in output-tokens {tokens}"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_no_forbidden_keys(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        found = FORBIDDEN_ROLE_KEYS & set(fm.keys())
        assert not found, f"{slug}: forbidden frontmatter keys present: {found}"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_no_relay_block(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert "relay" not in fm, f"{slug}: role files must not have a relay: block"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS))
    def test_body_nonempty(self, slug):
        _, body = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert len(body) > 50, f"{slug}: role body too short"

    @pytest.mark.parametrize("slug", sorted(WRITER_ROLE_SLUGS))
    def test_writer_class_correct(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert fm.get("role-class") == "writer", f"{slug}: expected role-class=writer"

    @pytest.mark.parametrize("slug", sorted(READER_ROLE_SLUGS))
    def test_reader_class_correct(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert fm.get("role-class") == "reader", f"{slug}: expected role-class=reader"

    @pytest.mark.parametrize("slug", sorted(VERIFY_ARTIFACT_ROLES))
    def test_verify_artifact_present_where_sourced(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        va = fm.get("verify_artifact")
        assert isinstance(va, str) and va, \
            f"{slug}: verify_artifact must be present as non-empty string"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_ROLE_SLUGS - VERIFY_ARTIFACT_ROLES))
    def test_verify_artifact_absent_elsewhere(self, slug):
        fm, _ = _parse_role_fm(ROLES_DIR / f"{slug}.md")
        assert "verify_artifact" not in fm, \
            f"{slug}: verify_artifact must be absent (not a fast-path verify role)"


class TestRolesReadmeExists:
    def test_roles_readme_exists(self):
        assert (ROLES_DIR / "README.md").is_file(), "roles/README.md missing"

    def test_roles_readme_mentions_22_roles(self):
        text = (ROLES_DIR / "README.md").read_text()
        assert "22 roles" in text or "The 22 roles" in text, \
            "roles/README.md must mention '22 roles'"

    def test_roles_readme_has_role_class_column(self):
        text = (ROLES_DIR / "README.md").read_text()
        assert "role-class" in text or "writer" in text, \
            "roles/README.md must include role-class information"


# ---------------------------------------------------------------------------
# §10.2: No de-registered agentType scan
# ---------------------------------------------------------------------------

COLLAPSED_SLUGS = {
    "doc-reference-reviewer", "fix-coder", "fix-planner", "implementer",
    "navigator", "panel-member", "panel-moderator", "panel-synthesizer",
    "plan-fixer", "plan-simulator", "plan-writer", "scenario-writer",
    "server-runner", "spec-fixer", "spec-reviewer", "spec-simulator",
    "test-writer", "ui-accessibility-evaluator", "ui-code-evaluator",
    "ui-generator", "ui-ux-evaluator", "ui-visual-evaluator",
}
# Patterns that would indicate a de-registered slug used as agentType or literal path
COLLAPSED_AGENTTYPES = {f"relay:{s}" for s in COLLAPSED_SLUGS}
COLLAPSED_AGENT_PATHS = {f"agents/{s}" for s in COLLAPSED_SLUGS}


class TestNoDeregisteredAgentType:
    """§10.2: zero hits for collapsed agentType refs in skills/commands/docs."""

    def _scan_files(self):
        scan_dirs = [
            PLUGIN_ROOT / "skills",
            PLUGIN_ROOT / "commands",
            PLUGIN_ROOT / "docs",
        ]
        for d in scan_dirs:
            for p in d.rglob("*.md"):
                try:
                    yield p, p.read_text()
                except (UnicodeDecodeError, OSError):
                    continue
            for p in d.rglob("*.sh"):
                try:
                    yield p, p.read_text()
                except (UnicodeDecodeError, OSError):
                    continue

    def test_no_collapsed_slug_as_agenttype(self):
        """No agentType= reference to a collapsed slug."""
        import re as _re
        offenders = []
        agenttype_pat = _re.compile(r"agentType\s*=\s*['\"]?(relay:\S+)['\"]?")
        for path, text in self._scan_files():
            for m in agenttype_pat.finditer(text):
                slug_ref = m.group(1).rstrip("'\")")
                if slug_ref in COLLAPSED_AGENTTYPES:
                    offenders.append((str(path.relative_to(PLUGIN_ROOT)), slug_ref))
        assert not offenders, f"collapsed agentType refs found: {offenders}"

    def test_no_collapsed_agent_path_refs(self):
        """No agents/<collapsed-slug> path references in skills/commands/docs."""
        offenders = []
        for path, text in self._scan_files():
            for agent_path in COLLAPSED_AGENT_PATHS:
                if agent_path in text:
                    offenders.append((str(path.relative_to(PLUGIN_ROOT)), agent_path))
        assert not offenders, f"collapsed agent path refs found: {offenders}"


# ---------------------------------------------------------------------------
# §10.3: Leaf tool lists exact
# ---------------------------------------------------------------------------

class TestLeafToolListsExact:
    WORKER_TOOLS = {"Read", "Write", "Edit", "Bash", "Grep", "Glob"}
    READER_TOOLS = {"Read", "Grep", "Glob", "Bash"}

    def _get_tools(self, slug):
        path = PLUGIN_ROOT / "agents" / f"{slug}.md"
        text = path.read_text()
        end = text.index("---", 3)
        fm = yaml.safe_load(text[3:end]) or {}
        raw = fm.get("tools", [])
        if isinstance(raw, list):
            return {t.strip() for t in raw}
        return {t.strip() for t in str(raw).split(",")}

    def test_leaf_worker_tools_exact(self):
        assert self._get_tools("leaf-worker") == self.WORKER_TOOLS

    def test_leaf_reader_tools_exact(self):
        assert self._get_tools("leaf-reader") == self.READER_TOOLS

    def test_leaf_worker_description_contains_do_not_invoke_directly(self):
        text = (PLUGIN_ROOT / "agents" / "leaf-worker.md").read_text()
        assert "Do not invoke directly" in text

    def test_leaf_reader_description_contains_do_not_invoke_directly(self):
        text = (PLUGIN_ROOT / "agents" / "leaf-reader.md").read_text()
        assert "Do not invoke directly" in text


# ---------------------------------------------------------------------------
# §10.4: Bindings cover every role (bijection)
# ---------------------------------------------------------------------------

class TestBindingsBijection:
    def _load_presets(self):
        return yaml.safe_load((PLUGIN_ROOT / "bindings" / "presets.yaml").read_text())

    def test_every_role_file_has_binding(self):
        presets = self._load_presets()
        roles_keys = set(presets.get("roles", {}).keys())
        role_files = {p.stem for p in ROLES_DIR.glob("*.md") if p.name != "README.md"}
        unbound = role_files - roles_keys
        assert not unbound, f"role files with no presets.yaml entry: {unbound}"

    def test_every_non_registered_binding_has_role_file(self):
        presets = self._load_presets()
        missing = []
        for slug, entry in presets.get("roles", {}).items():
            if entry.get("role-class") != "registered":
                if not (ROLES_DIR / f"{slug}.md").is_file():
                    missing.append(slug)
        assert not missing, f"bindings without role files: {missing}"

    def test_every_binding_has_role_class(self):
        presets = self._load_presets()
        missing = [s for s, e in presets.get("roles", {}).items()
                   if "role-class" not in e]
        assert not missing, f"bindings missing role-class: {missing}"

    def test_every_binding_has_model(self):
        presets = self._load_presets()
        missing = [s for s, e in presets.get("roles", {}).items()
                   if "model" not in e]
        assert not missing, f"bindings missing model: {missing}"

    def test_registered_bindings_have_explicit_agenttype(self):
        presets = self._load_presets()
        for slug, entry in presets.get("roles", {}).items():
            if entry.get("role-class") == "registered":
                assert "agentType" in entry, \
                    f"{slug}: registered binding must have explicit agentType"
                at = entry["agentType"]
                assert (PLUGIN_ROOT / "agents" / f"{at.split(':', 1)[1]}.md").is_file(), \
                    f"{slug}: agentType {at!r} does not resolve to an agent file"


# ---------------------------------------------------------------------------
# §10.5: Derivation table presence in dispatch-contract.md + both dispatch skills
# ---------------------------------------------------------------------------

class TestDerivationTablePresence:
    DERIVATION_MARKERS = ("relay:leaf-worker", "relay:leaf-reader", "role-class")

    def _check(self, path):
        text = path.read_text()
        for marker in self.DERIVATION_MARKERS:
            assert marker in text, \
                f"{path.relative_to(PLUGIN_ROOT)}: missing derivation marker {marker!r}"

    def test_dispatch_contract_has_table(self):
        self._check(PLUGIN_ROOT / "docs" / "dispatch-contract.md")

    def test_in_session_skill_has_table(self):
        self._check(PLUGIN_ROOT / "skills" / "dispatching-in-session-agents" / "SKILL.md")

    def test_acpx_skill_has_table(self):
        self._check(PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "SKILL.md")


# ---------------------------------------------------------------------------
# §10.6: Roster pin — agents/*.md set == exactly the 7 §2 slugs
# ---------------------------------------------------------------------------

class TestRosterPin:
    EXPECTED_7 = {
        "code-reviewer", "scout", "leaf-worker", "leaf-reader",
        "gatherer", "strategist", "analyst",
    }

    def test_agents_dir_has_exactly_7_agents(self):
        actual = {p.stem for p in (PLUGIN_ROOT / "agents").glob("*.md")
                  if p.name != "README.md"}
        assert actual == self.EXPECTED_7, (
            f"agents/*.md set mismatch.\n"
            f"Expected: {sorted(self.EXPECTED_7)}\n"
            f"Actual:   {sorted(actual)}"
        )
