import re

from conftest import PLUGIN_ROOT, parse_frontmatter

SETUP = PLUGIN_ROOT / "commands" / "setup.md"


class TestSetupCommand:
    def test_exists(self):
        assert SETUP.is_file()

    def test_has_description_and_arg_hint(self):
        fm, _ = parse_frontmatter(SETUP)
        assert fm.get("description")
        assert "argument-hint" in fm

    def test_sources_parser_with_all_positionals(self):
        _, body = parse_frontmatter(SETUP)
        assert "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh" in body
        assert re.search(r'parse-engine-agent\.sh"\s+"\$@"', body)
        assert '"$1" "$2"' not in body

    def test_dispatches_setting_up_relay(self):
        _, body = parse_frontmatter(SETUP)
        assert "relay:setting-up-relay" in body

    def test_does_not_fatally_gate_on_check_deps(self):
        # setup PROVISIONS deps, so it must not abort on their absence
        _, body = parse_frontmatter(SETUP)
        assert not re.search(r'check-deps\.sh"\s*\|\|\s*exit 1', body)

    def test_no_spec_path_and_no_stale_refs(self):
        _, body = parse_frontmatter(SETUP)
        assert "RELAY_ALLOW_SPEC_PATH" not in body
        assert "roles/" not in body
        # forbidden stale ref (split to avoid triggering the tree-wide literal guard)
        _stale = "end-to-end" + "-implementation"
        assert _stale not in body

    def test_allowed_tools_declared(self):
        # CMD-1: setup sources bash and invokes the setting-up-relay skill, so it
        # must declare allowed-tools containing Bash and Skill. Kept bespoke here
        # (not in COMMANDS) so setup's non-fatal check-deps pattern is never pulled
        # into TestCommands::test_sources_check_deps.
        fm, _ = parse_frontmatter(SETUP)
        allowed = str(fm.get("allowed-tools", ""))
        assert allowed, "commands/setup.md: allowed-tools must be declared"
        assert "Bash" in allowed, "commands/setup.md: allowed-tools must include Bash"
        assert "Skill" in allowed, "commands/setup.md: allowed-tools must include Skill"

    def test_description_drops_version_number(self):
        # CMD-4: soften the description from "acpx >=0.7.0 preflight" to "acpx
        # preflight"; the concrete floor stays single-sourced in setting-up-relay.
        fm, _ = parse_frontmatter(SETUP)
        desc = str(fm.get("description", ""))
        assert "0.7.0" not in desc, (
            "commands/setup.md: description must not pin a version number (CMD-4)"
        )
        assert "acpx preflight" in desc, (
            "commands/setup.md: description must soften to 'acpx preflight'"
        )
