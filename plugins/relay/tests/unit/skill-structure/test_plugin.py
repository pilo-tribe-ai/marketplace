import re
import subprocess
from pathlib import Path

import pytest

from conftest import PLUGIN_ROOT, parse_frontmatter


class TestCheckDepsScript:
    SCRIPT = PLUGIN_ROOT / "scripts" / "check-deps.sh"

    def test_file_exists(self):
        assert self.SCRIPT.is_file()

    def test_file_readable(self):
        # readable (and conventionally executable); at minimum we can read it
        assert self.SCRIPT.read_text()

    def test_uses_return_not_bare_exit(self):
        body = self.SCRIPT.read_text()
        assert "return 1" in body
        assert "return 0" in body
        # no bare top-level `exit 1` (it would kill the parent shell when sourced)
        assert "\nexit 1" not in body

    def test_discovery_probes_present(self):
        body = self.SCRIPT.read_text()
        assert "CLAUDE_PROJECT_DIR" in body
        assert "$HOME/.claude/plugins" in body
        assert "find" in body
        assert "claude plugin list" in body

    def test_blocking_marker_present(self):
        body = self.SCRIPT.read_text()
        assert "[relay] BLOCKING:" in body

    def test_install_hint_references_marketplace(self):
        body = self.SCRIPT.read_text()
        assert "obra/superpowers-marketplace" in body

    def test_cache_probe_handles_version_subdir(self):
        body = self.SCRIPT.read_text()
        # cache-hit path must not be version-naive: accept a versioned layout
        # (<hit>/<version>/skills/...) as well as the flat layout.
        assert ("/*/skills/" in body) or ('"$_relay_cache"/*/' in body)


class TestParseEngineAgent:
    SCRIPT = PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh"
    BEHAVIOR = PLUGIN_ROOT / "tests" / "unit" / "skill-structure" / "test_parse_engine_agent.sh"

    def test_file_exists(self):
        assert self.SCRIPT.is_file()

    def test_lowercases_inputs(self):
        body = self.SCRIPT.read_text()
        assert "tr '[:upper:]' '[:lower:]'" in body

    def test_declares_engine_enum(self):
        body = self.SCRIPT.read_text()
        assert "in-session" in body
        assert "acpx" in body

    def test_declares_agent_enum(self):
        body = self.SCRIPT.read_text()
        assert "claude" in body
        assert "codex" in body
        assert "opencode" in body

    def test_exports_env_vars(self):
        body = self.SCRIPT.read_text()
        assert "RELAY_ENGINE" in body
        assert "RELAY_AGENT" in body

    def test_enforces_invariant(self):
        body = self.SCRIPT.read_text()
        # in-session ⇒ claude: body references both in-session and a RELAY_AGENT mismatch path
        assert "in-session" in body
        assert "RELAY_AGENT" in body

    def test_uses_return_not_exit(self):
        body = self.SCRIPT.read_text()
        assert "return 1" in body
        assert "\nexit 1" not in body

    def test_behavioral_bash_suite(self):
        assert self.BEHAVIOR.is_file()
        result = subprocess.run(["bash", str(self.BEHAVIOR)], capture_output=True, text=True)
        assert result.returncode == 0, f"behavioral suite failed:\n{result.stdout}\n{result.stderr}"


class TestPluginJson:
    def test_file_exists(self):
        assert (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").is_file()

    def test_required_fields(self, plugin_json):
        for field in ("name", "version", "description", "author", "license", "keywords"):
            assert field in plugin_json, f"missing required field: {field}"

    def test_name_is_relay(self, plugin_json):
        assert plugin_json["name"] == "relay"

    def test_has_display_name(self, plugin_json):
        assert "displayName" in plugin_json, "plugin.json must have displayName field"
        assert plugin_json["displayName"] == "Relay", "plugin.json displayName must be 'Relay'"

    def test_license_is_mit(self, plugin_json):
        assert plugin_json["license"] == "MIT"

    def test_author_is_object(self, plugin_json):
        author = plugin_json["author"]
        assert isinstance(author, dict)
        assert "name" in author
        assert "email" in author

    def test_keywords_non_empty_list(self, plugin_json):
        keywords = plugin_json["keywords"]
        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_version_is_at_least_3_1_0(self, plugin_json):
        from packaging.version import Version
        assert Version(plugin_json["version"]) >= Version("3.1.0"), (
            f"plugin.json version must be >= 3.1.0; got {plugin_json['version']!r}"
        )


class TestPluginVersion140:
    """Task 10 — version bump for the UI-refinement feature. The UI feature was
    authored on the older coordinator architecture as a 1.4.0 bump, but it landed
    on the engine 'L3' line; after the merge the canonical version is the engine
    series (>= 3.2.0, which carries this UI-refinement change)."""

    def test_version_is_140(self, plugin_json):
        from packaging.version import Version
        assert Version(plugin_json["version"]) >= Version("3.2.0"), (
            f"plugin.json version must carry the UI-refinement bump (>= 3.2.0), "
            f"got {plugin_json['version']!r}"
        )


class TestVersion4110:
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_plugin_json_version_is_4110(self, plugin_json):
        # Superseded exact pin: 4.12.0 carries this line forward (TestVersion4120
        # owns the current exact pin).
        from packaging.version import Version
        assert Version(plugin_json["version"]) >= Version("4.11.0")

    def test_changelog_has_4100_engine_axis_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.10.0", "--engine", "--agent", "/relay:refine",
            "/relay:execute", "/relay:drive", "delegate-and-watch",
            "code-reviewer", "doc-reference-reviewer", "server-runner",
        ):
            assert token in body, f"CHANGELOG 4.10.0 entry missing {token!r}"

    def test_changelog_has_4110_ui_axis_fix_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.11.0", "refining-ui", "ui-generator", "ui-code-evaluator",
            "$ARGUMENTS", "ui-visual-evaluator",
        ):
            assert token in body, f"CHANGELOG 4.11.0 entry missing {token!r}"


CMD_NAMES = ("implement", "refine", "execute", "drive")
# Every command that GENERATES a Workflow must carry the Tier note. diagnose does,
# but it has no axis Step 0 (no --engine/--agent, no RELAY_* echo), so it belongs to
# this list only — never to CMD_NAMES, whose tests assert the axis machinery.
TIER_CMD_NAMES = CMD_NAMES + ("diagnose",)

# Sections whose prose is allowed to name a tier, keyed by command. Before 4.24.0 the
# polish leaves were pinned-tier wrapper nodes deliberately exempt from resolve-tier.sh,
# and that section legitimately spelled out a model in commands/implement.md. 4.24.0
# moved the loop mechanics — and the pinned-tier prose that goes with them — into
# skills/verifying-until-clean/SKILL.md, so commands/implement.md now names no model
# tier at all and needs no row here. Kept as an empty dict, not deleted, so the next
# exemption is one more row rather than one more branch inside the parametrized test
# below.
_TIER_PROSE_EXEMPT_SECTION = {}


def _generating_body(name):
    """The Workflow-generation prose for a command. 4.38.0 moved implement's to
    skills/running-implement-spine/SKILL.md."""
    if name == "implement":
        return (PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md").read_text()
    return (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()


class TestVersion4120:
    """Relay 4.12.0 — layered axis resolution, in-session tiers, cost harness (spec §8)."""

    SCRIPT = PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh"
    WT_SCRIPT = PLUGIN_ROOT / "scripts" / "worktree-preflight.sh"
    CMDS = [PLUGIN_ROOT / "commands" / f"{n}.md" for n in CMD_NAMES]
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    # --- §8.1: parse-engine-agent.sh body guards ---

    def test_parse_engine_agent_reads_relay_json(self):
        body = self.SCRIPT.read_text()
        for token in (
            "relay.json",
            "RELAY_AXIS_SOURCE",
            "RELAY_IN_SESSION_TIERS",
            "in_session_tiers",
            "(from .claude/relay.json pin)",
        ):
            assert token in body, f"parse-engine-agent.sh missing {token!r}"

    def test_parse_engine_agent_failure_messages(self):
        body = self.SCRIPT.read_text()
        assert "jq is required to read .claude/relay.json" in body
        assert ".claude/relay.json is not valid JSON" in body
        assert "in_session_tiers must be a boolean in .claude/relay.json" in body
        assert "came from .claude/relay.json" in body  # invariant hint template

    def test_parse_engine_agent_still_sourcing_safe(self):
        body = self.SCRIPT.read_text()
        assert "return 1" in body
        assert "\nexit 1" not in body  # bare top-level exit would kill the sourcing shell

    # --- §1.2 [inferred]: Step 0 / Step 0.5 report missing jq identically ---

    def test_worktree_preflight_jq_missing_contract_aligned(self):
        assert "jq is required to read .claude/relay.json" in self.WT_SCRIPT.read_text()

    # --- §8.3: command-file format + Step 0.25 guards (new tests; nothing asserted
    # the old "resolved dispatch axis" prefix — verified zero matches in tests/) ---

    @pytest.mark.parametrize("name", CMD_NAMES)
    def test_command_new_axis_echo(self, name):
        """Issue #110: the axis echo line moved into scripts/l3-preflight.sh,
        shared by all four commands; each command body now only calls it."""
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/scripts/l3-preflight.sh" {name} "$ARGUMENTS"' in body
        assert "resolved dispatch axis" not in body
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert "[relay] dispatch axis: engine=$RELAY_ENGINE agent=$RELAY_AGENT" in script
        assert "(source: $RELAY_AXIS_SOURCE)" in script

    @pytest.mark.parametrize("name", CMD_NAMES)
    def test_command_step_025_ask_when_unpinned(self, name):
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        assert "Step 0.25" in body
        assert "AskUserQuestion" in body
        assert "No dispatch engine is pinned for this repo" in body
        assert "(source: default)" in body  # trigger keys on source printed as exactly default
        assert "acpx (hybrid)" in body
        # honest re-echo after an answered question — the literal echo moved into
        # scripts/l3-preflight.sh's --axis-only mode; the command body calls it.
        assert "--axis-only acpx hybrid --source prompt" in body
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert "(source: $_ao_source)" in script
        # 4.47.0: the `(default)` label follows the command's own default engine.
        if name == "implement":
            assert "acpx (default)" in body
            assert "in-session (claude)" in body
        else:
            assert "in-session (default)" in body

    @pytest.mark.parametrize("name", CMD_NAMES)
    def test_command_headless_skip_in_025_and_05(self, name):
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        # verbatim sentence fragment appears in BOTH Step 0.25 and the Step 0.5 gate text
        assert body.count("cannot present an interactive question") >= 2, (
            f"{name}.md must carry the headless-skip sentence in Step 0.25 AND Step 0.5"
        )

    def test_drive_resume_echo_and_resume_skip(self):
        body = (PLUGIN_ROOT / "commands" / "drive.md").read_text()
        assert "resume=1" in body  # Step 0.25 resume-skip condition
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert "resume=$_resume (source: $RELAY_AXIS_SOURCE)" in script

    def test_refining_skill_prose_updated(self):
        body = (PLUGIN_ROOT / "skills" / "refining" / "SKILL.md").read_text()
        assert "resolved dispatch axis" not in body

    # --- §8.4: flat tier fields on every presets.yaml role ---

    # `inherit` = omit opts.model so the node takes the session model (4.14.0).
    # `fable` is deliberately absent: pinning the frontier by name goes stale every
    # release, so top-tier roles use `inherit` and follow whatever the session runs.
    FLAT_MODEL_ENUM = {"haiku", "sonnet", "opus", "inherit"}
    FLAT_EFFORT_ENUM = {"low", "medium", "high", "xhigh"}
    NEVER_DOWNSHIFT = ("plan-writer", "spec-simulator", "panel-moderator")

    def test_every_role_has_flat_model_and_effort(self):
        roles = _load_presets()["roles"]
        assert len(roles) == 24, f"expected 24 roles, found {len(roles)}"
        bad = []
        for slug, entry in roles.items():
            if entry.get("model") not in self.FLAT_MODEL_ENUM:
                bad.append(f"{slug}: model={entry.get('model')!r}")
            if entry.get("effort") not in self.FLAT_EFFORT_ENUM:
                bad.append(f"{slug}: effort={entry.get('effort')!r}")
        assert not bad, f"flat tier violations: {bad}"

    def test_never_downshift_roles_are_inherit(self):
        """4.14.0: never-downshift stopped being a hardcoded exception list repeated in
        each command body and became a tier value. These roles must resolve to `inherit`
        so a stronger session model actually reaches them."""
        roles = _load_presets()["roles"]
        for slug in self.NEVER_DOWNSHIFT:
            assert roles[slug]["model"] == "inherit", (
                f"{slug} is a never-downshift role and must carry model: inherit"
            )

    def test_every_tier_rung_is_used(self):
        """The ladder regressed to 21-sonnet/3-opus once before, which made the gate
        pointless. Assert all four rungs carry at least one role."""
        models = {v["model"] for v in _load_presets()["roles"].values()}
        assert models == self.FLAT_MODEL_ENUM, (
            f"every tier rung must be used; unused: {self.FLAT_MODEL_ENUM - models}"
        )

    def test_presets_header_documents_tier_source(self):
        text = PRESETS_PATH.read_text()
        assert "in_session_tiers" in text
        assert "resolve-tier.sh" in text, "header must point at the single resolution site"
        for rung in self.FLAT_MODEL_ENUM:
            assert rung in text, f"header must document the '{rung}' rung"

    # --- §8.3 (Tier note): every generating command routes tier choice through the
    # resolver instead of restating the ladder in prose ---

    @pytest.mark.parametrize("name", TIER_CMD_NAMES)
    def test_command_tier_note(self, name):
        body = _generating_body(name)
        assert "Tier note" in body, f"{name}.md missing the Tier note paragraph"
        assert "resolve-tier.sh" in body, (
            f"{name}.md must call the resolver, not hand-derive the ladder"
        )
        assert "model=inherit" in body, f"{name}.md must document the inherit row"
        assert "OMIT `opts.model`" in body

    @pytest.mark.parametrize("name", TIER_CMD_NAMES)
    def test_command_tier_note_does_not_restate_the_ladder(self, name):
        """The whole point of the resolver is one resolution site. A command body that
        names individual roles' tiers has started drifting from presets.yaml again."""
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        for slug in self.NEVER_DOWNSHIFT:
            assert slug not in body, (
                f"{name}.md hardcodes the never-downshift role {slug}; that is now data "
                "in presets.yaml (model: inherit), resolved by resolve-tier.sh"
            )

    def test_diagnose_can_actually_run_the_resolver(self):
        """diagnose.md carried agent() nodes but no Bash, so it could never resolve a
        tier — the gap the 4.12.0 CMD_NAMES tuple hid."""
        fm, _ = parse_frontmatter(PLUGIN_ROOT / "commands" / "diagnose.md")
        assert "Bash" in fm.get("allowed-tools", ""), (
            "diagnose.md needs Bash in allowed-tools to run resolve-tier.sh"
        )

    # --- §8.6: in-session dispatch SKILL states the corrected tier-source split ---

    def test_in_session_skill_tier_source_wording(self):
        body = (
            PLUGIN_ROOT / "skills" / "dispatching-in-session-agents" / "SKILL.md"
        ).read_text()
        assert "in_session_tiers" in body
        assert "downshift" in body
        # the old claim — modalities.claude as the in-session model/effort source — is gone
        assert "come from the binding's `modalities.claude` block" not in body

    # --- §8.7: version bump + CHANGELOG entry ---

    def test_plugin_version_4120(self):
        # Superseded exact pin: 4.13.0 carries this line forward (TestVersion4130
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.12.0")

    def test_changelog_has_4120_entry(self):
        assert "## 4.12.0" in self.CHANGELOG.read_text()


class TestVersion4130:
    """Relay 4.13.0 — simulator repo-grounding, findings read-back, refine in-place."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_plugin_version_4130(self):
        # Superseded exact pin: 4.14.0 carries this line forward (TestVersion4140
        # owns the current exact pin). Same relaxed idiom as TestVersion4120.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.13.0")

    def test_changelog_has_4130_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.13.0", "UNVERIFIED:", "run_bash", "Executable Claims",
            "FINDINGS_PATH", "{{FINDINGS}}",
        ):
            assert token in body, f"CHANGELOG 4.13.0 entry missing {token!r}"


class TestVersion4140:
    """Relay 4.14.0 — in-session tiers ON by default, the `inherit` rung, and
    scripts/resolve-tier.sh as the single tier resolution site."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    RESOLVER = PLUGIN_ROOT / "scripts" / "resolve-tier.sh"
    SUITE = PLUGIN_ROOT / "tests" / "unit" / "skill-structure" / "test_resolve_tier.sh"

    def test_plugin_version_4140(self):
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.14.0")

    def test_changelog_has_4140_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.14.0", "in_session_tiers", "inherit", "resolve-tier.sh",
        ):
            assert token in body, f"CHANGELOG 4.14.0 entry missing {token!r}"

    def test_resolver_exists_and_is_executable(self):
        assert self.RESOLVER.is_file(), "scripts/resolve-tier.sh missing"
        assert os.access(self.RESOLVER, os.X_OK), "resolve-tier.sh must be executable"

    def test_behavioral_bash_suite(self):
        """Actually run the resolver's behavioral suite — a mode-bit check alone would
        leave its gate matrix and readers-agree loop decorative in CI."""
        result = subprocess.run(["bash", str(self.SUITE)], capture_output=True, text=True)
        assert result.returncode == 0, (
            f"resolve-tier suite failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tiers_default_on(self):
        """The 4.12.0 default was OFF, which made the whole tier table inert."""
        body = (PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh").read_text()
        assert '_relay_tiers="1"' in body, "in-session tiers must default ON"
        assert 'jq -r \'.in_session_tiers\'' in body, (
            "the gate must read the key directly — a `//` default cannot distinguish "
            "an absent key from a literal false and would ignore the opt-out"
        )

    def test_resolver_handles_the_inherit_rung(self):
        body = self.RESOLVER.read_text()
        assert "inherit" in body
        assert "OMIT" in body.upper()

    # --- the watcher pin: delegate-and-watch outer nodes run sonnet/low ---

    def test_resolver_pins_the_watcher_node_kind(self):
        """The delegate-and-watch outer agent() node is role-independent (launch, wait,
        classify, route), so it takes one pinned pair — sonnet/low — instead of 24
        presets.yaml rows. Before this pin it silently inherited the session model,
        putting the frontier model on the one node whose context grows O(turns)."""
        body = self.RESOLVER.read_text()
        assert '_rt_watcher_model="sonnet"' in body
        assert '_rt_watcher_effort="low"' in body
        assert "watcher)" in body, "resolver must answer `resolve-tier.sh watcher`"

    def test_watcher_pin_is_not_a_presets_role(self):
        assert "watcher" not in _load_presets()["roles"], (
            "the watcher is a node-kind constant in resolve-tier.sh, not a role row"
        )

    @pytest.mark.parametrize("name", TIER_CMD_NAMES)
    def test_command_tier_note_routes_watcher_through_resolver(self, name):
        """Commands must point delegated nodes at the resolver's watcher line, not
        restate a tier in prose (one resolution site — same rule as the ladder).
        `inherit` is exempt: the Tier note legitimately documents the inherit row."""
        body = _generating_body(name)
        exempt_section = _TIER_PROSE_EXEMPT_SECTION.get(name)
        if exempt_section:
            body = re.sub(
                r"\n%s.*?(?=\n## |\Z)" % re.escape(exempt_section),
                "\n",
                body,
                flags=re.S,
            )
        # 4.46.0: scan the BODY only. `argument-hint` is a CLI enum, not tier prose —
        # `--fixes-model sonnet|opus|fable` names the values the flag accepts, and no
        # role's tier. The rule this test guards is about prose that restates the
        # ladder, so the frontmatter is out of its reach.
        body = re.sub(r"\A---\n.*?\n---\n", "", body, flags=re.S)
        assert "outer watcher" in body, f"{name}.md missing the watcher pin note"
        for rung in ("sonnet", "haiku", "opus"):
            assert rung not in body, (
                f"{name}.md restates a tier ({rung!r}); tiers must come from "
                "resolve-tier.sh"
            )

    def test_delegate_and_watch_skill_documents_the_pin(self):
        body = (
            PLUGIN_ROOT / "skills" / "delegate-and-watch" / "SKILL.md"
        ).read_text()
        assert "## Watcher tier" in body
        assert "model=sonnet effort=low" in body
        assert "in_session_tiers" in body, "the pin must honor the same gate"

    def test_skill_watcher_pin_matches_resolver_constants(self):
        """Cross-link the SKILL.md prose to the resolver's actual constants: without
        this, retuning the pin updates the resolver and its direct asserts while the
        skill's hardcoded literal stays green and stale."""
        body = self.RESOLVER.read_text()
        model = re.search(r'_rt_watcher_model="([a-z]+)"', body).group(1)
        effort = re.search(r'_rt_watcher_effort="([a-z-]+)"', body).group(1)
        skill = (
            PLUGIN_ROOT / "skills" / "delegate-and-watch" / "SKILL.md"
        ).read_text()
        assert f"model={model} effort={effort}" in skill, (
            "delegate-and-watch/SKILL.md must document the pin resolve-tier.sh "
            "actually prints"
        )

    def test_opus_and_haiku_rung_membership(self):
        """Pin the re-curated rung membership (the inherit trio already has its own
        test): the sets are documented in selecting-the-right-model's Layer-1 table
        and the CHANGELOG's 7/2/12/3 census — update those alongside any change here.
        4.46.0 re-cut these two rungs along the `category` split: every verification
        role is opus, every fixes role is sonnet."""
        roles = _load_presets()["roles"]
        by_model = {}
        for slug, entry in roles.items():
            by_model.setdefault(entry["model"], set()).add(slug)
        assert by_model["opus"] == {
            "spec-reviewer", "code-reviewer", "doc-reference-reviewer",
            "ui-visual-evaluator", "ui-ux-evaluator",
            "ui-accessibility-evaluator", "ui-code-evaluator",
        }
        assert by_model["haiku"] == {"server-runner", "navigator"}
        assert len(by_model["sonnet"]) == 12


class TestVersion4150:
    """Relay 4.15.0 — /relay:implement polish phase."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_plugin_version_4150(self):
        # Superseded exact pin: 4.16.0 carries this line forward (TestVersion4160
        # owns the current exact pin). Same relaxed idiom as TestVersion4130.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.15.0")

    def test_changelog_has_4150_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.15.0",
            "run-claude-command.sh",
            "polish-simplify",
            "polish-review",
            "/code-review max --fix",
            "No availability gate",
        ):
            assert token in body, f"CHANGELOG 4.15.0 entry missing {token!r}"


class TestVersion4320:
    """Relay 4.32.0 — `/relay:verify` takes `--engine` and defaults to `in-session`,
    so the approvals-off consent question now runs only under `--engine acpx`.

    The question added in 4.25.0 was a patch on a substrate choice. Every step ran as
    an `acpx --approve-all` child session, which is what the auto-mode rule
    `Create Unsafe Agents` refuses. Remove the child process and the rule has nothing
    to match. The substrate choice rested on one sentence that 4.30.0 had already
    contradicted.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.32.0")[1].split("## 4.31.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_the_entry_leads_with_the_default_and_the_removed_question(self):
        entry = self._entry()
        assert "defaults to `in-session`" in entry
        assert "only under `--engine acpx`" in entry

    @pytest.mark.parametrize(
        "token",
        [
            "--phase pre",
            "--phase post",
            "failed:no-reply",
            "failed:no-pre",
            "parse-engine-agent.sh",
            "has no verify-loop substrate",
            "test_verify_loop_in_session.py",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_entry_states_the_evidence_gap_it_accepts(self):
        """A claimed run is weaker than a started run. An entry that shipped this
        engine without saying so would hide the one real cost of the change."""
        entry = self._entry()
        assert "claimed run is weaker evidence than a started run" in entry
        assert "only `--engine acpx` removes that possibility" in entry

    def test_the_entry_states_the_acpx_path_did_not_change(self):
        entry = self._entry()
        assert "byte-identical" in entry
        assert "run_child" in entry

    def test_the_new_test_module_exists(self):
        """The entry claims a module. A claim of coverage with no file behind it is
        the failure this repo checks for most."""
        assert (
            PLUGIN_ROOT
            / "tests"
            / "unit"
            / "skill-structure"
            / "test_verify_loop_in_session.py"
        ).is_file()

    def test_the_design_spec_the_entry_cites_exists(self):
        assert (
            PLUGIN_ROOT
            / "docs"
            / "superpowers"
            / "specs"
            / "2026-08-20-relay-verify-engine-flag-design.md"
        ).is_file()


class TestVersion4310:
    """Relay 4.31.0 — two new dispatch engines built on Claude Code background
    sessions and cross-session messages: `--engine bg-sessions` for per-leaf
    dispatch, and `--engine session-tree`, the second documented exception to
    relay's one-Workflow doctrine.

    Built in the fixed order the design spec requires: contract (bg-launch.sh,
    bg-liveness.sh, docs/bg-dispatch-contract.md) -> bg-sessions
    (dispatching-bg-agents) -> session-tree (orchestrating-session-trees,
    bg-manifest.sh).
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.31.0")[1].split("## 4.30.0")[0]
        return re.sub(r"\s+", " ", body)

    @pytest.mark.parametrize(
        "token",
        [
            "bg-sessions",
            "session-tree",
            "LAUNCH_DENIED",
            "RELAY_BG_STALE_SECONDS",
            "provisional",
        ],
    )
    def test_changelog_has_4310_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.31.0 entry missing {token!r}"

    @pytest.mark.parametrize(
        "script",
        ["bg-launch.sh", "bg-liveness.sh", "bg-manifest.sh"],
    )
    def test_new_scripts_are_executable(self, script):
        import os

        path = PLUGIN_ROOT / "scripts" / script
        assert path.is_file(), f"{script} must be shipped"
        assert os.access(path, os.X_OK), f"{script} must be executable"


class TestVersion4300:
    """Relay 4.30.0 — the model can invoke /relay:implement and /relay:verify.

    All eight relay commands set `disable-model-invocation: true`, so only a human
    could start them. That blocked useful automation: an agent that plans a change
    could not hand the build to the implement pipeline, and an agent that lands a
    branch could not start the verify loop. Both commands drop the flag; the other
    six keep it.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.30.0")[1].split("## 4.29.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4300(self):
        # Superseded by 4.31.0, so this floors the version rather than pinning it
        # (the newest version class owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.30.0")

    @pytest.mark.parametrize(
        "token",
        [
            "disable-model-invocation",
            "SlashCommand",
            "implement.md",
            "verify.md",
            "No body change",
        ],
    )
    def test_changelog_has_4300_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.30.0 entry missing {token!r}"

    @pytest.mark.parametrize("command", ["implement", "verify"])
    def test_command_is_model_invocable(self, command):
        body = (PLUGIN_ROOT / "commands" / f"{command}.md").read_text()
        assert "disable-model-invocation" not in body

    @pytest.mark.parametrize(
        "command", ["diagnose", "drive", "engines", "execute", "refine", "setup"]
    )
    def test_other_commands_stay_human_started(self, command):
        body = (PLUGIN_ROOT / "commands" / f"{command}.md").read_text()
        assert "disable-model-invocation: true" in body


class TestVersion4290:
    """Relay 4.29.0 — the verify loop states the verdict line it needs, stops
    retrying a format it cannot change, and holds one deadline for the whole node.

    Run `wf_918a4deb-aba` spent three full rounds and verified nothing: the check
    node sent a bare `/verify`, the child's reply held no verdict token, the
    deterministic mismatch was retried anyway, and the retry pushed the node past
    the caller's 600-second ceiling. All three rounds reported `CHECK=missing`.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.29.0")[1].split("## 4.28.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4290(self):
        # Superseded exact pin: 4.30.0 carries this line forward (TestVersion4300
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.29.0")

    @pytest.mark.parametrize(
        "token",
        [
            "wf_918a4deb-aba",
            "no-verdict-line",
            "no-output-fence",
            "deadline",
            "CHECK=missing",
        ],
    )
    def test_changelog_has_4290_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.29.0 entry missing {token!r}"

    def test_changelog_says_the_guard_is_untouched(self):
        assert "untouched" in self._entry()

    def test_changelog_says_why_the_contract_uses_the_enum(self):
        assert "would have been read as a real pass" in self._entry()


class TestVersion4280:
    """Relay 4.28.0 — a loop node relays its status line instead of describing it.

    The status line sat above 25 to 40 lines of child output, so nodes summarised the
    block. Run wf_8ad76eec-5ac returned invented detail values, one the literal word
    `placeholder`, and reported `ran` for a step that had run nothing. The records were
    correct throughout, so the verdict stayed honest — the defect was in the layer that
    described the run, not the layer that decided it.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.28.0")[1].split("## 4.27.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4280(self):
        # Superseded exact pin: 4.29.0 carries this line forward (TestVersion4290
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.28.0")

    @pytest.mark.parametrize(
        "token",
        [
            "NODE_STATUS=absent",
            "verbatim",
            "placeholder",
            "wf_8ad76eec-5ac",
            "verify-loop-report",
        ],
    )
    def test_changelog_has_4280_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.28.0 entry missing {token!r}"

    def test_changelog_says_a_backgrounded_command_is_not_ran(self):
        assert "None of them is" in self._entry()

    def test_changelog_calls_this_a_reduction_not_a_removal(self):
        """A node can still mis-state a line it can plainly read. Claiming the defect
        is gone would invite dropping the tests that keep it rare."""
        body = self._entry()
        assert "reduction, not a removal" in body

    def test_changelog_says_the_records_stayed_correct(self):
        """The verdict was never wrong. An entry implying otherwise would misdescribe
        the fail-closed design that did hold."""
        assert "records on disk were correct" in self._entry()


class TestVersion4270:
    """Relay 4.27.0 — the verify loop gets a wall-clock budget.

    A node runs as one Bash call, and that call stops after two minutes by default. A
    round takes far longer, so run wf_8ad76eec-5ac lost 9 of its 12 steps: the child was
    killed before the script wrote its record, and each round directory held one 12-byte
    record. The loop reported `unverified`, so fail-closed held, but it named no cause.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.27.0")[1].split("## 4.26.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4270(self):
        # Superseded exact pin: 4.28.0 carries this line forward (TestVersion4280
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.27.0")

    @pytest.mark.parametrize(
        "token",
        [
            "600000",
            "RELAY_VERIFY_NODE_TIMEOUT",
            "failed:timeout",
            "wf_8ad76eec-5ac",
            "unverified",
        ],
    )
    def test_changelog_has_4270_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.27.0 entry missing {token!r}"

    def test_changelog_says_a_timeout_is_not_a_pass(self):
        """The whole value of the change is an honest record. An entry that presented
        it as a reliability tweak would invite folding it back into `skipped`."""
        body = self._entry()
        assert "not a skip" in body
        assert "never a pass" in body

    def test_changelog_says_why_the_budget_sits_below_the_ceiling(self):
        """Raise it above the caller's ceiling and the caller wins the race again, so
        no `failed:timeout` is ever written and the change silently does nothing."""
        assert "below the caller's ceiling" in self._entry()

    def test_changelog_says_the_helper_contracts_are_untouched(self):
        body = self._entry()
        assert "run-claude-command.sh" in body
        assert "untouched" in body

    def test_the_script_sets_a_default_budget(self):
        """A changelog entry naming a variable the script does not read is a lie the
        version pin would otherwise carry forward."""
        script = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        assert "RELAY_VERIFY_NODE_TIMEOUT" in script


class TestVersion4260:
    """Relay 4.26.0 — the verify-loop node bodies move into a script.

    A worktree-isolated session refused every inline node body; run wf_ddc51fb5-461
    lost 13 of 14 nodes and verified nothing. The refusal does not require `git`, so
    no inline shape could be rewritten toward — the bodies had to move.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.26.0")[1].split("## 4.25.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4260(self):
        # Superseded exact pin: 4.27.0 carries this line forward (TestVersion4270
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.26.0")

    @pytest.mark.parametrize(
        "token",
        [
            "verify-loop-node.sh",
            "test_verify_loop_node.py",
            "RELAY_WT_WORKTREE_ROOT",
            "wf_ddc51fb5-461",
            "EnterWorktree",
        ],
    )
    def test_changelog_has_4260_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.26.0 entry missing {token!r}"

    def test_changelog_says_why_no_inline_shape_would_work(self):
        """Without this, the next editor tries to rewrite the inline bash instead of
        moving it, and rediscovers the same wall."""
        body = self._entry()
        assert "does not need `git` to be present" in body or (
            "does not need" in body and "command substitution is refused" in body
        )

    def test_changelog_states_the_static_check_consequence(self):
        """The move has a real visibility cost. The entry must name it rather than
        presenting the change as purely a cleanup."""
        body = self._entry()
        assert "does not read this script" in body
        assert "scoped with `-C`" in body

    def test_changelog_says_the_helper_contracts_are_untouched(self):
        body = self._entry()
        assert "run-claude-command.sh" in body
        assert "untouched" in body

    def test_the_node_script_ships(self):
        """A changelog entry naming a script that does not exist is a lie the
        version pin would otherwise carry forward."""
        assert (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").is_file()


class TestVersion4250:
    """Relay 4.25.0 — the verify loop asks for agreement before it generates a node.

    Claude Code's auto-mode rule `Create Unsafe Agents` refused 2 of 13 loop nodes in
    run wf_55ed608d-904, because every leaf runs `acpx --approve-all` and a bare slash
    command never met the rule's consent bar. The release adds the question, and splits
    the state reset into a node that starts no child agent so one refusal cannot end a
    whole run.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.25.0")[1].split("## 4.24.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4250(self):
        # Superseded exact pin: 4.26.0 carries this line forward (TestVersion4260
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.25.0")

    @pytest.mark.parametrize(
        "token",
        [
            "BREAKING",
            "Create Unsafe Agents",
            "--approve-all",
            "verify-init",
            "failed:no-state",
            "RELAY_VERIFY_MISSING",
            "unverified",
        ],
    )
    def test_changelog_has_4250_entry(self, token):
        assert token in self._entry(), f"CHANGELOG 4.25.0 entry missing {token!r}"

    def test_changelog_states_the_consent_is_real(self):
        """The entry must not read as a way around a check. A reader who takes it
        that way will 'improve' the question into evasion at the next edit."""
        body = self._entry()
        assert "consent that did not exist before, not wording aimed at the classifier" in body
        assert "Do not write it to get past the check." in body

    def test_changelog_records_the_single_point_of_failure(self):
        """The reset move is the half of the release that survives even if the
        question does not clear the rule."""
        body = self._entry()
        assert "single point of failure" in body
        assert "starts no child agent" in body

    def test_changelog_says_the_helper_contracts_are_untouched(self):
        """The locked contract in test_relay_implement_polish.py. If a later change
        does touch it, this line has to change with it."""
        body = self._entry()
        assert "run-claude-command.sh" in body
        assert "untouched" in body


class TestVersion4240:
    """Relay 4.24.0 — /relay:implement ends with the same verify-until-clean loop as
    /relay:verify, both sharing the loop mechanics through one L2 skill. Breaking:
    a machine with no acpx now ends the run unverified instead of successful."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.24.0")[1].split("## 4.23.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4240(self):
        # Superseded exact pin: 4.25.0 carries this line forward (TestVersion4250
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.24.0")

    def test_changelog_has_4240_entry(self):
        body = self._entry()
        for token in (
            "BREAKING",
            "/relay:implement",
            "verifying-until-clean",
            "--verify",
            "polish-simplify",
            "polish-review",
            "--rounds",
            "RELAY_VERIFY_RESULT",
            "unverified (acpx unavailable)",
        ):
            assert token in body, f"CHANGELOG 4.24.0 entry missing {token!r}"

    def test_changelog_states_the_equivalence_contract(self):
        """The whole point of the release. A reader who misses this reads `--verify`
        as a convenience flag rather than as the guarantee it is."""
        body = self._entry()
        assert "exactly equivalent" in body
        assert "followed by `/relay:verify`" in body

    def test_changelog_warns_that_a_bare_run_does_no_cleanup(self):
        """The breaking change that hits the DEFAULT path. Anyone upgrading who never
        types `--verify` silently loses the simplify and code-review passes that
        4.23.0 always ran."""
        body = self._entry()
        assert "A bare run does no cleanup" in body

    def test_changelog_records_why_the_posture_changed(self):
        body = self._entry()
        assert "drift" in body.lower(), (
            "the 4.24.0 entry must say why the mechanics moved into one skill: a "
            "third copy would drift, as TestBlockedRetryRouteAgrees already proved "
            "across two"
        )
        assert "acpx" in body.lower(), (
            "the 4.24.0 entry must say why the release is breaking: a machine with "
            "no acpx now ends the run unverified instead of successful"
        )


class TestVersion4230:
    """Relay 4.23.0 — /relay:drive classifies the task kind like every other L3 command."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    DRIVE = PLUGIN_ROOT / "commands" / "drive.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.23.0")[1].split("## 4.22.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4230(self):
        # Superseded exact pin: 4.24.0 carries this line forward (TestVersion4240
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.23.0")

    def test_drive_has_classifier_and_branch_steps(self):
        text = self.DRIVE.read_text()
        assert "## Step 1 — Classify the task kind" in text
        assert "## Step 2 — Select the policy (branch on kind)" in text
        assert "classifying-task-kind" in text

    def test_drive_classifies_the_oracle_not_an_empty_string(self):
        """Step 0 sets RELAY_DRIVE_ORACLE to `$ARGUMENTS` minus the parsed flags, and
        drive's argument-hint is those flags plus `<oracle-file>` — it takes no free
        task text. So `$ARGUMENTS` minus the flags minus the oracle path is the empty
        string on every run. The four sibling L3 commands can classify `$ARGUMENTS`
        because each carries free task text; drive must read the oracle document
        instead, or the classifier returns a kind inferred from nothing."""
        text = self.DRIVE.read_text()
        step1 = text.split("## Step 1 — Classify the task kind")[1].split("## Step 2")[0]
        assert "RELAY_DRIVE_ORACLE" in step1, (
            "drive Step 1 must name the oracle file as the classifier's input"
        )
        assert not re.search(
            r"`relay:classifying-task-kind`\s+over\s+`\$ARGUMENTS`", step1
        ), (
            "drive Step 1 must classify the oracle's contents, not `$ARGUMENTS` — "
            "`$ARGUMENTS` holds only the flags and the oracle path"
        )

    def test_drive_keeps_the_pinned_later_headings(self):
        """Inserting the classifier must not shift Step 3.5 / 4, which are pinned
        across all five commands by the retro and completeness-gate suites."""
        text = self.DRIVE.read_text()
        for heading in (
            "## Step 3 — Generate one Workflow",
            "## Step 3.5 — Record run intent",
            "## Step 4 — Verify run completeness",
        ):
            assert heading in text, f"drive.md missing {heading!r}"

    def test_drive_kind_is_advisory_not_spine_altering(self):
        """The oracle still decides done; the kind only biases the soft zone."""
        flat = re.sub(r"\s+", " ", self.DRIVE.read_text())
        assert "advisory" in flat.lower()
        assert "never removes or reorders the hard spine" in flat

    def test_l3_checks_covers_exactly_the_five_l3_commands(self):
        """The 4.23.0 changelog promises this tripwire by name: L3_CHECKS covers
        exactly the five L3 commands and every filename in it exists on disk, so a
        sixth command cannot be added and silently skipped — the same omission shape
        as the drive.md gap this release closes. Without it the hand-maintained map
        has no guardrail."""
        import importlib.util

        _v = PLUGIN_ROOT / "scripts" / "validate_l3_command.py"
        s = importlib.util.spec_from_file_location("vl3_cov", _v)
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        cmd_root = PLUGIN_ROOT / "commands"
        assert set(m.L3_CHECKS) == {
            "implement.md",
            "refine.md",
            "execute.md",
            "drive.md",
            "diagnose.md",
        }, f"L3_CHECKS must list exactly the five L3 commands, got {sorted(m.L3_CHECKS)}"
        for fname in m.L3_CHECKS:
            assert (cmd_root / fname).exists(), f"L3_CHECKS names a missing file: {fname}"

    def test_changelog_has_4230_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.22.0")[0]
        for token in (
            "## 4.23.0",
            "CLASSIFIER_EXEMPT_COMMANDS",
            "L3_CHECKS",
            "classifying-task-kind",
        ):
            assert token in body, f"CHANGELOG 4.23.0 entry missing {token!r}"

    def test_changelog_records_that_this_reverses_a_deliberate_exemption(self):
        body = self._entry()
        assert "deliberate" in body, (
            "the 4.23.0 entry must state that drive's exemption was a recorded "
            "decision being reversed, not an oversight being corrected"
        )


class TestVersion4220:
    """Relay 4.22.0 — /relay:verify, a bounded verify-until-clean loop whose exit
    signal is the /verify verdict, never the findings count."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    CMD = PLUGIN_ROOT / "commands" / "verify.md"
    PROMPT_HELPER = PLUGIN_ROOT / "scripts" / "run-claude-prompt.sh"
    PARSER = PLUGIN_ROOT / "scripts" / "parse-verify-verdict.sh"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.22.0")[1].split("## 4.21.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4220(self):
        # Superseded exact pin: 4.23.0 carries this line forward (TestVersion4230
        # owns the current exact pin). Same relaxed idiom as TestVersion4210.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.22.0")

    def test_changelog_has_4220_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.21.0")[0]
        for token in (
            "## 4.22.0",
            "/relay:verify",
            "run-claude-prompt.sh",
            "parse-verify-verdict.sh",
            "SKIP",
            "BLOCKED",
            "RELAY_VERIFY_RESULT",
        ):
            assert token in body, f"CHANGELOG 4.22.0 entry missing {token!r}"

    def test_changelog_records_why_the_verdict_is_the_exit_signal(self):
        body = self._entry()
        assert "never be reached" in body and "findings count" in body, (
            "the 4.22.0 entry must record WHY the findings count cannot be an exit "
            "predicate, not merely that the verdict is read"
        )

    def test_new_scripts_are_executable(self):
        import os as _os

        for path in (self.PROMPT_HELPER, self.PARSER):
            assert _os.access(path, _os.X_OK), f"{path} must be executable"

    def test_verify_command_ships(self):
        assert self.CMD.is_file()


class TestVersion4210:
    """Relay 4.21.0 — three acpx-leg defects: undelivered preamble, rejected codex
    model encoding, and a capability gate that was never wired to anything."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    DISPATCH = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh"
    VALIDATOR = PLUGIN_ROOT / "scripts" / "capability-validate.js"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.21.0")[1].split("## 4.20.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4210(self):
        # Superseded exact pin: 4.22.0 carries this line forward (TestVersion4220
        # owns the current exact pin). Same relaxed idiom as TestVersion4200.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.21.0")

    def test_preamble_is_read_by_the_dispatcher(self):
        assert "preamble.md" in self.DISPATCH.read_text()

    def test_validator_exposes_the_tool_set_gate(self):
        assert "validateRoleAgainstTools" in self.VALIDATOR.read_text()

    def test_changelog_has_4210_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.20.0")[0]
        for token in (
            "## 4.21.0",
            "preamble.md",
            "NEEDS_DECISION:",
            "CODEX_CONFIG",
            "validateRoleAgainstTools",
            "test_capability_gate.py",
        ):
            assert token in body, f"CHANGELOG 4.21.0 entry missing {token!r}"

    def test_changelog_records_the_namespace_error(self):
        body = self._entry()
        assert "disjoint namespaces" in body, (
            "the 4.21.0 entry must record WHY the documented capability check was "
            "wrong, not merely that it was unwired — the pairing was a type error"
        )


class TestVersion4200:
    """Relay 4.20.0 — the polish-review leaf drops from xhigh to medium.

    4.24.0 moved the loop mechanics out of `commands/implement.md` and into
    `skills/verifying-until-clean/SKILL.md`; the medium pin this class checks moved
    with it, so `IMPLEMENT` below now points at the skill.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    IMPLEMENT = PLUGIN_ROOT / "skills" / "verifying-until-clean" / "SKILL.md"

    def test_plugin_version_4200(self):
        # Superseded exact pin: 4.21.0 carries this line forward (TestVersion4210
        # owns the current exact pin). Same relaxed idiom as TestVersion4190.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.20.0")

    def test_polish_review_runs_medium(self):
        body = self.IMPLEMENT.read_text()
        assert '"/code-review medium --fix"' in body
        assert '"/code-review xhigh --fix"' not in body

    def test_changelog_has_4200_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.19.0")[0]
        for token in (
            "## 4.20.0",
            "/code-review medium --fix",
            "down from `xhigh`",
        ):
            assert token in body, f"CHANGELOG 4.20.0 entry missing {token!r}"


class TestVersion4190:
    """Relay 4.19.0 — narrative documentation, the ADR set, and the freshness gate."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    ARCHITECTURE = PLUGIN_ROOT / "docs" / "architecture.md"
    CONTRIBUTING = PLUGIN_ROOT / "docs" / "contributing.md"
    ADR_DIR = PLUGIN_ROOT / "docs" / "adr"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.19.0")[1].split("## 4.18.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4190(self):
        # Superseded exact pin: 4.20.0 carries this line forward (TestVersion4200
        # owns the current exact pin). Same relaxed idiom as TestVersion4180.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.19.0")

    def test_narrative_docs_ship(self):
        for doc in (self.ARCHITECTURE, self.CONTRIBUTING):
            assert doc.is_file(), f"{doc.name} missing"

    def test_adr_set_ships(self):
        assert (self.ADR_DIR / "README.md").is_file(), "docs/adr/README.md missing"
        records = sorted(self.ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
        assert len(records) >= 8, f"expected the initial 8 ADRs; found {len(records)}"

    def test_changelog_has_4190_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.18.0")[0]
        for token in (
            "## 4.19.0",
            "docs/architecture.md",
            "docs/contributing.md",
            "docs/adr/",
            "test_docs_freshness.py",
            "ADR-FORMAT.md",
        ):
            assert token in body, f"CHANGELOG 4.19.0 entry missing {token!r}"

    def test_changelog_records_why_adrs_and_not_more_specs(self):
        body = self._entry()
        assert "still holds" in body, (
            "the 4.19.0 entry must state what an ADR answers that a spec and the "
            "CHANGELOG do not"
        )


class TestVersion4180:
    """Relay 4.18.0 — the agent-registration fix."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    ROSTER = PLUGIN_ROOT / "docs" / "agent-roster.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.18.0")[1].split("## 4.17.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4180(self):
        # Superseded exact pin: 4.19.0 carries this line forward (TestVersion4190
        # owns the current exact pin). Same relaxed idiom as TestVersion4170.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.18.0")

    def test_agents_dir_holds_no_documentation(self):
        """The roster moved out of agents/ because every *.md there registers."""
        assert not (PLUGIN_ROOT / "agents" / "README.md").exists()
        assert self.ROSTER.is_file()

    def test_changelog_has_4180_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.17.0")[0]
        for token in (
            "## 4.18.0",
            "relay:relay:leaf-worker",
            "docs/agent-roster.md",
            "test_agent_registration.py",
        ):
            assert token in body, f"CHANGELOG 4.18.0 entry missing {token!r}"

    def test_changelog_quotes_the_observed_dispatch_error(self):
        """The entry must carry the literal harness error, not a paraphrase — it is
        the evidence the defect was real and not merely cosmetic. Whitespace is
        collapsed because the file is hard-wrapped and the string straddles a break."""
        body = self._entry()
        assert "Agent type 'relay:leaf-worker' not found" in body, (
            "the 4.18.0 entry must quote the exact dispatch error verbatim"
        )

    def test_changelog_states_the_test_encoded_the_bug(self):
        body = self._entry()
        assert "encoded the bug" in body, (
            "the 4.18.0 entry must record that test_name_matches_slug asserted the "
            "broken name, since that is why the defect survived 17 releases"
        )


class TestVersion4170:
    """Relay 4.17.0 — `--retro`, the post-run audit, and the run-intent record."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    RETRO = PLUGIN_ROOT / "scripts" / "retro-run.sh"
    INTENT = PLUGIN_ROOT / "scripts" / "record-run-intent.sh"

    def test_plugin_version_4170(self):
        # Superseded exact pin: 4.18.0 carries this line forward (TestVersion4180
        # owns the current exact pin). Same relaxed idiom as TestVersion4160.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.17.0")

    def test_both_new_scripts_ship_and_are_executable(self):
        for script in (self.RETRO, self.INTENT):
            assert script.is_file(), f"{script.name} missing"
            assert os.access(script, os.X_OK), f"{script.name} is not executable"

    def test_changelog_has_4170_entry(self):
        body = self.CHANGELOG.read_text().split("## 4.16.0")[0]
        for token in (
            "## 4.17.0",
            "retro-run.sh",
            "record-run-intent.sh",
            "runs.jsonl",
            "--retro",
            "Step 3.5",
            "intended_spine",
            "gates",
            "axis_source",
        ):
            assert token in body, f"CHANGELOG 4.17.0 entry missing {token!r}"

    def test_changelog_states_the_retro_never_reports_clean_when_unchecked(self):
        body = re.sub(r"\s+", " ", self.CHANGELOG.read_text().split("## 4.16.0")[0])
        assert "never reports CLEAN" in body
        assert "audits the gate" in body


class TestVersion4160:
    """Relay 4.16.0 — turn-lifetime rule, improve-loop's third outcome, and the
    always-on run-completeness gate."""

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    GATE = PLUGIN_ROOT / "scripts" / "verify-run-completeness.sh"

    def _entry(self):
        """The 4.16.0 entry with newlines collapsed. The file is hard-wrapped at ~90
        columns, so any asserted phrase long enough to be meaningful will straddle a
        line break; matching the raw text would pass or fail on reflow rather than on
        content."""
        body = self.CHANGELOG.read_text().split("## 4.16.0")[1].split("## 4.15.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4160(self):
        # Superseded exact pin: 4.17.0 carries this line forward (TestVersion4170
        # owns the current exact pin). Same relaxed idiom as TestVersion4150.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.16.0")

    def test_changelog_has_4160_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.16.0",
            "TURN-LIFETIME RULE",
            "watcher_budget_exhausted",
            "no-answer",
            "verify-run-completeness.sh",
        ):
            assert token in body, f"CHANGELOG 4.16.0 entry missing {token!r}"

    def test_changelog_records_the_backgrounding_correction(self):
        """The precise distinction is load-bearing: all four succeeding nodes also
        backgrounded. A future reader who takes "backgrounding was the bug" from this
        entry would remove the only pattern that works."""
        body = self._entry()
        assert "Backgrounding is permitted; abandoning is not" in body
        assert "run_in_background" in body

    def test_changelog_records_the_measured_evidence(self):
        """Ungrounded reliability claims rot. Pin the corpus and the validation result
        so a later edit cannot quietly widen either."""
        body = self._entry()
        for token in ("38 workflow runs / 426 agent nodes", "35 PASS / 3 FAIL"):
            assert token in body, f"CHANGELOG 4.16.0 entry missing {token!r}"
        assert "zero false positives" in body.lower()

    def test_changelog_justifies_the_always_on_gate(self):
        """§2.5's argument, not just its conclusion: a reviewer who only sees "the gate
        is on" will read it as overreach and soften it, which is the bug."""
        body = self._entry()
        assert "always-on" in body
        assert "invisible exactly when it matters" in body

    def test_changelog_names_the_exit_codes(self):
        body = self._entry()
        for token in ("COMPLETE", "INCOMPLETE", "INDETERMINATE"):
            assert token in body, f"CHANGELOG 4.16.0 entry missing {token!r}"
        assert "never to a pass" in body

    def test_gate_script_exists_and_is_executable(self):
        assert self.GATE.is_file(), "scripts/verify-run-completeness.sh missing"
        assert os.access(self.GATE, os.X_OK), (
            "verify-run-completeness.sh must be executable"
        )

    def test_manifest_version_matches_newest_changelog_entry(self):
        """The version is the cache key for plugin distribution; a manifest bump with
        no entry, or an entry with no bump, ships an unannounced change."""
        import json

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        newest = re.search(r"^## (\d+\.\d+\.\d+)", self.CHANGELOG.read_text(), re.M)
        assert newest, "CHANGELOG has no versioned entry"
        assert newest.group(1) == manifest["version"]


class TestSimulatorGrounding:
    """Guards the grounding discipline duplicated across both simulator roles.

    `roles/` has no include mechanism, so the grounding block and the
    Executable Claims lens are necessarily copy-pasted between the two
    simulators. These assertions are the only thing preventing the copies
    from drifting apart.
    """

    SIMULATORS = ("plan-simulator", "spec-simulator")

    def _body(self, slug):
        return (PLUGIN_ROOT / "roles" / f"{slug}.md").read_text()

    @pytest.mark.parametrize("slug", SIMULATORS)
    def test_grounding_discipline_present(self, slug):
        body = self._body(slug)
        for token in ("file:line", "UNVERIFIED:", "read-only shell commands"):
            assert token in body, f"{slug}: grounding block missing {token!r}"

    @pytest.mark.parametrize("slug", SIMULATORS)
    def test_executable_claims_lens_present(self, slug):
        assert "**Executable Claims**" in self._body(slug), \
            f"{slug}: Executable Claims lens missing"

    @pytest.mark.parametrize("slug", SIMULATORS)
    def test_run_bash_capability_declared(self, slug):
        # The lens tells the role to execute commands; requires: must say so.
        assert "run_bash" in self._body(slug), \
            f"{slug}: Executable Claims lens needs run_bash in requires:"

    WORDS = {
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12,
    }

    @pytest.mark.parametrize(
        "slug,end_marker,pattern",
        [
            ("plan-simulator", "### Severity guide", r"all (\w+) lenses"),
            ("spec-simulator", "Severity guide:", r"these (\w+) gap patterns"),
        ],
    )
    def test_stated_lens_count_matches_bullets(self, slug, end_marker, pattern):
        # The counts are hand-maintained prose ("all eleven lenses", "these
        # eight gap patterns"). Parse the number OUT of the prose rather than
        # hardcoding it here, so a stale count fails even if the bullets and
        # this test still agree.
        import re

        body = self._body(slug)
        m = re.search(pattern, body)
        assert m, f"{slug}: could not find the lens-count prose matching {pattern!r}"
        word = m.group(1)
        assert word in self.WORDS, f"{slug}: unrecognised count word {word!r}"
        stated = self.WORDS[word]

        start = body.index("## Method")
        section = body[start:body.index(end_marker, start)]
        bullets = [ln for ln in section.splitlines() if ln.startswith("- **")]
        assert len(bullets) == stated, (
            f"{slug}: prose states {word} ({stated}) lenses but {len(bullets)} bullets "
            f"found — update the count when adding or removing a lens"
        )


class TestDirectoryStructure:
    def test_agents_dir(self):
        assert (PLUGIN_ROOT / "agents").is_dir()

    def test_commands_dir(self):
        assert (PLUGIN_ROOT / "commands").is_dir()

    def test_refine_is_single_command_file(self):
        # Phase-3 Task 3: the refine subcommand directory collapsed into one
        # thin-L3 command file; the old commands/refine/ dir is retired.
        assert (PLUGIN_ROOT / "commands" / "refine.md").is_file()
        assert not (PLUGIN_ROOT / "commands" / "refine").exists()

    def test_skills_dir(self):
        assert (PLUGIN_ROOT / "skills").is_dir()

    def test_bindings_dir(self):
        assert (PLUGIN_ROOT / "bindings").is_dir()

    def test_scripts_dir(self):
        assert (PLUGIN_ROOT / "scripts").is_dir()

    def test_docs_dir(self):
        assert (PLUGIN_ROOT / "docs").is_dir()

    def test_tests_unit_skill_structure_dir(self):
        assert (PLUGIN_ROOT / "tests" / "unit" / "skill-structure").is_dir()

    def test_tests_e2e_fixtures_dir(self):
        assert (PLUGIN_ROOT / "tests" / "e2e" / "fixtures").is_dir()


# Task 7 (PR3 §7): shrink to exactly the 7 §2 slugs after git rm of 22 collapsed agents.
EXPECTED_AGENTS = {
    "code-reviewer",
    "scout",
    "leaf-worker",
    "leaf-reader",
    "gatherer",
    "strategist",
    "analyst",
}

# ---------------------------------------------------------------------------
# Task 1 additions — diagnose agents subset (still kept registered)
# ---------------------------------------------------------------------------

DIAGNOSE_AGENT_SLUGS = {"gatherer", "strategist", "analyst"}

# ---------------------------------------------------------------------------
# PR3 Task 1 additions — two generic leaf agents (relay:leaf-worker, relay:leaf-reader)
# ---------------------------------------------------------------------------

LEAF_SLUGS = {"leaf-worker", "leaf-reader"}

LEAF_WORKER_TOOLS = {"Read", "Write", "Edit", "Bash", "Grep", "Glob"}
LEAF_READER_TOOLS = {"Read", "Grep", "Glob", "Bash"}

# spec §3 DROP list (verbatim). resolving-decision is not listed here — it was
# deleted in the phase-4 teardown as a dead orphan, not a spec §3 drop.
DROPPED_SKILLS = {
    "brainstorming",
    "writing-plans",
    "writing-skills",
    "executing-plans",
    "systematic-debugging",
    "test-driven-development",
    "using-git-worktrees",
    "verification-before-completion",
    "verify-spec",
    "requesting-code-review",
    "receiving-code-review",
    "identify-design-principles",
    "prototyping",
    "retrospective-provenance",
    "finishing-a-development-branch",
    "write-spec",
    "using-superpowers",
    "subagent-driven-development",
    "dispatching-parallel-agents",
}


def _agent_path(slug):
    return PLUGIN_ROOT / "agents" / f"{slug}.md"


def _normalize_tools(tools):
    """tools: may be a string ('Read, Bash') or a list. Return a single string blob."""
    if isinstance(tools, list):
        return ", ".join(str(t) for t in tools)
    return str(tools)


class TestAgents:
    def test_all_agent_files_exist(self):
        missing = sorted(s for s in EXPECTED_AGENTS if not _agent_path(s).is_file())
        assert not missing, f"missing agent files: {missing}"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_required_frontmatter(self, slug):
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        # Leaf agents intentionally carry no model: key (spec §2); all others require it.
        required = {"name", "description", "tools"} if slug in LEAF_SLUGS else {"name", "description", "tools", "model"}
        for field in required:
            assert field in fm, f"{slug}: missing frontmatter field {field}"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_name_matches_slug(self, slug):
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        # EVERY agent uses the bare slug. The loader prefixes the plugin namespace,
        # so `name: <slug>` registers as `relay:<slug>` — the string every dispatch
        # site in the plugin references.
        #
        # 4.18.0: the leaves previously carried `name: relay:<slug>`, which the loader
        # prefixed AGAIN and registered as `relay:relay:leaf-worker`. Dispatching the
        # documented `relay:leaf-worker` then failed hard with "Agent type not found",
        # on the path all 22 roles route through. This assertion used to encode that
        # bug by special-casing LEAF_SLUGS; it now holds one rule for all 7 agents.
        assert fm["name"] == slug, (
            f"{slug}: frontmatter name must be the bare slug. A namespaced value here "
            f"is prefixed twice and registers as relay:relay:{slug}."
        )

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_no_agent_tool(self, slug):
        # gate (a): leaf enforcement — no whole-word `Agent` in tools:
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        blob = _normalize_tools(fm["tools"])
        assert not re.search(r"\bAgent\b", blob), f"{slug}: Agent tool not allowed (leaf enforcement)"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_no_skill_backdoor(self, slug):
        # gate (a) hardening: no whole-word `Skill` in tools: (transitive dispatch backdoor)
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        blob = _normalize_tools(fm["tools"])
        assert not re.search(r"\bSkill\b", blob), f"{slug}: Skill tool not allowed (transitive backdoor)"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_relay_block(self, slug):
        # gate (c): relay: nested block parses + has envelope_tokens/one_shot/max_turns
        if slug in DIAGNOSE_AGENT_SLUGS | LEAF_SLUGS:
            pytest.skip("Workflow-leaf or generic leaf: no relay: block")
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        relay = fm.get("relay")
        assert isinstance(relay, dict), f"{slug}: relay block missing or not a dict"
        assert isinstance(relay.get("envelope_tokens"), list), f"{slug}: relay.envelope_tokens not a list"
        assert relay.get("one_shot") is True, f"{slug}: relay.one_shot must be True"
        assert isinstance(relay.get("max_turns"), int), f"{slug}: relay.max_turns not an int"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_verify_artifact_only_where_sourced(self, slug):
        # Post-PR3: verify_artifact has moved from agent relay: blocks to role frontmatter.
        # The 7 kept agents (code-reviewer, scout, leaves, diagnosis trio) carry no
        # verify_artifact in their relay: block.
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        relay = fm.get("relay") or {}
        va = relay.get("verify_artifact")
        # No kept agent should have verify_artifact — it moved to role frontmatter.
        assert va is None, f"{slug}: relay.verify_artifact must be absent from kept agents (moved to role frontmatter)"

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_body_nonempty(self, slug):
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        _, body = parse_frontmatter(path)
        assert len(body) > 200, f"{slug}: body too short"


class TestLeafInvariant:
    """TOOL-4: no agent tools: field may grant `Agent` or `Skill` (leaf enforcement gate).

    This is a deterministic leaf invariant — currently 0 violations across all agents.
    TestAgents already covers each agent individually via test_no_agent_tool /
    test_no_skill_backdoor; this class names TOOL-4 as its explicit motivation so the
    invariant stays auditable and any future accidental grant is caught.
    """

    @pytest.mark.parametrize("slug", sorted(EXPECTED_AGENTS))
    def test_no_agent_or_skill_in_tools_field(self, slug):
        path = _agent_path(slug)
        if not path.is_file():
            pytest.skip(f"{slug} not yet ported")
        fm, _ = parse_frontmatter(path)
        blob = _normalize_tools(fm.get("tools", ""))
        # Whole-word match: 'Agent'/'Skill' as standalone tool names, not as substrings
        # (e.g. MCP tool ids or words like 'agentType').
        assert not re.search(r"\bAgent\b", blob), (
            f"{slug}: 'Agent' tool grant violates leaf invariant (TOOL-4)"
        )
        assert not re.search(r"\bSkill\b", blob), (
            f"{slug}: 'Skill' tool grant violates leaf invariant (TOOL-4)"
        )


class TestLeafAgents:
    """CI-pinned §10 validators for the two generic leaf agents (PR3 Task 1)."""

    def test_leaf_worker_exists(self):
        assert _agent_path("leaf-worker").is_file()

    def test_leaf_reader_exists(self):
        assert _agent_path("leaf-reader").is_file()

    def test_leaf_worker_tools_exact(self):
        fm, _ = parse_frontmatter(_agent_path("leaf-worker"))
        tools = {t.strip() for t in _normalize_tools(fm["tools"]).split(",")}
        assert tools == LEAF_WORKER_TOOLS, f"leaf-worker tools mismatch: {tools}"

    def test_leaf_reader_tools_exact(self):
        fm, _ = parse_frontmatter(_agent_path("leaf-reader"))
        tools = {t.strip() for t in _normalize_tools(fm["tools"]).split(",")}
        assert tools == LEAF_READER_TOOLS, f"leaf-reader tools mismatch: {tools}"

    def test_leaf_worker_description_contains_do_not_invoke_directly(self):
        fm, _ = parse_frontmatter(_agent_path("leaf-worker"))
        assert "Do not invoke directly" in fm["description"]

    def test_leaf_reader_description_contains_do_not_invoke_directly(self):
        fm, _ = parse_frontmatter(_agent_path("leaf-reader"))
        assert "Do not invoke directly" in fm["description"]

    def test_leaf_worker_no_agent_tool(self):
        fm, _ = parse_frontmatter(_agent_path("leaf-worker"))
        blob = _normalize_tools(fm["tools"])
        assert not re.search(r"\bAgent\b", blob)
        assert not re.search(r"\bSkill\b", blob)

    def test_leaf_reader_no_agent_tool(self):
        fm, _ = parse_frontmatter(_agent_path("leaf-reader"))
        blob = _normalize_tools(fm["tools"])
        assert not re.search(r"\bAgent\b", blob)
        assert not re.search(r"\bSkill\b", blob)


class TestDocReferenceReviewerAgent:
    """Post-PR3 §7: doc-reference-reviewer is a role file, not an agent file."""
    ROLE_PATH = PLUGIN_ROOT / "roles" / "doc-reference-reviewer.md"

    def test_role_file_exists(self):
        assert self.ROLE_PATH.is_file(), "roles/doc-reference-reviewer.md must exist"

    def test_role_class_is_reader(self):
        import yaml as _yaml
        text = self.ROLE_PATH.read_text()
        end = text.index("---", 3)
        fm = _yaml.safe_load(text[3:end]) or {}
        assert fm.get("role-class") == "reader", "doc-reference-reviewer: role-class must be reader"

    def test_role_body_invokes_helper(self):
        import yaml as _yaml
        text = self.ROLE_PATH.read_text()
        end = text.index("---", 3)
        body = text[end + 3:].strip()
        assert "doc_reference_scan.py" in body, "doc-reference-reviewer role body must invoke doc_reference_scan.py"

    def test_role_output_tokens_nonempty(self):
        import yaml as _yaml
        text = self.ROLE_PATH.read_text()
        end = text.index("---", 3)
        fm = _yaml.safe_load(text[3:end]) or {}
        assert isinstance(fm.get("output-tokens"), list) and fm["output-tokens"], \
            "doc-reference-reviewer: output-tokens must be non-empty list"

    def test_presets_entry_present_and_well_formed(self):
        import yaml as _yaml
        presets = _yaml.safe_load((PLUGIN_ROOT / "bindings" / "presets.yaml").read_text())
        entry = presets["roles"].get("doc-reference-reviewer")
        assert entry is not None, "doc-reference-reviewer missing from presets roles"
        assert entry["role-class"] == "reader"
        # 4.46.0: this role joined the `verification` category, and every role of that
        # category takes the category model. It was on the haiku rung from 4.14.0,
        # because scripts/doc_reference_scan.py does the scanning work; the category
        # rule outranks that, and `--verification-model` moves this role with the rest.
        assert entry["category"] == "verification"
        assert entry["model"] == "opus"
        assert entry["one_shot"] is True
        assert entry["mechanism"] == "acpx-claude"
        assert entry["permissions"] == "approve-reads"
        assert entry["max_turns"] == 8
        assert entry["isolation"] == "none"
        assert entry["timeout_seconds"] == 900
        assert entry["retries"] == 1
        assert entry["provides"] == ["ROLE_DONE", "REVIEW"]
        assert entry["modalities"]["claude"] == {"model": "opus", "effort": "medium"}
        assert entry["modalities"]["codex"] == {"model": "gpt-5.6-terra", "effort": "medium"}
        assert entry["modalities"]["hybrid"] == {"engine": "claude"}


def _iter_text_files():
    """All text files under PLUGIN_ROOT, skipping tests/e2e/runs/ and .gitkeep."""
    for path in PLUGIN_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name == ".gitkeep":
            continue
        rel = path.relative_to(PLUGIN_ROOT)
        if "runs" in rel.parts and rel.parts[:2] == ("tests", "e2e"):
            continue
        if "__pycache__" in rel.parts:
            continue
        try:
            yield path, path.read_text()
        except (UnicodeDecodeError, OSError):
            continue


class TestRenameCompleteness:
    def test_no_end_to_end_literal(self):
        # gate (d): zero `end-to-end-implementation` literals tree-wide.
        # This test file itself documents the literal it forbids; exclude it.
        offenders = []
        for path, text in _iter_text_files():
            if path.resolve() == PLUGIN_ROOT.joinpath(
                "tests", "unit", "skill-structure", "test_plugin.py"
            ).resolve():
                continue
            if "end-to-end-implementation" in text:
                offenders.append(str(path.relative_to(PLUGIN_ROOT)))
        assert not offenders, f"end-to-end-implementation literal found in: {offenders}"

    def test_no_leftover_dropped_skill_refs(self):
        # gate (d) extension: no relative-path or bare-name dropped-skill refs in
        # retained agents/*.md (excluding README) and skills/**/SKILL.md.
        targets = []
        for path in (PLUGIN_ROOT / "agents").glob("*.md"):
            if path.name == "README.md":
                continue
            targets.append(path)
        targets.extend((PLUGIN_ROOT / "skills").rglob("SKILL.md"))

        offenders = []
        invoke_ctx = re.compile(r"Skill|invoke|dispatch|coordinator", re.IGNORECASE)
        for path in targets:
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for line in text.splitlines():
                for name in DROPPED_SKILLS:
                    # (1) relative-path reference skills/<name>/
                    if f"skills/{name}/" in line:
                        offenders.append((str(path.relative_to(PLUGIN_ROOT)), name, "path"))
                    # (2) bare-name in a Skill-invocation line without superpowers: prefix
                    if invoke_ctx.search(line):
                        bare = re.search(rf"(?<!superpowers:)\b{re.escape(name)}\b", line)
                        if bare:
                            offenders.append((str(path.relative_to(PLUGIN_ROOT)), name, "bare"))
        assert not offenders, f"leftover dropped-skill refs: {offenders}"


class TestAgentsReadme:
    README = PLUGIN_ROOT / "docs" / "agent-roster.md"

    def test_file_exists(self):
        assert self.README.is_file()

    def test_mentions_leaf_enforcement(self):
        text = self.README.read_text()
        assert "leaf" in text
        # leaf enforcement = no Agent in tools:
        assert "Agent" in text and "tools:" in text

    def test_dropped_roles_not_ported(self):
        text = self.README.read_text()
        # brainstormer and codex-session-driver may appear only inside the
        # "Not ported" section — never listed as ported native subagents.
        lines = text.splitlines()
        # find the "Not ported" heading and its section bounds
        not_ported_start = None
        for i, line in enumerate(lines):
            if line.lstrip().lower().startswith("## ") and "not ported" in line.lower():
                not_ported_start = i
                break
        assert not_ported_start is not None, "README missing a 'Not ported' section"
        not_ported_end = len(lines)
        for i in range(not_ported_start + 1, len(lines)):
            if lines[i].lstrip().startswith("## "):
                not_ported_end = i
                break
        not_ported_idx = set(range(not_ported_start, not_ported_end))
        for i, line in enumerate(lines):
            for dropped in ("brainstormer", "codex-session-driver"):
                if dropped in line:
                    assert i in not_ported_idx, (
                        f"{dropped} referenced outside the 'Not ported' section: {line!r}"
                    )

    def test_no_skill_md_claim(self):
        text = self.README.read_text()
        assert "SKILL.md" not in text

    def test_roster_heading_is_22_in_roles(self):
        """roles/README.md must say 'The 22 roles'."""
        text = (PLUGIN_ROOT / "roles" / "README.md").read_text()
        assert "22 roles" in text or "The 22 roles" in text

    def test_agents_readme_does_not_say_19_roles(self):
        text = (PLUGIN_ROOT / "docs" / "agent-roster.md").read_text()
        assert "The 19 roles" not in text

    def test_roster_heading_in_agents_readme_says_7(self):
        text = (PLUGIN_ROOT / "docs" / "agent-roster.md").read_text()
        assert "7 agents" in text

    def test_agents_readme_has_diagnosis_section(self):
        text = (PLUGIN_ROOT / "docs" / "agent-roster.md").read_text()
        assert "Diagnosis (Workflow substrate)" in text
        for trio in ("gatherer", "strategist", "analyst"):
            assert trio in text


# All relay skills (spec §3 + relay-ui-refine additions).
EXPECTED_SKILLS = {
    "refining",
    "refining-specs",
    "refining-plans",
    "refining-prs",
    "refining-ui",
    "dispatching-in-session-agents",
    "dispatching-acpx-agents",
    "using-relay",
    "setting-up-relay",
    "running-web-apps",
    "check-readiness",   # NEW
    "driving-to-done",   # NEW — autonomous run-to-done protocol backing /relay:drive
    "ensuring-worktree-isolation",   # NEW — Step 0.5 worktree-isolation gate (v4.5.0)
    "setting-up-engines",   # NEW — codex/opencode engine setup + verification assistant (v4.9.0)
    "verifying-until-clean",   # NEW — protocol skill backing /relay:verify (v4.22.0)
    "dispatching-bg-agents",   # NEW — bg-sessions per-leaf dispatch (v4.30.0)
    "orchestrating-session-trees",   # NEW — session-tree substrate orchestrator (v4.30.0)
    "running-implement-spine",   # NEW — Workflow generation + run-intent + completeness gate (v4.38.0)
    "implementing-spec",   # NEW — the apk-probed adapter over running-implement-spine (v4.39.0)
}


def _skill_path(name):
    return PLUGIN_ROOT / "skills" / name / "SKILL.md"


class TestSkills:
    @pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
    def test_skill_file_exists(self, name):
        path = _skill_path(name)
        if not path.is_file():
            pytest.skip(f"{name} not yet ported")
        assert path.is_file()

    @pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
    def test_required_frontmatter(self, name):
        path = _skill_path(name)
        if not path.is_file():
            pytest.skip(f"{name} not yet ported")
        fm, _ = parse_frontmatter(path)
        assert "name" in fm, f"{name}: missing frontmatter field name"
        assert "description" in fm, f"{name}: missing frontmatter field description"

    @pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
    def test_name_matches_dir(self, name):
        path = _skill_path(name)
        if not path.is_file():
            pytest.skip(f"{name} not yet ported")
        fm, _ = parse_frontmatter(path)
        assert fm["name"] == name

    @pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
    def test_body_nonempty(self, name):
        path = _skill_path(name)
        if not path.is_file():
            pytest.skip(f"{name} not yet ported")
        _, body = parse_frontmatter(path)
        assert len(body) > 200, f"{name}: body too short"


# SKILL-1: internal skills are every skill EXCEPT the menu/orientation skill.
# Derived (NOT hardcoded) so it tracks EXPECTED_SKILLS; with the scouting skill
# deleted (AGENT-3) this yields the 11-skill internal set.
INTERNAL_SKILLS = EXPECTED_SKILLS - {"using-relay"}


class TestSkillInvocableControl:
    """SKILL-1: all internal skills must set user-invocable: false."""

    @pytest.mark.parametrize("name", sorted(INTERNAL_SKILLS))
    def test_internal_skill_not_user_invocable(self, name):
        path = _skill_path(name)
        if not path.is_file():
            pytest.skip(f"{name} not yet ported")
        fm, _ = parse_frontmatter(path)
        assert fm.get("user-invocable") is False, (
            f"{name}: internal skill must have user-invocable: false"
        )

    def test_using_relay_has_no_user_invocable_false(self):
        fm, _ = parse_frontmatter(_skill_path("using-relay"))
        assert fm.get("user-invocable") is not False, (
            "using-relay: must NOT have user-invocable: false (it is the menu skill)"
        )


class TestNewSkillsRegistered:
    """Task 8 — explicit membership and invocable-control assertions for the two
    relay-ui-refine additions: refining-ui (Task 5) and running-web-apps (Task 4).

    These assertions are purposely redundant with the parametrized TestSkills and
    TestSkillInvocableControl rows so that a future refactor that removes either
    skill from EXPECTED_SKILLS immediately produces a named, easy-to-diagnose failure
    rather than a silent parametrize omission.
    """

    # Six named assertions required by the task specification.

    def test_refining_ui_in_expected_skills(self):
        """refining-ui must be a member of EXPECTED_SKILLS."""
        assert "refining-ui" in EXPECTED_SKILLS, (
            "refining-ui must be registered in EXPECTED_SKILLS"
        )

    def test_running_web_apps_in_expected_skills(self):
        """running-web-apps must be a member of EXPECTED_SKILLS."""
        assert "running-web-apps" in EXPECTED_SKILLS, (
            "running-web-apps must be registered in EXPECTED_SKILLS"
        )

    def test_refining_ui_in_internal_skills(self):
        """refining-ui must appear in INTERNAL_SKILLS (EXPECTED_SKILLS - {'using-relay'})."""
        assert "refining-ui" in INTERNAL_SKILLS, (
            "refining-ui must be in INTERNAL_SKILLS (derived as EXPECTED_SKILLS - {'using-relay'})"
        )

    def test_running_web_apps_in_internal_skills(self):
        """running-web-apps must appear in INTERNAL_SKILLS."""
        assert "running-web-apps" in INTERNAL_SKILLS, (
            "running-web-apps must be in INTERNAL_SKILLS (derived as EXPECTED_SKILLS - {'using-relay'})"
        )

    def test_refining_ui_user_invocable_false(self):
        """refining-ui SKILL.md must carry user-invocable: false (internal skill)."""
        path = _skill_path("refining-ui")
        if not path.is_file():
            pytest.skip("refining-ui/SKILL.md not yet present")
        fm, _ = parse_frontmatter(path)
        assert fm.get("user-invocable") is False, (
            "refining-ui: internal skill must have user-invocable: false"
        )

    def test_running_web_apps_user_invocable_false(self):
        """running-web-apps SKILL.md must carry user-invocable: false (internal skill)."""
        path = _skill_path("running-web-apps")
        if not path.is_file():
            pytest.skip("running-web-apps/SKILL.md not yet present")
        fm, _ = parse_frontmatter(path)
        assert fm.get("user-invocable") is False, (
            "running-web-apps: internal skill must have user-invocable: false"
        )

    def test_verifying_until_clean_in_expected_skills(self):
        """verifying-until-clean must be a member of EXPECTED_SKILLS."""
        assert "verifying-until-clean" in EXPECTED_SKILLS, (
            "verifying-until-clean must be registered in EXPECTED_SKILLS"
        )

    def test_verifying_until_clean_in_internal_skills(self):
        """verifying-until-clean must appear in INTERNAL_SKILLS."""
        assert "verifying-until-clean" in INTERNAL_SKILLS, (
            "verifying-until-clean must be in INTERNAL_SKILLS "
            "(derived as EXPECTED_SKILLS - {'using-relay'})"
        )


class TestRunningImplementSpineSkill:
    SKILL = _skill_path("running-implement-spine")

    def test_it_is_registered(self):
        assert "running-implement-spine" in EXPECTED_SKILLS

    def test_it_is_internal(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm.get("user-invocable") is False

    def test_it_names_the_command_it_backs(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert "/relay:implement" in str(fm["description"])

    @pytest.mark.parametrize(
        "field", ["kind", "task", "spec_path", "engine", "agent", "verify",
                  "rounds", "closes_issue", "keep_sessions"]
    )
    def test_it_declares_every_input(self, field):
        _, body = parse_frontmatter(self.SKILL)
        assert field in body

    @pytest.mark.parametrize("field", ["status", "run_id", "branch", "commit", "reason"])
    def test_it_returns_one_json_block(self, field):
        _, body = parse_frontmatter(self.SKILL)
        assert field in body

    @pytest.mark.parametrize("value", ["ok", "blocked", "error"])
    def test_the_status_vocabulary_is_closed(self, value):
        _, body = parse_frontmatter(self.SKILL)
        assert f"`{value}`" in body

    def test_the_command_delegates_and_keeps_no_copy(self):
        """Anti-vacuity: prove the move happened, not only that the skill exists."""
        cmd = (PLUGIN_ROOT / "commands" / "implement.md").read_text()
        assert "relay:running-implement-spine" in cmd
        assert "record-run-intent.sh" not in cmd
        assert "verify-run-completeness.sh" not in cmd
        _, body = parse_frontmatter(self.SKILL)
        assert "record-run-intent.sh" in body
        assert "verify-run-completeness.sh" in body


class TestCheckReadinessSkill:
    SKILL = PLUGIN_ROOT / "skills" / "check-readiness" / "SKILL.md"

    def test_file_exists(self):
        assert self.SKILL.is_file(), "skills/check-readiness/SKILL.md missing"

    def test_name_is_check_readiness(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm["name"] == "check-readiness"

    def test_user_invocable_false(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm.get("user-invocable") is False

    def test_model_only_true(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm.get("model-only") is True

    def test_returns_json_matrix(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "ok" in body and "agents" in body, \
            "skill body must describe the {ok, agents} JSON return shape"

    def test_runs_check_deps(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "check-deps.sh" in body, "skill must invoke check-deps.sh"

    def test_acpx_preflight_defined(self):
        """The floor check moved into scripts/acpx-floor.sh (relay 4.51.0).

        The skill used to run `acpx --version` and restate the number, which is how
        the floor came to disagree with itself across five files. It now calls the
        one script that owns the number.
        """
        _, body = parse_frontmatter(self.SKILL)
        assert "acpx-floor.sh" in body, "skill must run the acpx floor script"
        assert "acpx flow --help" in body, "skill must run acpx flow --help preflight"

    def test_status_field_values_documented(self):
        _, body = parse_frontmatter(self.SKILL)
        for status in ("ok", "missing", "too-old", "flow-subcommand-absent"):
            assert status in body, f"status value {status!r} must be documented"

    def test_no_interactive_output(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "AskUserQuestion" not in body, \
            "check-readiness must not call AskUserQuestion (non-interactive)"


# Task 27 — generic refining loop, 3 adapters, 3 thin shims.
REFINING_CONTRACT_FIELDS = (
    "subject",
    "subject_adapter",
    "critics",
    "aggregator",
    "fixer",
    "convergence_predicate",
    "max_rounds",
    "persistence_marker",
)
REFINING_LOOP_PHASES = ("init", "while round < max_rounds", "CONVERGED", "ESCALATE")
ADAPTER_VERBS = ("load", "snapshot", "diff", "post_fix", "persist", "recover")
ADAPTER_SLUGS = ("spec", "plan", "pr")


class TestRefining:
    SKILL = _skill_path("refining")
    ADAPTERS = PLUGIN_ROOT / "skills" / "refining" / "adapters"

    def test_skill_exists(self):
        assert self.SKILL.is_file()

    def test_name_is_refining(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm["name"] == "refining"

    def test_body_contains_contract_fields(self):
        _, body = parse_frontmatter(self.SKILL)
        for field in REFINING_CONTRACT_FIELDS:
            assert field in body, f"refining: missing contract field {field}"

    def test_body_contains_loop_phases(self):
        _, body = parse_frontmatter(self.SKILL)
        for phase in REFINING_LOOP_PHASES:
            assert phase in body, f"refining: missing loop phase {phase!r}"

    @pytest.mark.parametrize("slug", ADAPTER_SLUGS)
    def test_adapter_file_exists(self, slug):
        assert (self.ADAPTERS / f"{slug}.md").is_file(), f"missing adapter {slug}.md"

    @pytest.mark.parametrize("slug", ADAPTER_SLUGS)
    def test_adapter_declares_interface_verbs(self, slug):
        text = (self.ADAPTERS / f"{slug}.md").read_text()
        for verb in ADAPTER_VERBS:
            assert verb in text, f"adapter {slug}.md: missing interface verb {verb}"


REFINING_SHIMS = {
    "refining-specs": {
        "adapter": "spec",
        # NEW: role-file + leaf form instead of relay:spec-simulator / relay:spec-fixer
        "roles": (
            ("roles/spec-simulator.md", "relay:leaf-reader"),
            ("roles/spec-fixer.md", "relay:leaf-worker"),
        ),
    },
    "refining-plans": {
        "adapter": "plan",
        "roles": (
            ("roles/plan-simulator.md", "relay:leaf-reader"),
            ("roles/plan-fixer.md", "relay:leaf-worker"),
        ),
    },
    "refining-prs": {
        "adapter": "pr",
        # PR shim maps abstract pr-* roles to real ported agents; the dedicated
        # doc-reference-reviewer critic resolves directly (no archetype mapping).
        "agents": ("agents/code-reviewer",),
        "roles": (
            ("roles/server-runner.md", "relay:leaf-reader"),
            ("roles/fix-coder.md", "relay:leaf-worker"),
            ("roles/doc-reference-reviewer.md", "relay:leaf-reader"),
        ),
    },
}


class TestRefiningConvergenceModes:
    """§3 engine extension — convergence_mode: binary | scored.

    Binary path is frozen: spec/plan/pr shims must NOT contain the string
    `convergence_mode` (they inherit binary by absence).  `convergence_mode`
    must NOT appear in REFINING_CONTRACT_FIELDS (it is optional, not required).
    The scored-mode branch adds two aggregator operations (merge_scores + cap)
    and the threshold-AND / plateau-pivot loop from §3.2.
    """

    SKILL = _skill_path("refining")

    # ------------------------------------------------------------------ binary compat

    def test_convergence_mode_not_in_contract_fields(self):
        """convergence_mode is optional — must NOT be in the required-field set."""
        assert "convergence_mode" not in REFINING_CONTRACT_FIELDS, (
            "convergence_mode must be optional (absent from REFINING_CONTRACT_FIELDS)"
        )

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_binary_shims_do_not_contain_convergence_mode(self, name):
        """spec/plan/pr shims inherit binary by absence — must NOT declare convergence_mode."""
        _, body = parse_frontmatter(_skill_path(name))
        assert "convergence_mode" not in body, (
            f"{name}: binary shim must not contain 'convergence_mode' "
            "(binary is inherited by absence)"
        )

    def test_binary_loop_convergence_predicate_preserved(self):
        """Binary path: convergence_predicate + critical_or_important still present."""
        _, body = parse_frontmatter(self.SKILL)
        assert "convergence_predicate(findings)" in body, (
            "refining: binary convergence path must still call convergence_predicate(findings)"
        )
        assert "critical_or_important(findings)" in body, (
            "refining: binary convergence path must still call critical_or_important(findings)"
        )

    def test_binary_fixer_apply_preserved(self):
        """Binary path: fixer.apply(subject, findings) call still present (no mode= arg)."""
        _, body = parse_frontmatter(self.SKILL)
        assert "fixer.apply(subject, findings)" in body, (
            "refining: binary path must retain fixer.apply(subject, findings)"
        )

    # ------------------------------------------------------------------ scored mode

    def test_engine_declares_convergence_mode_field(self):
        """Engine SKILL.md must document the convergence_mode field."""
        _, body = parse_frontmatter(self.SKILL)
        assert "convergence_mode" in body, (
            "refining: engine SKILL.md must document the convergence_mode field"
        )

    def test_engine_declares_scored_mode_value(self):
        """scored is a valid value for convergence_mode."""
        _, body = parse_frontmatter(self.SKILL)
        assert "scored" in body, (
            "refining: engine SKILL.md must document the scored convergence_mode value"
        )

    def test_scored_aggregator_merge_scores(self):
        """Scored aggregator must name the merge_scores operation."""
        _, body = parse_frontmatter(self.SKILL)
        assert "merge_scores" in body, (
            "refining: scored aggregator must document merge_scores operation"
        )

    def test_scored_aggregator_cap(self):
        """Scored aggregator must name the cap operation."""
        _, body = parse_frontmatter(self.SKILL)
        assert "aggregator.cap" in body, (
            "refining: scored aggregator must document aggregator.cap operation"
        )

    def test_scored_mode_threshold_and_check(self):
        """Scored loop must document threshold-AND convergence."""
        _, body = parse_frontmatter(self.SKILL)
        assert "thresholds" in body, (
            "refining: scored mode must document threshold-based convergence"
        )

    def test_scored_mode_plateau_detection(self):
        """Scored loop must document plateau detection for pivot."""
        _, body = parse_frontmatter(self.SKILL)
        assert "plateau" in body, (
            "refining: scored mode must document plateau detection"
        )

    def test_scored_mode_pivot(self):
        """Scored loop must document the pivot fix mode."""
        _, body = parse_frontmatter(self.SKILL)
        assert "pivot" in body, (
            "refining: scored mode must document the pivot fix mode"
        )

    def test_scored_mode_fixer_apply_with_mode(self):
        """Scored path: fixer.apply must accept a mode= argument."""
        _, body = parse_frontmatter(self.SKILL)
        assert "mode=fix_mode" in body or "mode=" in body, (
            "refining: scored path must call fixer.apply with a mode= argument"
        )

    def test_scored_config_block_dimensions(self):
        """Scored config block must list the five UI dimensions."""
        _, body = parse_frontmatter(self.SKILL)
        for dim in ("design_quality", "originality", "craft", "functionality", "accessibility"):
            assert dim in body, (
                f"refining: scored config block must document dimension '{dim}'"
            )

    def test_scored_config_block_max_findings(self):
        """Scored config block must document max_findings_per_cycle."""
        _, body = parse_frontmatter(self.SKILL)
        assert "max_findings_per_cycle" in body, (
            "refining: scored config must document max_findings_per_cycle"
        )

    def test_scored_config_block_plateau_window(self):
        """Scored config block must document plateau_window."""
        _, body = parse_frontmatter(self.SKILL)
        assert "plateau_window" in body, (
            "refining: scored config must document plateau_window"
        )

    def test_scored_config_block_plateau_epsilon(self):
        """Scored config block must document plateau_epsilon."""
        _, body = parse_frontmatter(self.SKILL)
        assert "plateau_epsilon" in body, (
            "refining: scored config must document plateau_epsilon"
        )

    def test_mode_branch_wraps_aggregation(self):
        """Engine must branch on convergence_mode before the aggregation step."""
        _, body = parse_frontmatter(self.SKILL)
        assert 'convergence_mode == "scored"' in body or "convergence_mode == 'scored'" in body, (
            "refining: engine must branch on convergence_mode == 'scored'"
        )

    def test_escalate_reports_best_round_in_scored_mode(self):
        """Scored ESCALATE must report the best-scoring round."""
        _, body = parse_frontmatter(self.SKILL)
        assert "best" in body, (
            "refining: ESCALATE in scored mode must reference the best-scoring round"
        )


class TestRefiningShims:
    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_shim_exists(self, name):
        assert _skill_path(name).is_file()

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_name_matches(self, name):
        fm, _ = parse_frontmatter(_skill_path(name))
        assert fm["name"] == name

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_invokes_relay_refining(self, name):
        _, body = parse_frontmatter(_skill_path(name))
        assert "relay:refining" in body, f"{name}: must invoke relay:refining"

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_names_adapter_slug(self, name):
        _, body = parse_frontmatter(_skill_path(name))
        slug = REFINING_SHIMS[name]["adapter"]
        assert slug in body, f"{name}: must name adapter slug {slug}"

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_references_critic_fixer_agents(self, name):
        _, body = parse_frontmatter(_skill_path(name))
        for ref in REFINING_SHIMS[name].get("agents", ()):
            assert ref in body, f"{name}: missing agent reference {ref}"

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_references_role_and_leaf(self, name):
        _, body = parse_frontmatter(_skill_path(name))
        for role_path, leaf in REFINING_SHIMS[name].get("roles", []):
            assert role_path in body, f"{name}: missing role reference {role_path}"
            assert leaf in body, f"{name}: missing leaf reference {leaf}"

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_no_collapsed_slug_agent_refs(self, name):
        _, body = parse_frontmatter(_skill_path(name))
        for old_ref in ("relay:spec-simulator", "relay:plan-simulator",
                        "relay:spec-fixer", "relay:plan-fixer",
                        "relay:doc-reference-reviewer"):
            assert old_ref not in body, f"{name}: collapsed slug {old_ref!r} must be absent"


# --- Task 5 (relay-ui-refine): refining-ui thin shim (scored convergence) ---

UI_SHIM_CRITICS = (
    "relay:ui-code-evaluator",
    "relay:ui-visual-evaluator",
    "relay:ui-ux-evaluator",
    "relay:ui-accessibility-evaluator",
)
UI_SHIM_DIMENSIONS = (
    "design_quality",
    "originality",
    "craft",
    "functionality",
    "accessibility",
)


class TestRefiningUIShim:
    """Structural tests for skills/refining-ui/SKILL.md — spec §7.

    The shim configures relay:refining for the UI target with scored convergence:
    - convergence_mode: scored with all 5 dimension thresholds
    - calls relay:running-web-apps pre-flight before invoking relay:refining
    - ui-code-evaluator (browser-free) dispatched in parallel: true
    - browser critics dispatched sequentially: parallel: false
    - ui-generator as fixer
    """

    SKILL = _skill_path("refining-ui")

    def test_shim_exists(self):
        """skills/refining-ui/SKILL.md must exist."""
        assert self.SKILL.is_file(), (
            "skills/refining-ui/SKILL.md missing — create the UI thin shim"
        )

    def test_name_matches(self):
        """Frontmatter name must be refining-ui."""
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm["name"] == "refining-ui", (
            "refining-ui: frontmatter name must be 'refining-ui'"
        )

    def test_user_invocable_false(self):
        """Internal skill must have user-invocable: false."""
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm.get("user-invocable") is False, (
            "refining-ui: internal skill must have user-invocable: false"
        )

    def test_announces_refinement_loop(self):
        """Shim must announce the refinement loop at start."""
        _, body = parse_frontmatter(self.SKILL)
        assert "refining-ui" in body or "UI" in body or "ui" in body, (
            "refining-ui: must announce the refinement loop"
        )
        # Announcement pattern: "I'm using..." or similar
        assert "Announce" in body or "announce" in body or "using the" in body, (
            "refining-ui: must include an announce-at-start directive"
        )

    def test_invokes_relay_refining(self):
        """Shim must invoke relay:refining."""
        _, body = parse_frontmatter(self.SKILL)
        assert "relay:refining" in body, (
            "refining-ui: must invoke relay:refining"
        )

    def test_calls_running_web_apps_preflight(self):
        """Shim must call relay:running-web-apps before invoking the engine."""
        _, body = parse_frontmatter(self.SKILL)
        assert "relay:running-web-apps" in body, (
            "refining-ui: must call relay:running-web-apps as pre-flight"
        )

    def test_names_ui_adapter(self):
        """Shim must name the ui adapter slug."""
        _, body = parse_frontmatter(self.SKILL)
        assert "adapters/ui" in body or "subject_adapter" in body, (
            "refining-ui: must reference the ui subject adapter"
        )
        assert "ui" in body, (
            "refining-ui: must name the ui adapter slug"
        )

    def test_convergence_mode_scored(self):
        """Shim must set convergence_mode: scored."""
        _, body = parse_frontmatter(self.SKILL)
        assert "convergence_mode: scored" in body, (
            "refining-ui: must set convergence_mode: scored (spec §7)"
        )

    def test_aggregator_scored(self):
        """Shim must set aggregator: scored."""
        _, body = parse_frontmatter(self.SKILL)
        assert "aggregator: scored" in body, (
            "refining-ui: must set aggregator: scored (spec §7)"
        )

    def test_ui_code_evaluator_parallel_true(self):
        """ui-code-evaluator must be dispatched with parallel: true."""
        _, body = parse_frontmatter(self.SKILL)
        # The spec §7 config block: ui-code-evaluator, parallel: true
        assert "ui-code-evaluator" in body, (
            "refining-ui: must reference relay:ui-code-evaluator"
        )
        # The parallel: true must appear after the ui-code-evaluator reference
        # We verify the config block contains both tokens; order is confirmed by presence.
        code_eval_idx = body.index("ui-code-evaluator")
        parallel_true_idx = body.index("parallel: true")
        assert code_eval_idx < parallel_true_idx, (
            "refining-ui: ui-code-evaluator must appear before the parallel: true entry"
        )

    def test_browser_critics_parallel_false(self):
        """Browser critics must be dispatched sequentially (parallel: false)."""
        _, body = parse_frontmatter(self.SKILL)
        assert "parallel: false" in body, (
            "refining-ui: browser critics must set parallel: false (spec §7)"
        )
        for critic in ("ui-visual-evaluator", "ui-ux-evaluator", "ui-accessibility-evaluator"):
            assert critic in body, (
                f"refining-ui: must reference relay:{critic}"
            )

    def test_all_five_dimension_thresholds(self):
        """Scored config block must set all 5 dimension thresholds."""
        _, body = parse_frontmatter(self.SKILL)
        for dim in UI_SHIM_DIMENSIONS:
            assert dim in body, (
                f"refining-ui: scored config must include threshold for dimension '{dim}' (spec §7)"
            )

    def test_ui_generator_as_fixer(self):
        """Shim must configure ui-generator as the fixer."""
        _, body = parse_frontmatter(self.SKILL)
        assert "ui-generator" in body, (
            "refining-ui: must configure relay:ui-generator as fixer (spec §7)"
        )

    def test_max_rounds_set(self):
        """Shim must document max_rounds (spec §7 default 10)."""
        _, body = parse_frontmatter(self.SKILL)
        assert "max_rounds" in body, (
            "refining-ui: must document max_rounds (spec §7)"
        )

    def test_scored_config_max_findings_per_cycle(self):
        """Scored config block must set max_findings_per_cycle."""
        _, body = parse_frontmatter(self.SKILL)
        assert "max_findings_per_cycle" in body, (
            "refining-ui: scored config must document max_findings_per_cycle (spec §7)"
        )

    def test_scored_config_plateau_window(self):
        """Scored config block must set plateau_window."""
        _, body = parse_frontmatter(self.SKILL)
        assert "plateau_window" in body, (
            "refining-ui: scored config must document plateau_window (spec §7)"
        )

    def test_scored_config_plateau_epsilon(self):
        """Scored config block must set plateau_epsilon."""
        _, body = parse_frontmatter(self.SKILL)
        assert "plateau_epsilon" in body, (
            "refining-ui: scored config must document plateau_epsilon (spec §7)"
        )

    def test_body_nonempty(self):
        """Shim body must have substantial content."""
        _, body = parse_frontmatter(self.SKILL)
        assert len(body) > 200, "refining-ui: body too short"


class TestRefiningUILeafDispatch:
    """Post-migration: refining-ui must dispatch via leaf agents, not direct relay:ui-* agentTypes."""

    SKILL = _skill_path("refining-ui")

    def test_ui_evaluators_dispatched_via_leaf_reader(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "relay:leaf-reader" in body, "refining-ui must dispatch evaluators via relay:leaf-reader"

    def test_ui_generator_dispatched_via_leaf_worker(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "relay:leaf-worker" in body, "refining-ui must dispatch ui-generator via relay:leaf-worker"

    def test_roles_ui_paths_in_body(self):
        _, body = parse_frontmatter(self.SKILL)
        for slug in ("ui-visual-evaluator", "ui-ux-evaluator",
                     "ui-accessibility-evaluator", "ui-code-evaluator", "ui-generator"):
            assert f"roles/{slug}.md" in body, f"refining-ui: must reference roles/{slug}.md"

    def test_playwright_preflight_check(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "npx playwright --version" in body or "playwright" in body.lower()

    def test_no_direct_ui_agent_agenttype_refs(self):
        _, body = parse_frontmatter(self.SKILL)
        for old in ("relay:ui-visual-evaluator", "relay:ui-ux-evaluator",
                    "relay:ui-accessibility-evaluator", "relay:ui-generator"):
            assert old not in body, f"refining-ui: {old!r} must not appear as agentType"


# Task 28 — bindings/presets.yaml gate (b) + dispatch skills.
import os

PRESETS_PATH = PLUGIN_ROOT / "bindings" / "presets.yaml"
VALID_MECHANISMS = {"in-session", "acpx-claude", "codex-session"}
# Roles that MUST be acpx-dispatched (non-in-session) so --engine acpx is not a no-op
# for the bulk of the implement pipeline.
ACPX_PIPELINE_ROLES = {"implementer", "test-writer", "fix-coder", "plan-writer"}


def _load_presets():
    import yaml as _yaml

    return _yaml.safe_load(PRESETS_PATH.read_text())


# 4.48.0: every L3 command's Step 0 collapsed into one call to
# scripts/l3-preflight.sh. `refine` and `execute` share one `refine|execute)`
# case label; every other command owns its own label.
_L3_CASE_LABEL = {
    "implement": "implement",
    "verify": "verify",
    "refine": "refine|execute",
    "execute": "refine|execute",
    "drive": "drive",
}


def _l3_case_block(script_text, name):
    """The body of scripts/l3-preflight.sh's case block for one L3 command name,
    or None when the label is not found."""
    label = _L3_CASE_LABEL[name]
    m = re.search(
        r"  " + re.escape(label) + r"\)\n(.*?)\n    ;;", script_text, re.S
    )
    return m.group(1) if m else None


class TestBindings:
    def test_presets_parses_and_has_roles(self):
        assert PRESETS_PATH.is_file(), "bindings/presets.yaml missing"
        data = _load_presets()
        assert isinstance(data, dict)
        assert isinstance(data.get("roles"), dict), "top-level roles: mapping required"
        assert data["roles"], "roles: mapping must be non-empty"

    def test_every_role_resolves(self):
        """Each binding resolves per §5 order: roles/<slug>.md OR agents/<slug>.md for registered."""
        import yaml as _yaml
        roles = _load_presets()["roles"]
        missing = []
        for slug, entry in roles.items():
            rc = entry.get("role-class")
            if rc == "registered":
                if not _agent_path(slug).is_file():
                    missing.append(f"{slug}: role-class=registered but agents/{slug}.md absent")
            else:
                roles_path = PLUGIN_ROOT / "roles" / f"{slug}.md"
                if not roles_path.is_file():
                    missing.append(f"{slug}: no roles/{slug}.md (role-class={rc})")
        assert not missing, f"binding resolution failures: {missing}"

    def test_required_fields_and_mechanism_enum(self):
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            assert isinstance(entry, dict), f"{slug}: entry not a mapping"
            assert "mechanism" in entry, f"{slug}: missing required field mechanism"
            assert "provides" in entry, f"{slug}: missing required field provides"
            assert entry["mechanism"] in VALID_MECHANISMS, (
                f"{slug}: mechanism {entry['mechanism']!r} not in {VALID_MECHANISMS}"
            )

    def test_provides_matches_output_tokens(self):
        """set(provides) == set(role frontmatter output-tokens) for role-backed bindings;
        for registered bindings, provides == relay.envelope_tokens from agents/<slug>.md."""
        import yaml as _yaml
        roles = _load_presets()["roles"]
        mismatches = []
        for slug, entry in roles.items():
            provides = set(entry.get("provides") or [])
            rc = entry.get("role-class")
            if rc == "registered":
                fm, _ = parse_frontmatter(_agent_path(slug))
                envelope = set((fm.get("relay") or {}).get("envelope_tokens") or [])
                if provides != envelope:
                    mismatches.append((slug, sorted(provides), sorted(envelope)))
            else:
                roles_path = PLUGIN_ROOT / "roles" / f"{slug}.md"
                if roles_path.is_file():
                    text = roles_path.read_text()
                    end = text.index("---", 3)
                    rfm = _yaml.safe_load(text[3:end]) or {}
                    tokens = set(rfm.get("output-tokens") or [])
                    if provides != tokens:
                        mismatches.append((slug, sorted(provides), sorted(tokens)))
        assert not mismatches, f"provides != output-tokens: {mismatches}"

    def test_acpx_preset_exercises_out_of_session(self):
        # Per-role binding: the implement-pipeline roles must bind to a non-in-session
        # mechanism (acpx-claude / codex-session), independent of any pipeline preset.
        roles = _load_presets()["roles"]
        offenders = sorted(
            s for s in ACPX_PIPELINE_ROLES
            if roles.get(s, {}).get("mechanism") == "in-session"
        )
        assert not offenders, (
            f"pipeline roles must be acpx-dispatched (non-in-session): {offenders}"
        )


class TestRefineEngineAxisPresets:
    def test_pr_refinement_eligibility(self):
        roles = _load_presets()["roles"]
        assert roles["code-reviewer"]["delegate_eligible"] is True
        assert roles["doc-reference-reviewer"]["delegate_eligible"] is True
        assert roles["server-runner"]["delegate_eligible"] is False
        # ui-code-evaluator + ui-generator are eligible (source-only: no browser,
        # no screenshot vision), so /relay:refine --target ui --engine acpx can
        # delegate its fixer and code critic. The three browser critics stay
        # in-session — ui-visual-evaluator must READ rendered screenshots.
        assert roles["ui-code-evaluator"]["delegate_eligible"] is True
        assert roles["ui-generator"]["delegate_eligible"] is True
        assert roles["ui-visual-evaluator"]["delegate_eligible"] is False
        eligible_count = sum(
            entry.get("delegate_eligible") is True for entry in roles.values()
        )
        assert eligible_count == 12


# Per-modality model/effort schema (the claude/codex/opencode/hybrid blocks).
MODALITY_EFFORTS = {"low", "medium", "high", "xhigh"}
CODEX_MODELS = {"gpt-5.6-sol", "gpt-5.6-terra"}
# Opencode models are provider-qualified: the `opencode-go/` prefix pins the
# serving provider (OpenCode Go subscription) — opencode resolves the provider
# from the model-id prefix, so no other connected provider can serve these.
OPENCODE_MODELS = {
    "opencode-go/kimi-k2.7-code",
    "opencode-go/kimi-k2.6",
}
# Slot alignment: each opencode model mirrors a codex tier (sol/terra).
# The luna slot and its `opencode-go/minimax-m3` mirror retired together in
# 4.45.0 — this map is a bijection, so a tier cannot retire on one engine only.
CODEX_TIER_TO_OPENCODE = {
    "gpt-5.6-sol": "opencode-go/kimi-k2.7-code",
    "gpt-5.6-terra": "opencode-go/kimi-k2.6",
}


class TestModalities:
    """Every role carries a well-formed modalities block (claude/codex/opencode/hybrid)."""

    def test_every_role_has_four_modalities(self):
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            mods = entry.get("modalities")
            assert isinstance(mods, dict), f"{slug}: missing modalities block"
            for key in ("claude", "codex", "opencode", "hybrid"):
                assert key in mods, f"{slug}: modalities missing {key}"

    def test_claude_modality_is_opus_with_valid_effort(self):
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            claude = entry["modalities"]["claude"]
            assert claude.get("model") == "opus", f"{slug}: claude model must be opus"
            assert claude.get("effort") in MODALITY_EFFORTS, (
                f"{slug}: claude effort {claude.get('effort')!r} not in {MODALITY_EFFORTS}"
            )

    def test_codex_modality_model_and_effort(self):
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            codex = entry["modalities"]["codex"]
            assert codex.get("model") in CODEX_MODELS, (
                f"{slug}: codex model {codex.get('model')!r} not in {CODEX_MODELS}"
            )
            assert codex.get("effort") in MODALITY_EFFORTS, (
                f"{slug}: codex effort {codex.get('effort')!r} not in {MODALITY_EFFORTS}"
            )

    def test_opencode_modality_model_pinned_to_go_provider(self):
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            opencode = entry["modalities"]["opencode"]
            model = opencode.get("model")
            assert model in OPENCODE_MODELS, (
                f"{slug}: opencode model {model!r} not in {OPENCODE_MODELS}"
            )
            assert model.startswith("opencode-go/"), (
                f"{slug}: opencode model {model!r} must be provider-pinned "
                f"(opencode-go/ prefix routes to the Go subscription)"
            )
            # Open-weight models define no acpx effort values (ACP -32602 on
            # `set effort`); the modality omits the key and the driver
            # soft-degrades to the model's default reasoning.
            assert "effort" not in opencode, (
                f"{slug}: opencode modality must not carry an effort key"
            )

    def test_opencode_model_mirrors_codex_tier(self):
        """The opencode ladder tracks the codex sol/terra slot per role, so
        the simulator one-hop-mirror rule and slot assignments stay aligned
        across engines automatically."""
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            codex_model = entry["modalities"]["codex"]["model"]
            expected = CODEX_TIER_TO_OPENCODE[codex_model]
            actual = entry["modalities"]["opencode"]["model"]
            assert actual == expected, (
                f"{slug}: codex tier {codex_model} should map to {expected}, "
                f"got {actual}"
            )

    def test_hybrid_engine_consistent_with_mechanism(self):
        # hybrid.engine is the per-role default engine; it MUST agree with the
        # role's `mechanism` (codex => codex-session; claude => in-session|acpx-claude),
        # so /relay:implement acpx (hybrid default) dispatches on the right engine.
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            engine = entry["modalities"]["hybrid"].get("engine")
            assert engine in ("claude", "codex"), (
                f"{slug}: hybrid.engine {engine!r} not in (claude, codex)"
            )
            mech = entry["mechanism"]
            if engine == "codex":
                assert mech == "codex-session", (
                    f"{slug}: hybrid.engine=codex but mechanism={mech!r}"
                )
            else:
                assert mech in ("in-session", "acpx-claude"), (
                    f"{slug}: hybrid.engine=claude but mechanism={mech!r}"
                )


# The 8 codex/opencode session-driver.sh env vars (6 required + 2 in-driver-defaulted).
# Multi-turn vars (ACPX_MAX_TURNS, ACPX_NUDGE_PROMPT) and the sessions-close trap
# moved to the delegate-and-watch watcher (L2 skill). Drivers are now single-turn.
CODEX_DRIVER_REQUIRED_VARS = (
    "ACPX_ENGINE",
    "ACPX_MODEL",
    "ACPX_CWD",
    "ACPX_TIMEOUT",
    "ACPX_SESSION_NAME",
    "ACPX_PROMPT_FILE",
)
CODEX_DRIVER_DEFAULTED_VARS = (
    "ACPX_TERMINAL_TOKEN",
    "ACPX_VERIFY_ARTIFACT",
)
ACPX_SKILL_DIR = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents"
ACPX_SHIPPED_FILES = (
    "acpx-dispatch.sh",
    "codex-session-driver.sh",
    "parse-turn-protocol.sh",
    "preamble.md",
)


class TestDispatchSkills:
    IN_SESSION = _skill_path("dispatching-in-session-agents")
    ACPX = _skill_path("dispatching-acpx-agents")

    def test_both_skill_files_exist(self):
        assert self.IN_SESSION.is_file()
        assert self.ACPX.is_file()

    @pytest.mark.parametrize("name", ["dispatching-in-session-agents", "dispatching-acpx-agents"])
    def test_valid_frontmatter(self, name):
        fm, _ = parse_frontmatter(_skill_path(name))
        assert fm.get("name") == name
        assert "description" in fm

    @pytest.mark.parametrize("fname", ACPX_SHIPPED_FILES)
    def test_acpx_ships_files(self, fname):
        assert (ACPX_SKILL_DIR / fname).is_file(), f"dispatching-acpx-agents missing {fname}"

    @pytest.mark.parametrize("fname", ["acpx-dispatch.sh", "codex-session-driver.sh", "parse-turn-protocol.sh"])
    def test_scripts_executable(self, fname):
        assert os.access(ACPX_SKILL_DIR / fname, os.X_OK), f"{fname} not executable"

    @pytest.mark.parametrize("fname", ["acpx-dispatch.sh", "codex-session-driver.sh", "parse-turn-protocol.sh"])
    def test_scripts_syntax_ok(self, fname):
        result = subprocess.run(
            ["bash", "-n", str(ACPX_SKILL_DIR / fname)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{fname} bash -n failed:\n{result.stderr}"

    def test_acpx_skill_documents_v2_candidate_note(self):
        _, body = parse_frontmatter(self.ACPX)
        assert "codex-session-driver.sh" in body
        # v2-candidate note: merge into acpx-dispatch.sh or upstream to ACPX.
        assert "v2" in body.lower()
        assert ("merg" in body.lower()) or ("upstream" in body.lower())

    def test_acpx_skill_documents_driver_var_contract(self):
        # codex/opencode: 8 vars (6 required + 2 defaulted).
        # claude/opencode: 10 vars (8 + ACPX_EFFORT + ACPX_PERMISSIONS).
        _, body = parse_frontmatter(self.ACPX)
        for var in CODEX_DRIVER_REQUIRED_VARS:
            assert var in body, f"acpx SKILL.md missing required env var {var}"
        for var in CODEX_DRIVER_DEFAULTED_VARS:
            assert var in body, f"acpx SKILL.md missing defaulted env var {var}"
        # ACPX_EFFORT and ACPX_PERMISSIONS are the two claude/opencode-only extras.
        assert "ACPX_EFFORT" in body, "acpx SKILL.md missing claude extra var ACPX_EFFORT"
        assert "ACPX_PERMISSIONS" in body, "acpx SKILL.md missing claude extra var ACPX_PERMISSIONS"
        # documents that the optional vars are caller-optional (defaulted in-driver)
        assert "default" in body.lower()
        # ACPX_MAX_TURNS and ACPX_NUDGE_PROMPT must NOT appear as driver vars
        # (moved to delegate-and-watch watcher).
        assert "ACPX_MAX_TURNS" not in body, (
            "acpx SKILL.md must not document ACPX_MAX_TURNS as a driver var "
            "(moved to delegate-and-watch watcher)"
        )
        assert "ACPX_NUDGE_PROMPT" not in body, (
            "acpx SKILL.md must not document ACPX_NUDGE_PROMPT as a driver var "
            "(moved to delegate-and-watch watcher)"
        )

    def test_in_session_documents_binding_resolution(self):
        _, body = parse_frontmatter(self.IN_SESSION)
        # (a) binding override precedence, (b) preamble prepend, (c) token capture.
        assert "presets.yaml" in body
        assert "preamble" in body.lower()
        assert "envelope" in body.lower() or "token" in body.lower()
        assert "frontmatter" in body.lower()

    def test_preamble_documents_both_autonomy_modes(self):
        """preamble.md must document both the fire-and-forget autonomy mode
        ('decide, never ask') and the interactive mode (AUTONOMY=interactive).
        Both modes must be flip-selectable so the dispatching orchestrator can choose
        the appropriate posture for each delegation.
        """
        preamble = ACPX_SKILL_DIR / "preamble.md"
        assert preamble.is_file(), "preamble.md must exist"
        text = preamble.read_text()
        assert "decide, never ask" in text, (
            "preamble.md must document the fire-and-forget autonomy mode "
            "('decide, never ask')"
        )
        assert "AUTONOMY=interactive" in text, (
            "preamble.md must document the interactive autonomy mode "
            "('AUTONOMY=interactive')"
        )

    def test_parse_turn_protocol_role_frontmatter(self, tmp_path):
        """Parser reads verify_artifact from role file YAML frontmatter (post-migration §6)."""
        script = ACPX_SKILL_DIR / "parse-turn-protocol.sh"
        role_with_va = tmp_path / "implementer.md"
        role_with_va.write_text(
            "---\n"
            "role-version: 1\n"
            "description: implementer role\n"
            "role-class: writer\n"
            'verify_artifact: "{{REPO_ROOT}}"\n'
            "output-tokens: [ROLE_DONE]\n"
            "terminal_token: ROLE_DONE\n"
            "requires: [run_bash]\n"
            "---\n\nbody\n"
        )
        out = subprocess.run(
            ["bash", "-c",
             f'source "{script}"; SLOT_REPO_ROOT=/tmp/repo parse_turn_protocol "{role_with_va}"; '
             'echo "TT=$TP_TERMINAL_TOKEN"; echo "VA=$TP_VERIFY_ARTIFACT"'],
            capture_output=True, text=True,
        )
        assert out.returncode == 0
        assert "TT=ROLE_DONE" in out.stdout
        assert "VA=/tmp/repo" in out.stdout


class TestDispatchSkillsResolution:
    """§10.5: derivation table appears in docs + both dispatch skills."""

    def test_derivation_table_in_dispatch_in_session(self):
        _, body = parse_frontmatter(_skill_path("dispatching-in-session-agents"))
        assert "relay:leaf-worker" in body
        assert "relay:leaf-reader" in body
        assert "role-class" in body

    def test_derivation_table_in_dispatch_acpx(self):
        _, body = parse_frontmatter(_skill_path("dispatching-acpx-agents"))
        assert "relay:leaf-worker" in body
        assert "relay:leaf-reader" in body
        assert "role-class" in body

    def test_in_session_uses_resolution_order(self):
        _, body = parse_frontmatter(_skill_path("dispatching-in-session-agents"))
        assert "roles/" in body, "in-session dispatch must reference roles/ resolution"
        assert "agents/" in body, "in-session dispatch must still reference agents/ for kept agents"

    def test_acpx_uses_resolution_order(self):
        _, body = parse_frontmatter(_skill_path("dispatching-acpx-agents"))
        assert "roles/" in body


class TestThinnedDriverNoTrap:
    """Gate: thinned session drivers must not own the sessions-close trap.

    The sessions-close cleanup trap moved to the delegate-and-watch watcher (L2 skill).
    Thin single-turn drivers must NOT register it themselves.
    """

    @pytest.mark.parametrize("fname", [
        "codex-session-driver.sh",
        "claude-session-driver.sh",
        "opencode-session-driver.sh",
    ])
    def test_driver_has_no_sessions_close_trap(self, fname):
        text = (ACPX_SKILL_DIR / fname).read_text()
        assert "sessions close" not in text, (
            f"{fname}: sessions-close trap must be absent from thinned driver "
            "(moved to delegate-and-watch watcher)"
        )

    @pytest.mark.parametrize("fname", [
        "codex-session-driver.sh",
        "claude-session-driver.sh",
        "opencode-session-driver.sh",
    ])
    def test_driver_has_no_acpx_max_turns(self, fname):
        text = (ACPX_SKILL_DIR / fname).read_text()
        assert "ACPX_MAX_TURNS" not in text, (
            f"{fname}: ACPX_MAX_TURNS must be absent from thinned driver "
            "(moved to delegate-and-watch watcher)"
        )

    @pytest.mark.parametrize("fname", [
        "codex-session-driver.sh",
        "claude-session-driver.sh",
        "opencode-session-driver.sh",
    ])
    def test_driver_has_no_acpx_nudge_prompt(self, fname):
        text = (ACPX_SKILL_DIR / fname).read_text()
        assert "ACPX_NUDGE_PROMPT" not in text, (
            f"{fname}: ACPX_NUDGE_PROMPT must be absent from thinned driver "
            "(moved to delegate-and-watch watcher)"
        )

    @pytest.mark.parametrize("fname", [
        "codex-session-driver.sh",
        "claude-session-driver.sh",
        "opencode-session-driver.sh",
    ])
    def test_driver_syntax_ok(self, fname):
        result = subprocess.run(
            ["bash", "-n", str(ACPX_SKILL_DIR / fname)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{fname} bash -n failed:\n{result.stderr}"

    @pytest.mark.parametrize("fname", [
        "codex-session-driver.sh",
        "claude-session-driver.sh",
        "opencode-session-driver.sh",
    ])
    def test_driver_references_turn_log(self, fname):
        """Phase D2 two-log contract: driver must reference turn.log (the turn-content channel).

        The driver must write full turn stdout to ~/.acpx/sessions/${session}.turn.log
        (the dedicated content channel the watcher reads at each turn boundary).
        The driver.log carries metadata only (timestamp/rc/reply_bytes).
        """
        text = (ACPX_SKILL_DIR / fname).read_text()
        assert "turn.log" in text, (
            f"{fname}: must write full turn stdout to ${{session}}.turn.log "
            "(Phase D2 two-log contract: turn-content channel for the watcher)"
        )


def _json_chunk(text):
    """One ACP `agent_message_chunk` line carrying `text`.

    The drivers read `--format json --json-strict` output through acpx-envelope.sh,
    so every fake acpx in this file emits chunks rather than bare text.
    """
    import json as _json

    return _json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "s1",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "messageId": "m1",
                    "content": {"type": "text", "text": text},
                    "_meta": None,
                },
            },
        },
        separators=(",", ":"),
    )


class TestThinnedDriverTurnLogWrite:
    """Behavioral gate: each thinned driver must actually write the turn reply to turn.log.

    The spec (Phase D2) requires the driver to capture the full turn stdout into a
    dedicated content log file at ~/.acpx/sessions/${session}.turn.log. This class
    asserts the file is created and contains the expected content — not just that the
    driver *mentions* turn.log in source.
    """

    def _make_fake_acpx_with_reply(self, tmp_path, reply="ROLE_DONE"):
        """Fake acpx that emits `reply` as an ACP message chunk on a turn.

        Since 4.51.0 every acpx call runs under `--format json --json-strict` and the
        drivers rebuild the reply with acpx-envelope.sh, so the fake emits the raw
        JSON-RPC stream rather than bare text.
        """
        import stat as _stat
        log_file = tmp_path / "acpx.calls.log"
        fake = tmp_path / "acpx"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'printf \'%s\\\\n\' "$@" >> {log_file}\n'
            "for arg in \"$@\"; do\n"
            "    case \"$arg\" in\n"
            "        sessions) exit 0 ;;\n"
            "        set) exit 0 ;;\n"
            "    esac\n"
            "done\n"
            "printf '%s\\n' '" + _json_chunk(reply) + "'\n"
            "exit 0\n"
        )
        fake.chmod(fake.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
        return fake

    def _make_prompt(self, tmp_path):
        pf = tmp_path / "prompt.md"
        pf.write_text("<<DO_NOT_LOAD_SKILLS>>\ndo the thing\n")
        return pf

    @pytest.mark.parametrize("fname,extra_env", [
        ("codex-session-driver.sh", {"ACPX_EFFORT": "high"}),
        ("claude-session-driver.sh", {"ACPX_EFFORT": "high", "ACPX_PERMISSIONS": ""}),
        ("opencode-session-driver.sh", {"ACPX_EFFORT": "medium", "ACPX_PERMISSIONS": ""}),
    ])
    def test_driver_writes_turn_log(self, tmp_path, fname, extra_env):
        """Driver must write the turn reply to ~/.acpx/sessions/${session}.turn.log."""
        import os as _os
        fake_acpx = self._make_fake_acpx_with_reply(tmp_path, reply="ROLE_DONE")
        prompt = self._make_prompt(tmp_path)
        session_name = f"run-turnlog-{fname.replace('.sh', '')}"
        env = {
            **_os.environ,
            "PATH": f"{tmp_path}:{_os.environ['PATH']}",
            "HOME": str(tmp_path),
            "ACPX_ENGINE": "codex" if "codex" in fname else ("claude" if "claude" in fname else "opencode"),
            # A plain adapter-advertised id: acpx >= 0.12.0 rejects the bracket form,
            # and since 4.51.0 the codex driver applies effort via session config.
            "ACPX_MODEL": "gpt-5.6-terra" if "codex" in fname else "opus",
            "ACPX_CWD": str(tmp_path),
            "ACPX_TIMEOUT": "60",
            "ACPX_SESSION_NAME": session_name,
            "ACPX_PROMPT_FILE": str(prompt),
            "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
            "ACPX_VERIFY_ARTIFACT": "",
            **extra_env,
        }
        result = subprocess.run(
            ["bash", str(ACPX_SKILL_DIR / fname)], env=env,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"{fname} exited non-zero:\nstdout:{result.stdout}\nstderr:{result.stderr}"
        )
        turn_log = tmp_path / ".acpx" / "sessions" / f"{session_name}.turn.log"
        assert turn_log.exists(), (
            f"{fname}: turn.log must be created at {turn_log} "
            "(Phase D2 two-log contract: thinned driver writes full turn stdout here)"
        )
        content = turn_log.read_text()
        assert "ROLE_DONE" in content, (
            f"{fname}: turn.log must contain the turn reply (found: {content!r})"
        )


class TestThinnedDriverResultStates:
    """Gate: thinned session drivers emit ROLE_RESULT=NOT_DONE and ROLE_RESULT=ERRORED correctly.

    These are the two new result states introduced by the thin-driver redesign:
    - NOT_DONE: terminal token absent, rc=0, reply non-empty — watcher decides re-dispatch.
    - ERRORED: rc!=0 AND empty reply — unrecoverable driver error.

    Both states are primary new observables that the delegate-and-watch watcher keys on.
    """

    def _make_fake_acpx_no_token(self, tmp_path, reply="some output but no token"):
        """Fake acpx that returns reply text without the terminal token."""
        log_file = tmp_path / "acpx.calls.log"
        fake = tmp_path / "acpx"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'printf \'%s\\\\n\' "$@" >> {log_file}\n'
            "for arg in \"$@\"; do\n"
            "    case \"$arg\" in\n"
            "        sessions) exit 0 ;;\n"
            "        set) exit 0 ;;\n"
            "    esac\n"
            "done\n"
            # Turn invocation — emit reply without terminal token
            "printf '%s\\n' '" + _json_chunk(reply) + "'\n"
            "exit 0\n"
        )
        import stat as _stat
        fake.chmod(fake.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
        return fake, log_file

    def _make_fake_acpx_fail_empty(self, tmp_path):
        """Fake acpx that fails with rc=1 and emits no output (ERRORED condition)."""
        log_file = tmp_path / "acpx.calls.log"
        fake = tmp_path / "acpx"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'printf \'%s\\\\n\' "$@" >> {log_file}\n'
            "for arg in \"$@\"; do\n"
            "    case \"$arg\" in\n"
            "        sessions) exit 0 ;;\n"
            "        set) exit 0 ;;\n"
            "    esac\n"
            "done\n"
            # Turn invocation — emit nothing and fail
            "exit 1\n"
        )
        import stat as _stat
        fake.chmod(fake.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
        return fake, log_file

    def _make_prompt(self, tmp_path):
        pf = tmp_path / "prompt.md"
        pf.write_text("<<DO_NOT_LOAD_SKILLS>>\ndo the thing\n")
        return pf

    @pytest.mark.parametrize("fname,extra_env", [
        ("codex-session-driver.sh", {"ACPX_EFFORT": "high"}),
        ("claude-session-driver.sh", {"ACPX_EFFORT": "high", "ACPX_PERMISSIONS": ""}),
        ("opencode-session-driver.sh", {"ACPX_EFFORT": "medium", "ACPX_PERMISSIONS": ""}),
    ])
    def test_not_done_when_token_absent_no_error(self, tmp_path, fname, extra_env):
        """Token absent, rc=0, reply non-empty → ROLE_RESULT=NOT_DONE."""
        import os as _os
        fake_acpx, log_file = self._make_fake_acpx_no_token(tmp_path, reply="partial progress")
        prompt = self._make_prompt(tmp_path)
        session_name = f"run-notdone-{fname}"
        env = {
            **_os.environ,
            "PATH": f"{tmp_path}:{_os.environ['PATH']}",
            "HOME": str(tmp_path),
            "ACPX_ENGINE": "codex" if "codex" in fname else ("claude" if "claude" in fname else "opencode"),
            # A plain adapter-advertised id: acpx >= 0.12.0 rejects the bracket form,
            # and since 4.51.0 the codex driver applies effort via session config.
            "ACPX_MODEL": "gpt-5.6-terra" if "codex" in fname else "opus",
            "ACPX_CWD": str(tmp_path),
            "ACPX_TIMEOUT": "60",
            "ACPX_SESSION_NAME": session_name,
            "ACPX_PROMPT_FILE": str(prompt),
            "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
            "ACPX_VERIFY_ARTIFACT": "",
            **extra_env,
        }
        result = subprocess.run(
            ["bash", str(ACPX_SKILL_DIR / fname)], env=env,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"{fname} NOT_DONE path should exit 0:\nstdout:{result.stdout}\nstderr:{result.stderr}"
        )
        assert "ROLE_RESULT=NOT_DONE" in result.stdout, (
            f"{fname}: expected ROLE_RESULT=NOT_DONE when token absent and rc=0:\n{result.stdout}"
        )
        assert "TURNS_USED=1" in result.stdout, (
            f"{fname}: expected TURNS_USED=1:\n{result.stdout}"
        )

    @pytest.mark.parametrize("fname,extra_env", [
        ("codex-session-driver.sh", {"ACPX_EFFORT": "high"}),
        ("claude-session-driver.sh", {"ACPX_EFFORT": "high", "ACPX_PERMISSIONS": ""}),
        ("opencode-session-driver.sh", {"ACPX_EFFORT": "medium", "ACPX_PERMISSIONS": ""}),
    ])
    def test_errored_when_rc_nonzero_and_empty_reply(self, tmp_path, fname, extra_env):
        """rc!=0 AND empty reply → ROLE_RESULT=ERRORED; driver exits with that rc."""
        import os as _os
        fake_acpx, log_file = self._make_fake_acpx_fail_empty(tmp_path)
        prompt = self._make_prompt(tmp_path)
        session_name = f"run-errored-{fname}"
        env = {
            **_os.environ,
            "PATH": f"{tmp_path}:{_os.environ['PATH']}",
            "HOME": str(tmp_path),
            "ACPX_ENGINE": "codex" if "codex" in fname else ("claude" if "claude" in fname else "opencode"),
            # A plain adapter-advertised id: acpx >= 0.12.0 rejects the bracket form,
            # and since 4.51.0 the codex driver applies effort via session config.
            "ACPX_MODEL": "gpt-5.6-terra" if "codex" in fname else "opus",
            "ACPX_CWD": str(tmp_path),
            "ACPX_TIMEOUT": "60",
            "ACPX_SESSION_NAME": session_name,
            "ACPX_PROMPT_FILE": str(prompt),
            "ACPX_TERMINAL_TOKEN": "ROLE_DONE",
            "ACPX_VERIFY_ARTIFACT": "",
            **extra_env,
        }
        result = subprocess.run(
            ["bash", str(ACPX_SKILL_DIR / fname)], env=env,
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            f"{fname} ERRORED path should exit non-zero:\nstdout:{result.stdout}\nstderr:{result.stderr}"
        )
        assert "ROLE_RESULT=ERRORED" in result.stdout, (
            f"{fname}: expected ROLE_RESULT=ERRORED when rc!=0 and reply empty:\n{result.stdout}"
        )
        assert "TURNS_USED=1" in result.stdout, (
            f"{fname}: expected TURNS_USED=1:\n{result.stdout}"
        )


class TestSidecarEnvFile:
    """Gate: acpx-dispatch.sh must write the ${session}.env sidecar before invoking the driver.

    The sidecar carries the fully-resolved env-var contract:
    - 8 vars for codex/opencode (ACPX_ENGINE, ACPX_MODEL, ACPX_CWD, ACPX_TIMEOUT,
      ACPX_SESSION_NAME, ACPX_PROMPT_FILE, ACPX_TERMINAL_TOKEN, ACPX_VERIFY_ARTIFACT)
    - 10 vars for claude (8 above + ACPX_EFFORT, ACPX_PERMISSIONS)

    The delegate-and-watch watcher sources this sidecar at entry instead of re-deriving
    those values from the binding.
    """

    import shutil as _shutil
    _TOOLING_MISSING = _shutil.which("yq") is None or _shutil.which("jq") is None

    DISPATCH_SCRIPT = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh"

    def _make_fake_driver(self, tmp_path, exit_code=0):
        """Fake driver: writes env snapshot to a log and exits."""
        import stat as _stat
        script = tmp_path / "fake_driver.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "echo ROLE_RESULT=DONE\n"
            "echo TURNS_USED=1\n"
            "echo ROLE_DONE\n"
            f"exit {exit_code}\n"
        )
        script.chmod(script.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
        return script

    @pytest.mark.skipif(
        not (Path(__file__).parents[3] / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh").is_file()
        or __import__("shutil").which("yq") is None
        or __import__("shutil").which("jq") is None,
        reason="acpx-dispatch.sh or yq/jq not available"
    )
    def test_codex_sidecar_written_with_the_driver_contract(self, tmp_path):
        """codex-session dispatch writes the driver's sidecar before invoking it."""
        import json as _json
        import os as _os
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_driver = self._make_fake_driver(tmp_path)

        # Use a binding with verify_artifact so it routes to the driver path
        # (the fast path skips the driver; we need the driver path for the sidecar).
        # Provide TP_VERIFY_ARTIFACT directly via env so parse-turn-protocol is bypassed.
        env = {
            **_os.environ,
            "ACPX_ROLE_SLUG": "implementer",
            "ACPX_BINDING_PRESET": "implementer",
            "ACPX_INPUTS_JSON": _json.dumps(
                {"task_text": "do the thing", "repo_root": str(worktree)}
            ),
            "ACPX_RUN_ID": "run-sidecar-codex",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
            # Force the driver path by providing a verify_artifact value.
            "TP_VERIFY_ARTIFACT": str(worktree / "out.txt"),
            "TP_TERMINAL_TOKEN": "ROLE_DONE",
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            ["bash", str(self.DISPATCH_SCRIPT)], env=env,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"dispatch failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
        )
        session_name = "run-sidecar-codex-implementer"
        sidecar = tmp_path / ".acpx" / "sessions" / f"{session_name}.env"
        assert sidecar.is_file(), (
            f"sidecar {sidecar} must be written before the driver is invoked; "
            f"stderr:\n{result.stderr}"
        )
        content = sidecar.read_text()
        codex_vars = [
            "ACPX_ENGINE", "ACPX_MODEL", "ACPX_CWD", "ACPX_TIMEOUT",
            "ACPX_SESSION_NAME", "ACPX_PROMPT_FILE",
            "ACPX_TERMINAL_TOKEN", "ACPX_VERIFY_ARTIFACT",
            # 4.51.0: the codex driver applies effort itself via `set reasoning_effort`,
            # so it now needs the value, and every driver needs the policy path.
            "ACPX_EFFORT", "ACPX_POLICY_FILE",
        ]
        for var in codex_vars:
            assert var in content, (
                f"codex sidecar missing var {var}:\n{content}"
            )
        # CODEX_CONFIG stays for one release so a watcher still running the 4.50.0
        # contract sources this file cleanly; the driver no longer reads it.
        assert "CODEX_CONFIG" in content, (
            f"codex sidecar must keep CODEX_CONFIG for one release:\n{content}"
        )
        # ACPX_PERMISSIONS is a claude/opencode field and never applied to codex.
        assert "ACPX_PERMISSIONS" not in content, (
            f"codex sidecar must not contain ACPX_PERMISSIONS (claude-only):\n{content}"
        )

    @pytest.mark.skipif(
        not (Path(__file__).parents[3] / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh").is_file()
        or __import__("shutil").which("yq") is None
        or __import__("shutil").which("jq") is None,
        reason="acpx-dispatch.sh or yq/jq not available"
    )
    def test_claude_sidecar_written_with_10_vars(self, tmp_path):
        """acpx-claude dispatch writes a 10-var sidecar before invoking the driver."""
        import json as _json
        import os as _os
        worktree = tmp_path / "wt"
        worktree.mkdir()
        fake_driver = self._make_fake_driver(tmp_path)

        env = {
            **_os.environ,
            "ACPX_ROLE_SLUG": "code-reviewer",
            "ACPX_BINDING_PRESET": "code-reviewer",
            "ACPX_INPUTS_JSON": "{}",
            "ACPX_RUN_ID": "run-sidecar-claude",
            "WORKTREE": str(worktree),
            "DRIVER_OVERRIDE": str(fake_driver),
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            ["bash", str(self.DISPATCH_SCRIPT)], env=env,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"dispatch failed:\nstdout:{result.stdout}\nstderr:{result.stderr}"
        )
        session_name = "run-sidecar-claude-code-reviewer"
        sidecar = tmp_path / ".acpx" / "sessions" / f"{session_name}.env"
        assert sidecar.is_file(), (
            f"sidecar {sidecar} must be written before the driver is invoked; "
            f"stderr:\n{result.stderr}"
        )
        content = sidecar.read_text()
        # 10 required vars for claude (8 base + ACPX_EFFORT + ACPX_PERMISSIONS)
        claude_vars = [
            "ACPX_ENGINE", "ACPX_MODEL", "ACPX_CWD", "ACPX_TIMEOUT",
            "ACPX_SESSION_NAME", "ACPX_PROMPT_FILE",
            "ACPX_TERMINAL_TOKEN", "ACPX_VERIFY_ARTIFACT",
            "ACPX_EFFORT", "ACPX_PERMISSIONS",
        ]
        for var in claude_vars:
            assert var in content, (
                f"claude sidecar missing var {var}:\n{content}"
            )


class TestDelegateAndWatchSkill:
    """Gate: delegate-and-watch SKILL.md contains the required Phase D2 gate criteria."""

    SKILL_PATH = PLUGIN_ROOT / "skills" / "delegate-and-watch" / "SKILL.md"

    def test_skill_file_exists(self):
        assert self.SKILL_PATH.is_file(), "skills/delegate-and-watch/SKILL.md must exist"

    def test_execution_path_comment_at_top(self):
        """An HTML comment declaring EXECUTION PATH must appear before the first heading.

        In YAML-frontmatter Markdown files the `---...---` block is always first;
        the comment is placed immediately after the closing `---` and before the
        first `# heading` line — satisfying the 'top-of-file' gate criterion.
        """
        fm, body = parse_frontmatter(self.SKILL_PATH)
        # The comment must appear in the body, before the first heading line.
        lines = body.splitlines()
        comment_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith("<!--") and "EXECUTION PATH:" in line:
                comment_line = i
                break
            if line.startswith("#"):
                # Hit a heading before finding the comment — gate fails.
                break
        assert comment_line is not None, (
            "delegate-and-watch SKILL.md body must open with an "
            "'<!-- EXECUTION PATH: ...' HTML comment before the first heading"
        )
        comment_text = lines[comment_line]
        assert "blocking" in comment_text.lower(), (
            "delegate-and-watch EXECUTION PATH comment must name 'blocking'"
        )

    def test_bash_scaffolding_has_crash_cleanup_trap(self):
        """The SKILL.md bash scaffolding must register a crash-cleanup trap with 'sessions close'."""
        text = self.SKILL_PATH.read_text()
        assert "sessions close" in text, (
            "delegate-and-watch SKILL.md bash scaffolding must contain "
            "'sessions close' crash-cleanup trap"
        )
        assert "trap" in text, (
            "delegate-and-watch SKILL.md must register a trap in the bash scaffolding"
        )
        assert "EXIT" in text, (
            "delegate-and-watch SKILL.md trap must include EXIT signal"
        )

    def test_four_bucket_gate_documented(self):
        """The four-bucket gate (done/not-done/blocked/errored) must be documented."""
        text = self.SKILL_PATH.read_text()
        for bucket in ("done", "not-done", "blocked", "errored"):
            assert bucket in text.lower(), (
                f"delegate-and-watch SKILL.md must document the '{bucket}' gate bucket"
            )

    def test_two_log_contract_documented(self):
        """The two-log contract (driver.log and turn.log) must be documented."""
        text = self.SKILL_PATH.read_text()
        assert "driver.log" in text, (
            "delegate-and-watch SKILL.md must document the .driver.log forensic log"
        )
        assert "turn.log" in text, (
            "delegate-and-watch SKILL.md must document the .turn.log turn-content channel"
        )

    def test_env_sidecar_contract_documented(self):
        """The env sidecar contract (8 vars codex/opencode, 10 vars claude) must be documented."""
        text = self.SKILL_PATH.read_text()
        assert "ACPX_ENGINE" in text, "sidecar contract must document ACPX_ENGINE"
        assert "ACPX_SESSION_NAME" in text, "sidecar contract must document ACPX_SESSION_NAME"
        assert "ACPX_EFFORT" in text, "sidecar contract must document ACPX_EFFORT (claude extra)"
        assert "ACPX_PERMISSIONS" in text, "sidecar contract must document ACPX_PERMISSIONS (claude extra)"


# Task 29 — using-relay bootstrap skill.
RELAY_COMMANDS = (
    "/relay:implement",
    "/relay:refine",
    "/relay:execute",
)


class TestUsingRelay:
    SKILL = _skill_path("using-relay")

    def test_skill_exists(self):
        assert self.SKILL.is_file(), "skills/using-relay/SKILL.md missing"

    def test_name_is_using_relay(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert fm.get("name") == "using-relay"

    def test_has_description(self):
        fm, _ = parse_frontmatter(self.SKILL)
        assert "description" in fm and fm["description"], "missing discovery description"

    @pytest.mark.parametrize("cmd", RELAY_COMMANDS)
    def test_documents_each_command(self, cmd):
        _, body = parse_frontmatter(self.SKILL)
        assert cmd in body, f"using-relay: command {cmd} not documented"

    def test_documents_engine_agent_args(self):
        _, body = parse_frontmatter(self.SKILL)
        # per-leaf binding surface: in-session vs acpx engine, claude/codex
        assert "engine" in body.lower() and "agent" in body.lower()
        assert "in-session" in body and "acpx" in body
        for default in ("claude", "codex"):
            assert default in body, f"using-relay: missing engine {default}"

    def test_documents_superpowers_dependency(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "superpowers" in body, "using-relay: hard superpowers dependency not stated"
        # check-deps.sh dependency-gate behaviour documented
        assert "check-deps.sh" in body

    def test_documents_delegation_namespace(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "superpowers:" in body, "using-relay: superpowers:* delegation rule missing"

    def test_owns_skills_as_relay_namespace(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "relay:" in body, "using-relay: own skills must be referenced as relay:<name>"


class TestUsingRelayNamesNoSpine:
    """#77: using-relay listed a spine that disagreed with the §4.2.1 branch table
    in commands/implement.md, so a model that read using-relay built the wrong
    Workflow. using-relay now names no spine of its own — it points at the one
    authority. This class fails if the two ever disagree again.
    """

    IMPLEMENT = PLUGIN_ROOT / "commands" / "implement.md"
    SKILL = _skill_path("using-relay")

    def _branch_table_labels(self):
        """Parse every node label out of the §4.2.1 branch table, generically —
        not a hard-coded list, so this tracks the table wherever it drifts."""
        body = self.IMPLEMENT.read_text()
        pre = body.split("Every branch ends")[0]
        section = pre.rsplit("branch table)", 1)[1]
        labels = set()
        for line in section.splitlines():
            line = line.strip()
            if not line.startswith("- `"):
                continue
            for segment in line.split("→"):
                segment = segment.strip()
                m = re.search(r"`relay:delegate-leaf`\(([a-z-]+)\)", segment)
                if m:
                    labels.add(m.group(1))
                    continue
                m = re.match(r"^`?([a-z][a-z-]*)`?( \(conditional\))?$", segment)
                if m:
                    labels.add(m.group(1))
        return labels

    def _implement_bullet(self):
        body = self.SKILL.read_text()
        start = body.index("## Pipelines")
        bullet = body[start:].split("- **Refine**")[0]
        assert "Implement" in bullet, "the Implement bullet is gone — test is vacuous"
        return bullet

    def test_extraction_is_not_vacuous(self):
        labels = self._branch_table_labels()
        assert {"refine-spec", "write-plan", "refine-plan", "commit", "verify"} <= labels

    def test_every_branch_table_label_appears_in_the_pointer_target(self):
        """using-relay's pointer names commands/implement.md as the authority.
        Every node label the branch table defines must actually live in the file
        the pointer names."""
        bullet = self._implement_bullet()
        assert "commands/implement.md" in bullet
        target_text = self.IMPLEMENT.read_text()
        for label in self._branch_table_labels():
            assert label in target_text, f"{label} missing from the pointer target"

    def test_the_bullet_points_at_the_one_authority(self):
        bullet = self._implement_bullet()
        assert "§4.2.1" in bullet
        assert "commands/implement.md" in bullet

    def test_the_command_row_points_at_the_same_authority(self):
        row = next(
            l
            for l in self.SKILL.read_text().splitlines()
            if l.startswith("| `/relay:implement`")
        )
        assert "commands/implement.md" in row
        assert "language-reference" not in row

    @pytest.mark.parametrize(
        "node", ["scout", "brainstorm", "write plan", "write e2e tests", "verify spec"]
    )
    def test_the_bullet_lists_no_stale_spine_node(self, node):
        assert node not in self._implement_bullet()

    def test_using_relay_enumerates_no_spine_of_its_own(self):
        """The old fault was an arrow-chain spine list inline in using-relay's
        Implement bullet. No arrow chain may return there."""
        assert "→" not in self._implement_bullet()

    def test_the_bullet_makes_no_pull_request_promise(self):
        """Relay opens no pull request. See spec section 3."""
        assert "finishing-a-development-branch" not in self._implement_bullet()

    def test_the_delegation_rule_still_names_the_superpowers_skill(self):
        """Guard against over-deletion: the delegation-rule section legitimately
        cites superpowers:finishing-a-development-branch as a namespace example."""
        assert "superpowers:finishing-a-development-branch" in self.SKILL.read_text()


# Task 30 — the relay commands.
COMMANDS = {
    "implement": {
        "path": PLUGIN_ROOT / "commands" / "implement.md",
        "skill": "relay:delegate-leaf",      # thin-L3 cites delegate-leaf in body
        "allows_spec_path": False,           # spec-path resolution moves into the generated workflow
    },
    "refine": {
        "path": PLUGIN_ROOT / "commands" / "refine.md",
        "skill": "relay:refining-specs",   # default target's critic; cited in body Step 2
        "allows_spec_path": False,
    },
    "execute": {
        "path": PLUGIN_ROOT / "commands" / "execute.md",
        "skill": "relay:delegate-leaf",   # execute cites delegate-leaf among the library; in body
        "allows_spec_path": False,
    },
    "drive": {
        "path": PLUGIN_ROOT / "commands" / "drive.md",
        "skill": "relay:driving-to-done",  # /relay:drive loads the driving-to-done protocol; in body Step 1
        "allows_spec_path": False,
    },
    "verify": {
        "path": PLUGIN_ROOT / "commands" / "verify.md",
        "skill": "relay:verifying-until-clean",  # /relay:verify loads the protocol; in body Step 1
        "allows_spec_path": False,
    },
}
# E.2: thin-L3 Workflow-dispatch commands are exempt from the engine/agent idioms.
WORKFLOW_DISPATCH_COMMANDS = {"refine", "implement", "execute", "drive", "verify"}
# drive's exemption is withdrawn (4.23.0). It was recorded here as "oracle-driven,
# not task-kind-classified" — a deliberate position, not an oversight. The position
# changed: drive now carries the classifier like every other L3 command, and treats
# the kind as advisory. test_drive_is_not_classifier_exempt below pins that, so
# reintroducing the exemption is an explicit edit to a named assertion.
# verify is verdict-driven, not task-kind-classified: the four-step round is
# identical for a feature, a bugfix, a script, a config artifact, and a doc
# change, so there is nothing for a kind to select. Dedicated coverage lives in
# test_verify_loop.py.
CLASSIFIER_EXEMPT_COMMANDS = {"verify"}


class TestCommands:
    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_command_exists(self, name):
        assert COMMANDS[name]["path"].is_file(), f"commands/{name}.md missing"

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_has_description_frontmatter(self, name):
        fm, _ = parse_frontmatter(COMMANDS[name]["path"])
        assert "description" in fm and fm["description"], f"{name}: missing description"

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_runs_the_preflight_script(self, name):
        """Issue #110: the dependency gate (check-deps.sh), --verify/--rounds
        validation, --retro extraction, and engine/agent resolution moved out of
        an inline Step 0 bash block — refused by a worktree-isolated session —
        into scripts/l3-preflight.sh. The command body now only forwards its own
        name and the raw $ARGUMENTS string to it."""
        _, body = parse_frontmatter(COMMANDS[name]["path"])
        needle = f'"${{CLAUDE_PLUGIN_ROOT}}/scripts/l3-preflight.sh" {name} "$ARGUMENTS"'
        assert needle in body, (
            f"{name}: must call scripts/l3-preflight.sh with its own command name and $ARGUMENTS"
        )
        assert re.search(r'l3-preflight\.sh"[^\n]*\|\|\s*exit 1', body), (
            f"{name}: the preflight script call must be guarded by || exit 1"
        )
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert re.search(r'source\s+"\$HERE/check-deps\.sh"\s*\|\|\s*exit 1', script), (
            "scripts/l3-preflight.sh must source check-deps.sh guarded by || exit 1"
        )

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_sources_parser_with_all_positionals(self, name):
        # all four workflow commands use flag-form parsing rather than the positional
        # "$@" convention; keep this positional-parser skip structurally unchanged.
        if name in WORKFLOW_DISPATCH_COMMANDS:
            pytest.skip(f"{name}: thin-L3 does not use the positional engine/agent parser convention")
        _, body = parse_frontmatter(COMMANDS[name]["path"])
        assert "${CLAUDE_PLUGIN_ROOT}/scripts/parse-engine-agent.sh" in body, (
            f"{name}: must source parse-engine-agent.sh"
        )
        # the parser MUST be sourced with "$@" (NOT "$1" "$2") so extras-rejection is live
        assert re.search(r'parse-engine-agent\.sh"\s+"\$@"', body), (
            f'{name}: parser must be sourced passing "$@"'
        )
        assert '"$1" "$2"' not in body, f'{name}: must not source parser with "$1" "$2"'

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_dispatches_backing_skill(self, name):
        _, body = parse_frontmatter(COMMANDS[name]["path"])
        assert COMMANDS[name]["skill"] in body, (
            f"{name}: must dispatch {COMMANDS[name]['skill']}"
        )

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_spec_path_flag(self, name):
        _, body = parse_frontmatter(COMMANDS[name]["path"])
        if COMMANDS[name]["allows_spec_path"]:
            assert "RELAY_ALLOW_SPEC_PATH=1" in body, (
                f"{name}: implement command must set RELAY_ALLOW_SPEC_PATH=1"
            )
        else:
            assert "RELAY_ALLOW_SPEC_PATH" not in body, (
                f"{name}: refine commands must NOT set RELAY_ALLOW_SPEC_PATH"
            )

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_argument_hint(self, name):
        fm, _ = parse_frontmatter(COMMANDS[name]["path"])
        assert "argument-hint" in fm, f"{name}: missing argument-hint frontmatter"

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_no_roles_or_end_to_end_refs(self, name):
        _, body = parse_frontmatter(COMMANDS[name]["path"])
        assert "roles/" not in body, f"{name}: zero roles/ refs"
        assert "end-to-end-implementation" not in body, (
            f"{name}: zero end-to-end-implementation literals"
        )

    @pytest.mark.parametrize("name", sorted(COMMANDS))
    def test_allowed_tools_declared(self, name):
        # CMD-1: Bash/Skill-dispatch commands must declare allowed-tools with Bash
        # and Skill; thin-L3 Workflow-dispatch commands must declare Workflow.
        # (setup is covered by its own bespoke check in TestSetupCommand.)
        fm, _ = parse_frontmatter(COMMANDS[name]["path"])
        allowed = str(fm.get("allowed-tools", ""))
        assert allowed, f"{name}: allowed-tools must be declared"
        if name in WORKFLOW_DISPATCH_COMMANDS:
            assert "Workflow" in allowed, f"{name}: thin-L3 must declare Workflow"
        else:
            assert "Bash" in allowed, f"{name}: allowed-tools must include Bash"
            assert "Skill" in allowed, f"{name}: allowed-tools must include Skill"

    @pytest.mark.parametrize("name", sorted(WORKFLOW_DISPATCH_COMMANDS))
    def test_thin_l3_classifier_and_branch(self, name):
        import importlib.util
        _v = PLUGIN_ROOT / "scripts" / "validate_l3_command.py"
        s = importlib.util.spec_from_file_location("vl3", _v)
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
        _, body = parse_frontmatter(COMMANDS[name]["path"])
        if name in CLASSIFIER_EXEMPT_COMMANDS:
            # An exempt command is verdict-driven, not task-kind-classified, so the
            # only tolerated validator finding is the missing-classifier node. The
            # other thin-L3 idioms still bind: no --kind override, and every
            # cited relay:<token> must be known vocabulary.
            errs = m.check_command(body, require_branch=False)
            assert errs == ["missing task-kind classifier node"], (
                f"{name}: only the classifier exemption is tolerated, got {errs}"
            )
            assert not any("--kind" in e for e in errs), f"{name}: must not expose --kind"
            assert not any("unknown relay vocabulary" in e for e in errs), (
                f"{name}: must cite only known relay vocabulary"
            )
            return
        require_branch = name != "execute"  # forward-compat for Task 5
        assert m.check_command(body, require_branch=require_branch) == []

    def test_drive_is_not_classifier_exempt(self):
        """drive's exemption was withdrawn in 4.23.0 (see the constant's comment).

        The set is kept rather than emptied because `verify` is still legitimately
        exempt. Pinning drive by name means reintroducing its exemption has to edit
        this assertion, instead of quietly re-adding a string to a set nobody reads.
        """
        assert "drive" not in CLASSIFIER_EXEMPT_COMMANDS, (
            "drive must carry the task-kind classifier like every other L3 command"
        )

    @pytest.mark.parametrize("name", ["refine"])
    def test_refine_description_is_imperative_menu_label(self, name):
        # CMD-2: refine descriptions must read as imperative menu labels, not the
        # skill-trigger "Use when ..." phrasing (inert on disable-model-invocation).
        fm, _ = parse_frontmatter(COMMANDS[name]["path"])
        desc = str(fm.get("description", ""))
        assert "Use when" not in desc, (
            f"{name}: description must be an imperative menu label, not 'Use when ...'"
        )


ENGINE_AXIS_COMMANDS = {
    "implement": PLUGIN_ROOT / "commands" / "implement.md",
    "refine": PLUGIN_ROOT / "commands" / "refine.md",
    "execute": PLUGIN_ROOT / "commands" / "execute.md",
    "drive": PLUGIN_ROOT / "commands" / "drive.md",
}


class TestWorkflowEngineArgs:
    @pytest.mark.parametrize("name,path", sorted(ENGINE_AXIS_COMMANDS.items()))
    def test_argument_hint_exposes_engine_and_agent(self, name, path):
        fm, _ = parse_frontmatter(path)
        hint = str(fm.get("argument-hint", ""))
        assert "--engine" in hint, f"{name}: argument-hint must expose --engine"
        assert "--agent" in hint, f"{name}: argument-hint must expose --agent"

    @pytest.mark.parametrize("name,path", sorted(ENGINE_AXIS_COMMANDS.items()))
    def test_sources_guarded_flag_form_parser(self, name, path):
        # The Step 0 flag extraction moved into scripts/l3-preflight.sh (issue
        # #110). The command body's own job is now just to forward the raw
        # $ARGUMENTS string to that script. See the regression guard below.
        _, body = parse_frontmatter(path)
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/scripts/l3-preflight.sh" {name} "$ARGUMENTS"' in body, (
            f"{name}: must forward $ARGUMENTS to scripts/l3-preflight.sh"
        )
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        for flag in ("--engine", "--agent"):
            # The value class tolerates an optional surrounding quote so
            # `--engine "acpx"` resolves instead of silently defaulting. The `"`
            # is backslash-escaped in the file (it lives inside a double-quoted
            # sed program), hence `[\"']?`.
            needle = flag + r'''[ =]+[\"']?([A-Za-z-]+)'''
            assert needle in script, (
                f"scripts/l3-preflight.sh: missing quote-tolerant {flag} extraction from RAW_ARGS"
            )
        assert re.search(
            r'parse-engine-agent\.sh"\s+"\$_engine"\s+"\$_agent"\s*\|\|\s*exit 1',
            script,
        ), "scripts/l3-preflight.sh: parser must receive _engine/_agent and be guarded"

    @pytest.mark.parametrize("name,path", sorted(ENGINE_AXIS_COMMANDS.items()))
    def test_step0_never_reads_positional_parameters(self, name, path):
        """Regression guard for the silent engine/agent drop.

        The Step 0 bash block runs as a standalone script with NO positionals
        ($# == 0), so `while [ $# -gt 0 ]` never iterates and `--engine`/`--agent`
        silently resolve to their defaults. The harness also substitutes $1/$2
        textually into the command body before the shell runs, corrupting any
        `case "$1" in` subject. Executable lines must therefore never reference
        $# or $1..$9. Comments may still describe the trap.
        """
        _, body = parse_frontmatter(path)
        for block in re.findall(r"```bash\n(.*?)```", body, re.DOTALL):
            for lineno, line in enumerate(block.splitlines(), 1):
                # Strip a shell comment only when `#` begins the line or follows
                # whitespace. Splitting on the first `#` unconditionally would eat
                # the `#` inside `$#` and silently disable the `$#` assertion.
                code = re.sub(r"(^|\s)#.*$", "", line)
                assert not re.search(r"\$#", code), (
                    f"{name}:{lineno}: Step 0 reads $# — it is always 0 here. "
                    f"Parse from $ARGUMENTS instead. Line: {line!r}"
                )
                assert not re.search(r"\$\{?[1-9]\}?", code), (
                    f"{name}:{lineno}: Step 0 reads a positional parameter — the "
                    f"harness substitutes these textually and none are passed. "
                    f"Parse from $ARGUMENTS instead. Line: {line!r}"
                )
                assert not re.search(r"\$[@*]", code), (
                    f"{name}:{lineno}: Step 0 reads $@/$* — the positional array is "
                    f"empty here. Parse from $ARGUMENTS instead. Line: {line!r}"
                )
                assert not re.search(r"\bset\s+--", code), (
                    f"{name}:{lineno}: Step 0 runs `set --` to fabricate positionals "
                    f"from $ARGUMENTS — parse the string directly. Line: {line!r}"
                )
                assert not re.search(r"\bshift\b", code), (
                    f"{name}:{lineno}: Step 0 uses `shift`, implying positional "
                    f"iteration that never runs here. Line: {line!r}"
                )

    @pytest.mark.parametrize("name,path", sorted(ENGINE_AXIS_COMMANDS.items()))
    def test_threads_resolved_engine_into_delegation(self, name, path):
        _, body = parse_frontmatter(path)
        assert "RELAY_ENGINE" in body, f"{name}: delegation must branch on RELAY_ENGINE"
        assert "relay:delegate-and-watch" in body, (
            f"{name}: must retain watched-worker substitution wiring"
        )


# --- Task 7 (relay-ui-refine): generic /relay:refine command ---

REFINE_CMD_PATH = PLUGIN_ROOT / "commands" / "refine.md"


REFINING_AXIS_SHIMS = ("refining-specs", "refining-plans", "refining-prs", "refining-ui")


class TestRefiningEngineAxis:
    @staticmethod
    def _section(body, heading, next_heading):
        return body.split(heading, 1)[1].split(next_heading, 1)[0]

    def test_refine_workflow_passes_resolved_axis_to_shim(self):
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "RELAY_ENGINE" in body
        assert "RELAY_AGENT" in body
        assert "literal values" in body

    @pytest.mark.parametrize("shim", REFINING_AXIS_SHIMS)
    def test_refine_propagates_axis_to_every_shim(self, shim):
        # The propagation list must name every target shim, including refining-ui:
        # an omitted shim silently drops the flags to in-session/claude for that
        # target with no error (the ui-target regression that abface7 fixed).
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert f"relay:{shim}" in body, (
            f"refine.md must inject the resolved axis into relay:{shim}"
        )

    @pytest.mark.parametrize("name", REFINING_AXIS_SHIMS)
    def test_shim_config_accepts_optional_engine_and_agent(self, name):
        _, body = parse_frontmatter(_skill_path(name))
        assert "engine:" in body, f"{name}: inline config needs engine"
        assert "agent:" in body, f"{name}: inline config needs agent"
        assert "in-session" in body and "claude" in body

    def test_refining_persists_axis_and_uses_delegate_substitution(self):
        _, body = parse_frontmatter(_skill_path("refining"))
        critics = self._section(body, "### Critics", "### Aggregator")
        fixer = self._section(body, "### Fixer + post-fix action", "### Convergence")
        for section_name, section in (("critics", critics), ("fixer", fixer)):
            assert "RELAY_ENGINE" in section, f"{section_name}: missing axis rule"
            assert "relay:delegate-and-watch" in section, f"{section_name}: missing delegate path"
            assert "delegate_eligible" in section, f"{section_name}: missing eligibility gate"
            assert "refine-loop-state.md" in section, f"{section_name}: must re-read state"
        for token in (
            "engine", "agent", "ACPX_MECHANISM_OVERRIDE", "acpx-opencode",
            "delegated_dispatch_failed", "fresh session", "needs-decision",
            "smart-routing", "max_turns=1", "refine-loop-state.md", "state_key",
        ):
            assert token in body, f"refining: missing {token!r}"

    def test_refining_state_recovery_is_subject_keyed(self):
        _, body = parse_frontmatter(_skill_path("refining"))
        for token in ("canonical subject identity", "state_key", "incomplete", "unrelated flagless invocation"):
            assert token in body, f"refining: missing keyed recovery guard {token!r}"

    def test_refining_retry_calls_have_identical_inputs_and_distinct_sessions(self):
        _, body = parse_frontmatter(_skill_path("refining"))
        for token in ("retry_attempt=0", "retry_attempt=1", "unchanged role body", "distinct fresh session identities"):
            assert token in body, f"refining: missing retry contract {token!r}"

    def test_acpx_override_translation_contract_is_aligned(self):
        _, body = parse_frontmatter(_skill_path("dispatching-acpx-agents"))
        for token in ("ACPX_MECHANISM_OVERRIDE", "acpx-claude", "codex-session", "acpx-opencode"):
            assert token in body, f"dispatching-acpx-agents: missing override contract {token!r}"


class TestRefineCommand:
    """Structural tests for commands/refine.md.

    On the engine 'L3' line /relay:refine is a thin-L3 command: it sources the
    Step-0 dependency gate, classifies the task via relay:classifying-task-kind,
    branches on --target (spec|plan|pr|ui), and generates one dynamic Workflow
    over the relay:improve-loop spine keyed on that target. The UI feature adds
    the 'ui' target, which routes the loop over relay:refining-ui. It is a single
    flat command file (the old interactive commands/refine/ subdirectory is gone).
    """

    def test_command_file_exists(self):
        """commands/refine.md must exist as a file (not a directory)."""
        assert REFINE_CMD_PATH.is_file(), (
            "commands/refine.md missing — create the generic /relay:refine command"
        )

    def test_is_single_command_file(self):
        """commands/refine.md is a flat thin-L3 file; no commands/refine/ subdirectory."""
        assert REFINE_CMD_PATH.is_file()
        assert not (PLUGIN_ROOT / "commands" / "refine").exists(), (
            "the old interactive commands/refine/ subdirectory must be retired"
        )

    def test_has_description_frontmatter(self):
        """commands/refine.md must have a non-empty description."""
        fm, _ = parse_frontmatter(REFINE_CMD_PATH)
        assert "description" in fm and fm["description"], (
            "commands/refine.md: missing description frontmatter"
        )

    def test_has_argument_hint(self):
        """commands/refine.md must have argument-hint frontmatter."""
        fm, _ = parse_frontmatter(REFINE_CMD_PATH)
        hint = str(fm.get("argument-hint", ""))
        assert "--engine" in hint, "commands/refine.md: argument-hint must expose --engine"
        assert "--agent" in hint, "commands/refine.md: argument-hint must expose --agent"

    def test_allowed_tools_contains_bash_and_skill(self):
        """commands/refine.md must declare Bash and Skill in allowed-tools."""
        fm, _ = parse_frontmatter(REFINE_CMD_PATH)
        allowed = str(fm.get("allowed-tools", ""))
        assert "Bash" in allowed, "commands/refine.md: allowed-tools must include Bash"
        assert "Skill" in allowed, "commands/refine.md: allowed-tools must include Skill"

    def test_is_disable_model_invocation(self):
        """commands/refine.md must be disable-model-invocation (thin-L3 menu command)."""
        fm, _ = parse_frontmatter(REFINE_CMD_PATH)
        assert fm.get("disable-model-invocation") is True, (
            "commands/refine.md: thin-L3 refine must set disable-model-invocation: true"
        )

    def test_allowed_tools_contains_workflow(self):
        """commands/refine.md must declare Workflow (it generates a dynamic Workflow)."""
        fm, _ = parse_frontmatter(REFINE_CMD_PATH)
        allowed = str(fm.get("allowed-tools", ""))
        assert "Workflow" in allowed, (
            "commands/refine.md: thin-L3 refine must declare Workflow in allowed-tools"
        )

    def test_runs_the_preflight_script(self):
        """commands/refine.md must call scripts/l3-preflight.sh, guarded by ||
        exit 1 (issue #110). check-deps.sh is sourced from inside that script."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert '"${CLAUDE_PLUGIN_ROOT}/scripts/l3-preflight.sh" refine "$ARGUMENTS"' in body, (
            "commands/refine.md: must call scripts/l3-preflight.sh refine \"$ARGUMENTS\""
        )
        assert re.search(r'l3-preflight\.sh"[^\n]*\|\|\s*exit 1', body), (
            "commands/refine.md: the preflight script call must be guarded by || exit 1"
        )
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert re.search(r'source\s+"\$HERE/check-deps\.sh"\s*\|\|\s*exit 1', script), (
            "scripts/l3-preflight.sh must source check-deps.sh guarded by || exit 1"
        )

    def test_classifies_task_kind(self):
        """commands/refine.md must classify the task via relay:classifying-task-kind."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "classifying-task-kind" in body, (
            "commands/refine.md: must run relay:classifying-task-kind"
        )

    def test_branches_on_target(self):
        """commands/refine.md must branch on --target over the documented enum."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "--target" in body, "commands/refine.md: must expose a --target surface"
        assert "branch" in body.lower(), (
            "commands/refine.md: must branch on the refine target"
        )
        # all four target options documented
        for target in ("spec", "plan", "pr", "ui"):
            assert target in body, (
                f"commands/refine.md: must list target option '{target}'"
            )

    def test_routes_to_refining_specs(self):
        """commands/refine.md must route spec target to relay:refining-specs."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "relay:refining-specs" in body, (
            "commands/refine.md: must route spec target to relay:refining-specs (spec §6)"
        )

    def test_routes_to_refining_plans(self):
        """commands/refine.md must route plan target to relay:refining-plans."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "relay:refining-plans" in body, (
            "commands/refine.md: must route plan target to relay:refining-plans (spec §6)"
        )

    def test_routes_to_refining_prs(self):
        """commands/refine.md must route pr target to relay:refining-prs."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "relay:refining-prs" in body, (
            "commands/refine.md: must route pr target to relay:refining-prs (spec §6)"
        )

    def test_routes_to_refining_ui(self):
        """commands/refine.md must route ui target to relay:refining-ui."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "relay:refining-ui" in body, (
            "commands/refine.md: must route ui target to relay:refining-ui (spec §6)"
        )

    def test_ui_target_runs_scored_convergence_loop(self):
        """For the ui target the thin-L3 loop runs over relay:refining-ui under the
        scored convergence_mode (not the binary verdict used by spec/plan/pr). The
        per-input gathering (base_url, dev_command, thresholds, web-app health) is
        owned by relay:refining-ui, not the thin command body."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "relay:refining-ui" in body, (
            "commands/refine.md: ui target must route to relay:refining-ui"
        )
        assert "convergence_mode" in body or "scored" in body.lower(), (
            "commands/refine.md: ui target must document its scored convergence loop"
        )

    def test_no_roles_refs(self):
        """commands/refine.md must contain no roles/ refs."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "roles/" not in body, "commands/refine.md: must contain zero roles/ refs"

    def test_no_relay_allow_spec_path(self):
        """commands/refine.md is a refine command — must NOT set RELAY_ALLOW_SPEC_PATH."""
        _, body = parse_frontmatter(REFINE_CMD_PATH)
        assert "RELAY_ALLOW_SPEC_PATH" not in body, (
            "commands/refine.md: refine commands must NOT set RELAY_ALLOW_SPEC_PATH"
        )


# --- Task 31: shipped refinement-contract.md ---

# Abstract PR-target role archetypes that have NO dedicated agent in the 18-agent
# set, plus the real agent each maps to (mirrors skills/refining-prs/SKILL.md).
PR_TARGET_MAPPING = {
    "pr-reviewer": "code-reviewer",
    "pr-validator": "code-reviewer",
    "pr-runner": "server-runner",
    "pr-fixer": "fix-coder",
}


class TestShippedDocs:
    def _contract_path(self):
        return PLUGIN_ROOT / "docs" / "refinement-contract.md"

    def test_contract_shipped(self):
        assert self._contract_path().exists(), (
            "docs/refinement-contract.md must be shipped inside the plugin"
        )

    def test_port_inventory_not_shipped(self):
        assert not (PLUGIN_ROOT / "docs" / "port-inventory.md").exists(), (
            "docs/port-inventory.md is design-time only and must NOT be shipped"
        )

    def test_orchestration_substrates_shipped(self):
        """SUBSTRATE-1 / HYGIENE-3: the substrate doc must ship with the Native
        Workflow Tool substrate, the diagnose→refine→implement ladder, and the
        flows/ leaf-capability note.

        4.30.0: the doc moved from a single-substrate model to two — the
        session-tree exception (spec §Deliverable 3, Doctrine) generates no
        Workflow at all. `docs/contributing.md::test_docs_freshness.py` is the
        place that catches drift on the exact count; this test only proves the
        stale "single orchestration substrate" sentence did not survive.
        """
        path = PLUGIN_ROOT / "docs" / "orchestration-substrates.md"
        assert path.exists(), "docs/orchestration-substrates.md must be shipped"
        body = path.read_text()
        assert "single orchestration substrate" not in body, (
            "orchestration-substrates.md must not claim a single substrate now "
            "that session-tree ships a second one"
        )
        assert "two orchestration substrates" in body, (
            "orchestration-substrates.md must state there are now two substrates"
        )
        assert "session-tree exception" in body, (
            "orchestration-substrates.md must name the session-tree exception "
            "alongside the /relay:drive exception"
        )
        assert "Native Workflow Tool" in body, (
            "orchestration-substrates.md must document the Native Workflow Tool substrate"
        )
        # HYGIENE-3: flows/ documented as a surviving leaf capability
        assert "flows/" in body, (
            "orchestration-substrates.md must document the flows/ acpx-native substrate (HYGIENE-3)"
        )
        # the diagnose → refine → implement ladder
        assert re.search(r"diagnose.*refine.*implement", body, re.DOTALL), (
            "orchestration-substrates.md must document the diagnose→refine→implement ladder"
        )

    def test_dispatch_contract_shipped(self):
        """CONTRACT-2: the shared §5.1 wrapper-contract doc must ship and cover
        the (role_slug, binding, inputs) → result envelope."""
        path = PLUGIN_ROOT / "docs" / "dispatch-contract.md"
        assert path.exists(), "docs/dispatch-contract.md must be shipped"
        body = path.read_text()
        assert "Wrapper Contract" in body, (
            "dispatch-contract.md must document the §5.1 wrapper contract"
        )
        assert "role_slug" in body and "binding" in body and "result" in body, (
            "dispatch-contract.md must describe the (role_slug, binding, inputs) → result envelope"
        )

    def test_shipped_contract_pr_section_reconciled(self):
        """No undefined relay:pr-* slug may be named without its mapped real agent/role.

        The pr-archetype→agent mapping now lives in skills/refining/adapters/pr.md
        (REFINE-3); the shipped refinement-contract.md retains the per-target
        instantiation overview plus a cross-reference to the adapter. For each
        abstract pr-* archetype, EITHER it does not appear, OR its mapped real
        agent/role is named in the adapter (so the guard does not pass vacuously once
        the mapping table relocates out of the contract doc). Every concrete
        relay:<slug> referenced in the contract doc must still resolve to an
        existing agents/<slug>.md or roles/<slug>.md file unless it is an annotated archetype.

        Post-PR3 §7: server-runner and fix-coder are now roles (roles/<slug>.md),
        not agents. The check accepts either location.
        """
        contract_body = self._contract_path().read_text()
        adapter_path = PLUGIN_ROOT / "skills" / "refining" / "adapters" / "pr.md"
        adapter_body = adapter_path.read_text()
        for archetype, real_agent in PR_TARGET_MAPPING.items():
            # the archetype's mapping now lives in adapters/pr.md
            assert archetype in adapter_body, (
                f"adapters/pr.md must document the abstract `{archetype}` archetype"
            )
            assert real_agent in adapter_body, (
                f"adapters/pr.md names abstract `{archetype}` but never names its "
                f"mapped real agent `{real_agent}`"
            )
            # that real agent/role must actually exist (post-PR3: check roles/ too)
            agent_exists = (PLUGIN_ROOT / "agents" / f"{real_agent}.md").exists()
            role_exists = (PLUGIN_ROOT / "roles" / f"{real_agent}.md").exists()
            assert agent_exists or role_exists, (
                f"mapped agent/role {real_agent} must exist in agents/ or roles/"
            )
        # every relay:<slug> referenced in the shipped contract doc resolves to an
        # existing agent or role UNLESS it is one of the annotated PR-target archetypes.
        # Slugs must end in an alphanumeric char; the literal `relay:pr-*` wildcard
        # reference is not a concrete slug and is ignored.
        for slug in set(re.findall(r"relay:([a-z][a-z0-9-]*[a-z0-9])(?![\w*-])", contract_body)):
            if slug in PR_TARGET_MAPPING:
                continue
            agent_exists = (PLUGIN_ROOT / "agents" / f"{slug}.md").exists()
            role_exists = (PLUGIN_ROOT / "roles" / f"{slug}.md").exists()
            assert agent_exists or role_exists, (
                f"shipped contract references relay:{slug} but neither agents/{slug}.md "
                f"nor roles/{slug}.md exists"
            )


# --- Task 2 (relay-ui-refine): refinement-contract.md convergence_mode extension ---


class TestRefinementContractConvergenceMode:
    """Verify refinement-contract.md documents the convergence_mode extension (§3.1, §7).

    The contract doc must gain:
    1. A convergence_mode extension section documenting binary | scored values.
    2. A refining-ui per-target instantiation block (scored mode, adapter=ui, aggregator=scored).
    3. The scored config block dimensions and loop parameters.

    Binary shims (refining-specs, refining-plans, refining-prs) must NOT carry
    convergence_mode — they inherit binary by absence (enforced by TestRefiningConvergenceModes).
    """

    CONTRACT = PLUGIN_ROOT / "docs" / "refinement-contract.md"

    def _body(self):
        return self.CONTRACT.read_text()

    def test_convergence_mode_extension_section_exists(self):
        """Contract doc must have a convergence_mode extension section."""
        body = self._body()
        assert "convergence_mode" in body, (
            "refinement-contract.md must document the convergence_mode extension"
        )

    def test_binary_mode_documented(self):
        """binary is the default convergence_mode value."""
        body = self._body()
        assert "binary" in body, (
            "refinement-contract.md must document 'binary' as a convergence_mode value"
        )

    def test_scored_mode_documented(self):
        """scored is the new convergence_mode value for UI refinement."""
        body = self._body()
        assert "scored" in body, (
            "refinement-contract.md must document 'scored' as a convergence_mode value"
        )

    def test_refining_ui_per_target_block_exists(self):
        """Contract doc must have a refining-ui per-target instantiation block."""
        body = self._body()
        assert "refining-ui" in body, (
            "refinement-contract.md must contain a refining-ui per-target block"
        )

    def test_refining_ui_uses_scored_mode(self):
        """The refining-ui block must set convergence_mode: scored."""
        body = self._body()
        assert "convergence_mode: scored" in body, (
            "refinement-contract.md refining-ui block must set convergence_mode: scored"
        )

    def test_refining_ui_names_ui_adapter(self):
        """The refining-ui block must name the ui adapter slug."""
        body = self._body()
        assert "subject_adapter" in body and "ui" in body, (
            "refinement-contract.md refining-ui block must reference subject_adapter and ui"
        )

    def test_refining_ui_scored_dimensions(self):
        """Scored config block must list all five UI dimensions."""
        body = self._body()
        for dim in ("design_quality", "originality", "craft", "functionality", "accessibility"):
            assert dim in body, (
                f"refinement-contract.md must document scored dimension '{dim}'"
            )

    def test_refining_ui_scored_config_parameters(self):
        """Scored config block must document loop parameters."""
        body = self._body()
        assert "max_findings_per_cycle" in body, (
            "refinement-contract.md must document max_findings_per_cycle"
        )
        assert "plateau_window" in body, (
            "refinement-contract.md must document plateau_window"
        )

    def test_refining_ui_aggregator_scored(self):
        """The refining-ui block must set aggregator: scored."""
        body = self._body()
        assert "aggregator: scored" in body, (
            "refinement-contract.md refining-ui block must set aggregator: scored"
        )

    def test_refining_ui_max_rounds(self):
        """The refining-ui block must document max_rounds."""
        body = self._body()
        assert "max_rounds" in body, (
            "refinement-contract.md must document max_rounds for refining-ui"
        )

    def test_scored_aggregator_operations_documented(self):
        """Scored aggregator operations merge_scores and cap must be noted."""
        body = self._body()
        assert "merge_scores" in body, (
            "refinement-contract.md must document the merge_scores aggregator operation"
        )
        assert "cap" in body, (
            "refinement-contract.md must document the cap aggregator operation"
        )


# --- Task 32: top-level attribution + docs files ---


class TestTopLevelFiles:
    def test_license_exists_with_both_copyrights(self):
        path = PLUGIN_ROOT / "LICENSE"
        assert path.exists(), "LICENSE must exist"
        text = path.read_text()
        assert "MIT License" in text, "LICENSE must be MIT"
        assert "Copyright (c) 2025 Jesse Vincent" in text, (
            "LICENSE must retain the original superpowers copyright"
        )
        assert "Copyright (c) 2026 Yassel Piloto" in text, (
            "LICENSE must add the relay copyright"
        )

    def test_notice_attributes_superpowers(self):
        path = PLUGIN_ROOT / "NOTICE.md"
        assert path.exists(), "NOTICE.md must exist"
        text = path.read_text()
        assert "superpowers" in text, "NOTICE must reference superpowers"
        assert "Jesse Vincent" in text, "NOTICE must credit Jesse Vincent"
        assert "github.com/obra/superpowers" in text, "NOTICE must link the obra repo"

    def test_readme_credits_superpowers_up_top(self):
        path = PLUGIN_ROOT / "README.md"
        assert path.exists(), "README.md must exist"
        text = path.read_text()
        assert "superpowers" in text[:600].lower(), (
            "README first paragraph must prominently credit superpowers"
        )

    def test_readme_documents_commands_and_install(self):
        text = (PLUGIN_ROOT / "README.md").read_text()
        for cmd in ("/relay:implement", "/relay:refine", "/relay:execute"):
            assert cmd in text, f"README must document the {cmd} command"
        assert "/plugin install relay" in text, "README must document the install command"
        assert "ai-advanced-futures/claude-code-dev-plugins" in text, (
            "README must document the marketplace add command"
        )

    def test_changelog_has_v1(self):
        path = PLUGIN_ROOT / "CHANGELOG.md"
        assert path.exists(), "CHANGELOG.md must exist"
        assert "1.0.0" in path.read_text(), "CHANGELOG must contain 1.0.0"


# --- Task 33: e2e eval harness + fixture ---

# Standardized phase markers the harness greps for. The refining loop is
# relay-owned, so the Phase 2 marker is relay:refining-specs (NOT superpowers:).
E2E_MARKERS = [
    "relay:refining-specs",
    "spec-simulator",
    "spec-fixer",
    "ROLE_DONE",
    "superpowers:writing-plans",
    "/relay:implement",
    "implementer",
    "code-reviewer",
    "REVIEW=PASS",
]


class TestE2EHarness:
    EVAL = PLUGIN_ROOT / "tests" / "e2e" / "run-eval.sh"
    FIXTURE = PLUGIN_ROOT / "tests" / "e2e" / "fixtures" / "hello-spec.md"
    RUNS_GITKEEP = PLUGIN_ROOT / "tests" / "e2e" / "runs" / ".gitkeep"

    def test_run_eval_exists(self):
        assert self.EVAL.is_file(), "tests/e2e/run-eval.sh must exist"

    def test_run_eval_syntax(self):
        result = subprocess.run(["bash", "-n", str(self.EVAL)], capture_output=True, text=True)
        assert result.returncode == 0, f"run-eval.sh syntax error:\n{result.stderr}"

    def test_run_eval_invokes_acpx_implement(self):
        body = self.EVAL.read_text()
        assert "acpx claude exec" in body, "harness must invoke acpx claude exec"
        assert "/relay:implement" in body, "harness must target /relay:implement"
        # the fixture path is passed as the 3rd positional of /relay:implement
        assert "in-session claude $FIXTURE" in body, (
            "harness must pass the fixture as the spec-path positional"
        )

    def test_run_eval_writes_timestamped_log(self):
        body = self.EVAL.read_text()
        assert "runs/" in body, "harness must write under tests/e2e/runs/"
        assert "output.log" in body, "harness must write output.log"

    def test_run_eval_greps_phase_markers(self):
        body = self.EVAL.read_text()
        for marker in E2E_MARKERS:
            assert marker in body, f"harness must grep for the {marker} phase marker"

    def test_fixture_exists_with_greet_and_refinement_status(self):
        assert self.FIXTURE.is_file(), "hello-spec.md fixture must exist"
        text = self.FIXTURE.read_text()
        assert "greet" in text, "fixture must specify a greet(name) function"
        assert "## Refinement Status" in text, (
            "fixture must include a Refinement Status section"
        )

    def test_runs_gitkeep_exists(self):
        assert self.RUNS_GITKEEP.is_file(), "tests/e2e/runs/.gitkeep must exist"


class TestDiagnoseAgents:
    """Smoke checks specific to the three diagnose leaf agents."""

    @pytest.mark.parametrize("slug", sorted(DIAGNOSE_AGENT_SLUGS))
    def test_agent_file_exists(self, slug):
        assert _agent_path(slug).is_file(), f"agents/{slug}.md missing"

    def test_gatherer_tools_no_agent_or_skill(self):
        fm, _ = parse_frontmatter(_agent_path("gatherer"))
        blob = _normalize_tools(fm["tools"])
        assert not re.search(r"\bAgent\b", blob)
        assert not re.search(r"\bSkill\b", blob)

    def test_strategist_has_tools_field(self):
        # iterate source omitted tools:; relay copy must add it (test_required_frontmatter gate)
        fm, _ = parse_frontmatter(_agent_path("strategist"))
        assert "tools" in fm, "strategist: tools field required"

    def test_strategist_tools_no_agent_or_skill(self):
        fm, _ = parse_frontmatter(_agent_path("strategist"))
        blob = _normalize_tools(fm["tools"])
        assert not re.search(r"\bAgent\b", blob)
        assert not re.search(r"\bSkill\b", blob)

    # [inferred] analyst does not get a dedicated tools-no-agent-or-skill test here because
    # [inferred] the PC1 fix causes the parametrized TestAgents.test_no_agent_tool and
    # [inferred] TestAgents.test_no_skill_backdoor to cover analyst at module evaluation time.
    # [inferred] No separate analyst tools check is required.

    def test_not_in_presets(self):
        # Workflow-only leaves must NOT appear in presets.yaml (would inflate roster).
        if not PRESETS_PATH.is_file():
            pytest.skip("presets.yaml not present")
        roles = _load_presets()["roles"]
        for slug in DIAGNOSE_AGENT_SLUGS:
            assert slug not in roles, (
                f"{slug} must not be in presets.yaml (workflow-only leaf)"
            )

    def test_no_relay_block(self):
        """TRIO-2 guard: Workflow-leaf agents must NOT carry a relay: block."""
        for slug in sorted(DIAGNOSE_AGENT_SLUGS):
            path = _agent_path(slug)
            assert path.is_file(), f"agents/{slug}.md missing"
            fm, _ = parse_frontmatter(path)
            assert fm.get("relay") is None, (
                f"{slug}: Workflow-leaf agent must not have a relay: block"
                " (inert under Workflow dispatch, creates false parity expectations)"
            )


class TestDiagnoseCommand:
    CMD = PLUGIN_ROOT / "commands" / "diagnose.md"

    def test_command_file_exists(self):
        assert self.CMD.is_file(), "commands/diagnose.md missing"

    def test_has_description(self):
        fm, _ = parse_frontmatter(self.CMD)
        assert "description" in fm and fm["description"], "diagnose.md: missing description"

    def test_disable_model_invocation(self):
        fm, _ = parse_frontmatter(self.CMD)
        assert fm.get("disable-model-invocation") is True, (
            "diagnose.md: disable-model-invocation must be true"
        )

    def test_allowed_tools_contains_workflow(self):
        fm, _ = parse_frontmatter(self.CMD)
        allowed = str(fm.get("allowed-tools", ""))
        assert "Workflow" in allowed, "diagnose.md: allowed-tools must include Workflow"

    def test_allowed_tools_contains_ask_user_question(self):
        fm, _ = parse_frontmatter(self.CMD)
        allowed = str(fm.get("allowed-tools", ""))
        assert "AskUserQuestion" in allowed, (
            "diagnose.md: allowed-tools must include AskUserQuestion"
        )

    def test_no_check_deps_sourced(self):
        _, body = parse_frontmatter(self.CMD)
        assert "check-deps.sh" not in body, (
            "diagnose.md must NOT source check-deps.sh (no superpowers dependency)"
        )

    def test_no_parse_engine_agent_sourced(self):
        _, body = parse_frontmatter(self.CMD)
        assert "parse-engine-agent.sh" not in body, (
            "diagnose.md must NOT source parse-engine-agent.sh (no engine/agent args)"
        )

    def test_references_workflow_script_path(self):
        _, body = parse_frontmatter(self.CMD)
        assert "workflows/diagnose.js" not in body, (
            "thin-L3 diagnose generates a workflow inline; it must not dispatch the old diagnose.js"
        )

    def test_has_degradation_guard(self):
        _, body = parse_frontmatter(self.CMD)
        assert "CLAUDE_CODE_WORKFLOWS" not in body, (
            "thin-L3 diagnose has no env-var degradation guard"
        )

    def test_degradation_message_has_launch_recipe(self):
        _, body = parse_frontmatter(self.CMD)
        assert "DISABLE_GROWTHBOOK=1" not in body, (
            "thin-L3 diagnose has no launch recipe"
        )

    def test_problem_captured_via_arguments(self):
        # SUBSTRATE-3: the problem statement comes from $ARGUMENTS, NOT an
        # AskUserQuestion "Describe the problem" block.
        _, body = parse_frontmatter(self.CMD)
        assert "$ARGUMENTS" in body, (
            "diagnose.md must capture the problem via $ARGUMENTS"
        )
        assert "Describe the problem" not in body, (
            "diagnose.md must not collect the problem text via AskUserQuestion"
        )
        assert "What problem are you trying to diagnose" not in body, (
            "diagnose.md must not ask for the problem text via AskUserQuestion"
        )

    def test_render_template_pushed_into_workflow(self):
        # SUBSTRATE-2: the ~60-line render template lives in diagnose.js now; the
        # command body's remaining job is to invoke the Workflow and echo the
        # returned report verbatim. The per-field substitution markers must be gone.
        _, body = parse_frontmatter(self.CMD)
        assert "DIAGNOSIS COMPLETE" not in body, (
            "diagnose.md must not inline the render template (SUBSTRATE-2)"
        )
        assert "RESULT.ranking" not in body, (
            "diagnose.md must not inline per-field render substitutions (SUBSTRATE-2)"
        )

    def test_l3_classifier_and_branch(self):
        import importlib.util
        _v = PLUGIN_ROOT / "scripts" / "validate_l3_command.py"
        s = importlib.util.spec_from_file_location("vl3", _v)
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
        _, body = parse_frontmatter(self.CMD)
        assert m.check_command(body, require_branch=True) == []


# [inferred] Added so the pytest gate asserts relay:diagnose is documented in using-relay/SKILL.md.
# [inferred] Do NOT add diagnose to RELAY_COMMANDS — its row format differs from the four argument-taking commands.
# [inferred] Task 5 is the task that turns this test green.
class TestUsingRelayDiagnose:
    """Assert /relay:diagnose appears in using-relay/SKILL.md."""  # [inferred]

    def test_documents_diagnose_command(self):  # [inferred]
        skill_path = PLUGIN_ROOT / "skills" / "using-relay" / "SKILL.md"  # [inferred]
        if not skill_path.is_file():  # [inferred]
            pytest.skip("using-relay/SKILL.md not present")  # [inferred]
        text = skill_path.read_text()  # [inferred]
        assert "relay:diagnose" in text, (  # [inferred]
            "using-relay/SKILL.md must document /relay:diagnose"  # [inferred]
        )  # [inferred]


# --- Task 3 (relay-ui-refine): UI subject adapter ---

UI_ADAPTER_PATH = PLUGIN_ROOT / "skills" / "refining" / "adapters" / "ui.md"

# All six interface verbs required by spec §4.
UI_ADAPTER_VERBS = ("load", "snapshot", "diff", "post_fix", "persist", "recover")

# Spec §4 structural requirements documented in the adapter body.
UI_ADAPTER_LOAD_REQUIREMENTS = (
    "PRE_LOOP_SHA",          # safe revert anchor recorded at load() time
    "base_url",              # pre-warmed handle field
    "source_root",           # pre-warmed handle field
    "dev_command",           # pre-warmed handle field
)

UI_ADAPTER_PERSIST_REQUIREMENTS = (
    "refine(ui): round",     # structured commit subject prefix (spec §4 persist)
    "design_quality",        # per-dimension score in commit message
    "originality",
    "craft",
    "functionality",
    "accessibility",
    "mode=",                 # refine|pivot mode token in commit message
)

UI_ADAPTER_RECOVER_REQUIREMENTS = (
    r"refine\(ui\): round \d+",   # regex used to grep git log (spec §4 recover)
    r"(\w+)=([^\s]+)",            # key=value token parse regex (spec §4 recover)
)

UI_ADAPTER_SIDECAR_REQUIREMENTS = (
    ".relay",                # sidecar directory (spec §4 persist)
    "ui-refine-findings",    # sidecar filename (spec §4 persist)
)


class TestUIAdapter:
    """Structural tests for adapters/ui.md — spec §4.

    These tests verify the adapter file exists and documents all six interface verbs
    with the required behaviour: PRE_LOOP_SHA in load(), score-commit format in
    persist(), git log regex in recover(), and sidecar persistence.
    """

    def test_adapter_file_exists(self):
        """adapters/ui.md must exist."""
        assert UI_ADAPTER_PATH.is_file(), (
            "skills/refining/adapters/ui.md missing — create the UI subject adapter"
        )

    def test_adapter_declares_all_interface_verbs(self):
        """All six interface verbs from spec §4 must be present in the adapter body."""
        text = UI_ADAPTER_PATH.read_text()
        for verb in UI_ADAPTER_VERBS:
            assert verb in text, (
                f"adapters/ui.md: missing interface verb '{verb}' (spec §4)"
            )

    def test_load_documents_pre_loop_sha(self):
        """load() must record PRE_LOOP_SHA as a safe revert anchor (spec §4)."""
        text = UI_ADAPTER_PATH.read_text()
        assert "PRE_LOOP_SHA" in text, (
            "adapters/ui.md: load() must document PRE_LOOP_SHA safe revert anchor (spec §4)"
        )

    def test_load_accepts_pre_warmed_handle(self):
        """load() accepts the pre-warmed {base_url, source_root, dev_command} handle."""
        text = UI_ADAPTER_PATH.read_text()
        for field in UI_ADAPTER_LOAD_REQUIREMENTS:
            assert field in text, (
                f"adapters/ui.md: load() must document handle field '{field}' (spec §4)"
            )

    def test_persist_score_commit_format(self):
        """persist() must document the structured score-commit subject line (spec §4)."""
        text = UI_ADAPTER_PATH.read_text()
        for token in UI_ADAPTER_PERSIST_REQUIREMENTS:
            assert token in text, (
                f"adapters/ui.md: persist() must document score-commit token '{token}' (spec §4)"
            )

    def test_persist_documents_sidecar(self):
        """persist() must document the sidecar findings file (spec §4)."""
        text = UI_ADAPTER_PATH.read_text()
        for token in UI_ADAPTER_SIDECAR_REQUIREMENTS:
            assert token in text, (
                f"adapters/ui.md: persist() must document sidecar token '{token}' (spec §4)"
            )

    def test_recover_git_log_reading(self):
        """recover() must document git log reading with the score-commit regex (spec §4)."""
        text = UI_ADAPTER_PATH.read_text()
        assert "git log" in text, (
            "adapters/ui.md: recover() must document reading git log (spec §4)"
        )

    def test_recover_regex_patterns(self):
        """recover() must document both regex patterns from spec §4."""
        text = UI_ADAPTER_PATH.read_text()
        # The adapter documents the commit-subject match regex and the key=value parse regex.
        # We check for the literal regex fragments (the actual characters present in the body).
        assert r"refine\(ui\)" in text, (
            r"adapters/ui.md: recover() must document the commit-match regex refine\(ui\) (spec §4)"
        )
        assert r"(\w+)=" in text, (
            r"adapters/ui.md: recover() must document the key=value parse regex (\w+)= (spec §4)"
        )

    def test_recover_sidecar_fallback(self):
        """recover() must document fallback to the sidecar when no matching commit exists."""
        text = UI_ADAPTER_PATH.read_text()
        assert "fallback" in text.lower() or "fall back" in text.lower(), (
            "adapters/ui.md: recover() must document sidecar fallback (spec §4)"
        )

    def test_post_fix_re_read_action(self):
        """post_fix() must document the re-read action (spec §4)."""
        text = UI_ADAPTER_PATH.read_text()
        assert "re-read" in text, (
            "adapters/ui.md: post_fix() must document the 're-read' action (spec §4)"
        )

    def test_post_fix_smoke_check(self):
        """post_fix() must mention the smoke check (does the site still load)."""
        text = UI_ADAPTER_PATH.read_text()
        assert "smoke" in text.lower() or "still load" in text.lower() or "site still" in text.lower(), (
            "adapters/ui.md: post_fix() must reference the smoke/load check (spec §4)"
        )

    def test_snapshot_git_tree_state(self):
        """snapshot() must document capturing git tree state (HEAD + working tree hash)."""
        text = UI_ADAPTER_PATH.read_text()
        assert "git" in text, (
            "adapters/ui.md: snapshot() must reference git state (spec §4)"
        )
        assert "HEAD" in text, (
            "adapters/ui.md: snapshot() must reference HEAD (spec §4)"
        )

    def test_diff_uses_git_diff(self):
        """diff() must document git diff of source_root (spec §4)."""
        text = UI_ADAPTER_PATH.read_text()
        assert "git diff" in text, (
            "adapters/ui.md: diff() must document git diff (spec §4)"
        )

    def test_body_nonempty(self):
        """adapter body must have substantial content (>200 chars)."""
        text = UI_ADAPTER_PATH.read_text()
        assert len(text) > 200, "adapters/ui.md: body too short"

    def test_error_handling_documented(self):
        """Adapter must document error handling per spec §9."""
        text = UI_ADAPTER_PATH.read_text()
        # Spec §9: SERVER_FAILED / site-fails-to-load errors surface via load()
        assert "error" in text.lower() or "fail" in text.lower(), (
            "adapters/ui.md: must document error handling (spec §9)"
        )


# --- Task 4 (relay-ui-refine): running-web-apps skill ---

RUNNING_WEB_APPS_SKILL = _skill_path("running-web-apps")

# Setup phase requirements from spec §8.
SETUP_PHASE_TOKENS = (
    "~/.claude.json",           # Playwright MCP merge target
    "mcpServers",               # MCP server config key
    "playwright",               # Playwright MCP identifier
    ".claude/settings.local.json",  # permissions file
    "permissions",              # permissions merge
    "package.json",             # framework detection source
    "scripts.dev",              # dev command detection
    "scripts.start",            # fallback dev command detection
    ".relay/web-app.yaml",      # project config output
    "dev_command",              # config field
    "framework",                # config field
    "url",                      # config field
)

# Run phase requirements from spec §8.
RUN_PHASE_TOKENS = (
    "relay:server-runner",      # delegation to existing server-runner agent
    "SERVER_READY",             # health-check success token
    "SERVER_FAILED",            # health-check failure token
    "BASE_URL",                 # result field from server-runner
    "health",                   # health-check step
)

# Idempotency tokens from spec §8.
IDEMPOTENCY_TOKENS = (
    "idempotent",               # skill must describe its idempotency guarantee
    "already",                  # skip-if-exists pattern
)

# Return contract tokens from spec §8.
RETURN_CONTRACT_TOKENS = (
    "base_url",                 # returned handle field
    "dev_command",              # returned handle field
    "framework",                # returned handle field
    "server_status",            # returned handle field
)


class TestRunningWebApps:
    """Structural tests for skills/running-web-apps/SKILL.md — spec §8.

    Covers setup phase (Playwright MCP merge, permissions, framework detection,
    .relay/web-app.yaml write), run phase (server-runner delegation, health-check),
    idempotency guarantee, and return contract.
    """

    def test_skill_file_exists(self):
        """skills/running-web-apps/SKILL.md must exist."""
        assert RUNNING_WEB_APPS_SKILL.is_file(), (
            "skills/running-web-apps/SKILL.md missing — create the running-web-apps skill"
        )

    def test_name_is_running_web_apps(self):
        """Frontmatter name must match the directory slug."""
        fm, _ = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert fm.get("name") == "running-web-apps", (
            "running-web-apps: frontmatter name must be 'running-web-apps'"
        )

    def test_has_description(self):
        """Frontmatter description must be present and non-empty."""
        fm, _ = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "description" in fm and fm["description"], (
            "running-web-apps: frontmatter must include a non-empty description"
        )

    def test_user_invocable_false(self):
        """Internal skill must have user-invocable: false."""
        fm, _ = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert fm.get("user-invocable") is False, (
            "running-web-apps: internal skill must have user-invocable: false"
        )

    def test_body_nonempty(self):
        """Skill body must have substantial content."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert len(body) > 200, "running-web-apps: body too short"

    def test_setup_phase_documents_playwright_mcp_merge(self):
        """Setup phase must document Playwright MCP merge into ~/.claude.json."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "~/.claude.json" in body, (
            "running-web-apps: setup phase must document ~/.claude.json merge"
        )
        assert "mcpServers" in body, (
            "running-web-apps: setup phase must reference mcpServers key"
        )
        assert "playwright" in body.lower(), (
            "running-web-apps: setup phase must mention Playwright MCP"
        )

    def test_setup_phase_documents_permissions(self):
        """Setup phase must document permissions merge into .claude/settings.local.json."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert ".claude/settings.local.json" in body, (
            "running-web-apps: setup phase must reference .claude/settings.local.json"
        )
        assert "permissions" in body, (
            "running-web-apps: setup phase must document permissions merge"
        )

    def test_setup_phase_framework_detection(self):
        """Setup phase must document framework detection from package.json."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "package.json" in body, (
            "running-web-apps: setup phase must reference package.json for framework detection"
        )
        assert "scripts.dev" in body or ("scripts" in body and "dev" in body), (
            "running-web-apps: setup phase must document scripts.dev detection"
        )
        assert "scripts.start" in body or ("scripts" in body and "start" in body), (
            "running-web-apps: setup phase must document scripts.start detection"
        )

    def test_setup_phase_writes_relay_config(self):
        """Setup phase must write .relay/web-app.yaml config."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert ".relay/web-app.yaml" in body, (
            "running-web-apps: setup phase must write .relay/web-app.yaml"
        )

    def test_run_phase_delegates_to_server_runner_role(self):
        """Run phase must delegate server start via roles/server-runner.md + relay:leaf-reader."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "roles/server-runner.md" in body, (
            "running-web-apps: must reference roles/server-runner.md"
        )
        assert "relay:leaf-reader" in body, (
            "running-web-apps: must dispatch server-runner via relay:leaf-reader"
        )

    def test_run_phase_health_check(self):
        """Run phase must document health-check with SERVER_READY / SERVER_FAILED."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "SERVER_READY" in body, (
            "running-web-apps: run phase must reference SERVER_READY token"
        )
        assert "SERVER_FAILED" in body, (
            "running-web-apps: run phase must reference SERVER_FAILED token"
        )
        assert "health" in body.lower() or "BASE_URL" in body, (
            "running-web-apps: run phase must document health-check or BASE_URL"
        )

    def test_idempotency_documented(self):
        """Skill must document its idempotency guarantee (setup skipped when valid)."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "idempotent" in body.lower() or "already" in body.lower(), (
            "running-web-apps: must document idempotency guarantee (spec §8)"
        )

    def test_return_contract_documented(self):
        """Skill must document the return contract fields (spec §8)."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        for field in RETURN_CONTRACT_TOKENS:
            assert field in body, (
                f"running-web-apps: return contract must include field '{field}' (spec §8)"
            )

    def test_setup_phase_heading_present(self):
        """Skill must have a distinct setup phase section."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "setup" in body.lower(), (
            "running-web-apps: must have a setup phase section"
        )

    def test_run_phase_heading_present(self):
        """Skill must have a distinct run phase section."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "run" in body.lower(), (
            "running-web-apps: must have a run phase section"
        )

    def test_server_runner_old_slug_absent(self):
        """relay:server-runner must NOT appear in running-web-apps/SKILL.md post-migration."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "relay:server-runner" not in body, (
            "running-web-apps: relay:server-runner must be absent (collapsed to role)"
        )

    def test_no_dropped_skill_refs(self):
        """Skill must not reference any dropped skills."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        for dropped in DROPPED_SKILLS:
            assert f"skills/{dropped}/" not in body, (
                f"running-web-apps: must not reference dropped skill '{dropped}'"
            )

    def test_base_url_in_return_contract(self):
        """Return contract must include base_url field."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        assert "base_url" in body, (
            "running-web-apps: return contract must include base_url (spec §8)"
        )

    def test_web_app_yaml_config_fields(self):
        """The .relay/web-app.yaml config must document url, dev_command, framework fields."""
        _, body = parse_frontmatter(RUNNING_WEB_APPS_SKILL)
        for field in ("url", "dev_command", "framework"):
            assert field in body, (
                f"running-web-apps: .relay/web-app.yaml config must document field '{field}'"
            )


# ---------------------------------------------------------------------------
# Task 6 — Five UI agents: evaluators (visual, ux, accessibility, code) + generator
# ---------------------------------------------------------------------------

# TestUIAgents deleted in PR3 Task 7: all 5 UI agent files git-rm'd; assertions
# superseded by test_roles.py::TestRolesFrontmatterValidity (covers the slugs as roles).
# presets.yaml coverage verified by TestUIRefinementGuards.test_presets_length_is_24.

# ---------------------------------------------------------------------------
# Task 9 — Comprehensive test assertions (spec §10)
# ---------------------------------------------------------------------------


class TestUIRefinementGuards:
    """Seven comprehensive guards for the UI refinement feature (spec §10).

    1. presets.yaml length guard — 24 entries after PR3 §5 (17 collapsed + 2 registered + 5 UI).
    2. ui-code-evaluator parallel: true verification — shim config matches spec §7.
    3. browser critics parallel: false verification — ui-visual/ux/accessibility in shim.
    4. binary shims no convergence_mode regression — spec/plan/pr inherit binary by absence.
    5. no (*) syntax tree-wide — all agent tools: fields use plain names (spike lesson).
    6. convergence_mode not in REFINING_CONTRACT_FIELDS — it is optional, not required.
    7. refining-ui not in REFINING_SHIMS — it is a separate scored-mode shim, not binary.
    """

    # ---- 1. presets.yaml length guard (24 after PR3 §5 migration) ----

    def test_presets_length_is_24(self):
        """bindings/presets.yaml must contain exactly 24 role entries after PR3 §5.

        17 collapsed roles + 2 kept registered (code-reviewer, scout) + 5 UI entries.
        """
        import yaml as _yaml
        presets = _yaml.safe_load(PRESETS_PATH.read_text())
        roles = presets.get("roles", {})
        assert len(roles) == 24, (
            f"bindings/presets.yaml must contain exactly 24 roles; found {len(roles)}. "
            "Expected: 17 collapsed roles + 2 kept registered (code-reviewer, scout) + 5 UI entries."
        )

    # ---- 2. ui-code-evaluator parallel: true verification ----

    def test_ui_code_evaluator_parallel_true(self):
        """ui-code-evaluator must be configured with parallel: true in refining-ui shim.

        ui-code-evaluator is browser-free (source-only) and MUST run in parallel
        with the browser critics (spec §5, §7).
        """
        skill_path = _skill_path("refining-ui")
        if not skill_path.is_file():
            pytest.skip("refining-ui/SKILL.md not yet present")
        _, body = parse_frontmatter(skill_path)
        assert "ui-code-evaluator" in body, (
            "refining-ui shim must reference ui-code-evaluator"
        )
        assert "parallel: true" in body, (
            "refining-ui shim must contain 'parallel: true' for ui-code-evaluator (spec §7)"
        )
        # Order: ui-code-evaluator must appear before the parallel: true entry
        code_eval_idx = body.index("ui-code-evaluator")
        parallel_true_idx = body.index("parallel: true")
        assert code_eval_idx < parallel_true_idx, (
            "refining-ui: ui-code-evaluator must appear before the 'parallel: true' entry"
        )

    # ---- 3. browser critics parallel: false verification ----

    def test_browser_critics_parallel_false(self):
        """Browser critics must be dispatched sequentially (parallel: false) in refining-ui shim.

        ui-visual-evaluator, ui-ux-evaluator, and ui-accessibility-evaluator share one
        Playwright browser instance and MUST run sequentially (spec §5, §7).
        """
        skill_path = _skill_path("refining-ui")
        if not skill_path.is_file():
            pytest.skip("refining-ui/SKILL.md not yet present")
        _, body = parse_frontmatter(skill_path)
        assert "parallel: false" in body, (
            "refining-ui shim must contain 'parallel: false' for browser critics (spec §7)"
        )
        for critic in ("ui-visual-evaluator", "ui-ux-evaluator", "ui-accessibility-evaluator"):
            assert critic in body, (
                f"refining-ui shim must reference browser critic '{critic}' (spec §7)"
            )

    # ---- 4. binary shims no convergence_mode regression ----

    @pytest.mark.parametrize("name", sorted(REFINING_SHIMS))
    def test_binary_shims_no_convergence_mode(self, name):
        """spec/plan/pr shims must NOT contain 'convergence_mode' (inherit binary by absence).

        Binary is the default; shims that don't declare convergence_mode are binary.
        Adding convergence_mode to a binary shim would be a regression (spec §3.4).
        """
        skill_path = _skill_path(name)
        if not skill_path.is_file():
            pytest.skip(f"{name}/SKILL.md not yet present")
        _, body = parse_frontmatter(skill_path)
        assert "convergence_mode" not in body, (
            f"{name}: binary shim must not contain 'convergence_mode' "
            "(binary is inherited by absence — spec §3.4)"
        )

    # ---- 5. no (*) syntax tree-wide ----

    def test_no_star_permission_syntax_in_agent_tools(self):
        """No agent tools: field may use the (*) permission-rule syntax (spike lesson, spec §5).

        The external-composition spike proved that (*) syntax silently de-registers
        agents — they never become available as subagent types. Plain tool-name lists
        are required.  This guard covers every agent in EXPECTED_AGENTS.
        """
        offenders = []
        for slug in sorted(EXPECTED_AGENTS):
            path = _agent_path(slug)
            if not path.is_file():
                continue
            fm, _ = parse_frontmatter(path)
            blob = _normalize_tools(fm.get("tools", ""))
            if "(*)" in blob:
                offenders.append(slug)
        assert not offenders, (
            f"Agent tools: field must not use (*) permission-rule syntax: {offenders}"
        )

    # ---- 6. convergence_mode not in REFINING_CONTRACT_FIELDS ----

    def test_convergence_mode_not_in_refining_contract_fields(self):
        """convergence_mode must NOT appear in REFINING_CONTRACT_FIELDS (it is optional).

        The required-field set covers the 8 mandatory engine contract fields.
        convergence_mode is an optional extension — defaulting to 'binary' when absent.
        Adding it to REFINING_CONTRACT_FIELDS would require all shims to declare it,
        breaking the binary-by-absence convention (spec §3.4).
        """
        assert "convergence_mode" not in REFINING_CONTRACT_FIELDS, (
            "convergence_mode must be optional — it must NOT appear in REFINING_CONTRACT_FIELDS "
            "(binary is the default, inherited by absence; spec §3.4)"
        )

    # ---- 7. refining-ui not in REFINING_SHIMS ----

    def test_refining_ui_not_in_binary_shims(self):
        """refining-ui must NOT be a key in REFINING_SHIMS (it is a scored-mode shim).

        REFINING_SHIMS tracks only the binary-mode shims (spec/plan/pr).  The
        refining-ui shim uses scored convergence and has its own dedicated
        TestRefiningUIShim test class.  Including it in REFINING_SHIMS would
        subject it to binary-mode assertions (e.g. no convergence_mode) which
        would incorrectly fail.
        """
        assert "refining-ui" not in REFINING_SHIMS, (
            "refining-ui must not be in REFINING_SHIMS (it is a scored-mode shim, "
            "not a binary shim; spec §3.4, §7)"
        )


class TestUsingRelayNoWorkflowCheck:
    """diagnose command prose must not describe Workflow-availability conditional degradation."""
    SKILL = PLUGIN_ROOT / "skills" / "using-relay" / "SKILL.md"

    def test_no_disable_workflows_env_var_reference(self):
        body = self.SKILL.read_text()
        assert "CLAUDE_CODE_DISABLE_WORKFLOWS" not in body, \
            "using-relay/SKILL.md must not reference CLAUDE_CODE_DISABLE_WORKFLOWS (Workflow is GA)"

    def test_no_disable_workflows_config_reference(self):
        body = self.SKILL.read_text()
        assert '"disableWorkflows"' not in body, \
            'using-relay/SKILL.md must not reference "disableWorkflows" (Workflow check removed)'

    def test_no_conditional_degradation_prose(self):
        body = self.SKILL.read_text()
        assert "silently degrades" not in body, \
            "using-relay/SKILL.md must not describe silent degradation for Workflow availability"


class TestAgentsReadmeCountAndMechanism:
    """docs/agent-roster.md: post-PR3 §7 — 7-agent roster, S2-corrected wording."""
    README = PLUGIN_ROOT / "docs" / "agent-roster.md"

    def test_count_is_7(self):
        text = self.README.read_text()
        assert "7 agents total" in text, \
            "docs/agent-roster.md must state '7 agents total'"

    def test_old_count_22_and_27_absent(self):
        text = self.README.read_text()
        assert "22 agents total" not in text, \
            "docs/agent-roster.md must not state the old '22 agents total' count"
        assert "27 agents total" not in text, \
            "docs/agent-roster.md must not state the old '27 agents total' count"

    def test_leaf_enforcement_session_initialization(self):
        text = self.README.read_text()
        assert "session initialization" in text or "session init" in text or "absent" in text, \
            "docs/agent-roster.md leaf enforcement description must describe session-init absence"

    def test_leaf_enforcement_absent_not_denied(self):
        text = self.README.read_text()
        assert "absent" in text, \
            "docs/agent-roster.md must say the tool is 'absent' from the session tool set"

    def test_old_denied_at_runtime_claim_removed(self):
        text = self.README.read_text()
        assert "denied at runtime" not in text, \
            "docs/agent-roster.md must not use the old 'denied at runtime' mechanism claim"


class TestPluginVersion350:
    """Version bump for relay 3.5.0 PR1 change-set."""

    def test_version_is_350(self, plugin_json):
        from packaging.version import Version
        assert Version(plugin_json["version"]) >= Version("3.5.0"), (
            f"plugin.json version must be 3.5.0 after PR1 change-set; "
            f"got {plugin_json['version']!r}"
        )


class TestChangelog350:
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_changelog_has_350_entry(self):
        body = self.CHANGELOG.read_text()
        assert "## 3.5.0" in body, "CHANGELOG.md must have a ## 3.5.0 entry"

    def test_changelog_mentions_needs_decision(self):
        body = self.CHANGELOG.read_text()
        assert "needs-decision" in body or "needs_decision" in body or "NEEDS_DECISION" in body, \
            "CHANGELOG 3.5.0 entry must mention the needs-decision bucket"

    def test_changelog_mentions_check_readiness(self):
        body = self.CHANGELOG.read_text()
        assert "check-readiness" in body, \
            "CHANGELOG 3.5.0 entry must mention the check-readiness skill"

    def test_changelog_mentions_public_envelope_contract(self):
        body = self.CHANGELOG.read_text()
        assert "envelope contract" in body or "Public envelope" in body, \
            "CHANGELOG 3.5.0 entry must mention the public envelope contract"


# --- Task 6 (PR3): using-relay orientation, refinement-contract, delegate-leaf ---


class TestUsingRelayLeafRoster:
    """using-relay/SKILL.md must describe the 7-agent roster and roles/ directory."""
    SKILL = _skill_path("using-relay")

    def test_mentions_7_agents_total(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "7 agents" in body or "7-agent" in body, \
            "using-relay must describe the 7-agent roster"

    def test_mentions_roles_directory(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "roles/" in body, \
            "using-relay must mention the roles/ directory"

    def test_implementer_referenced_as_role(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "roles/implementer.md" in body, \
            "using-relay: agents/implementer must be repointed to roles/implementer.md"

    def test_no_agents_implementer_reference(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "agents/implementer" not in body, \
            "using-relay: must not reference agents/implementer (collapsed to role)"


class TestRefinementContractNoCollapsedSlugs:
    """docs/refinement-contract.md must not reference collapsed agentType slugs (§10.2)."""
    DOC = PLUGIN_ROOT / "docs" / "refinement-contract.md"

    def test_no_collapsed_agenttype_refs(self):
        text = self.DOC.read_text()
        collapsed = {
            "relay:spec-simulator", "relay:spec-fixer", "relay:plan-simulator",
            "relay:plan-fixer", "relay:doc-reference-reviewer", "relay:server-runner",
            "relay:fix-coder", "relay:fix-planner", "relay:panel-member",
            "relay:panel-moderator", "relay:panel-synthesizer", "relay:ui-generator",
            "relay:ui-visual-evaluator", "relay:ui-ux-evaluator",
            "relay:ui-accessibility-evaluator", "relay:ui-code-evaluator",
            "relay:implementer", "relay:test-writer", "relay:spec-reviewer",
            "relay:plan-writer", "relay:navigator", "relay:scenario-writer",
        }
        found = [slug for slug in collapsed if slug in text]
        assert not found, f"refinement-contract.md contains collapsed slugs: {found}"

    def test_server_runner_and_fix_coder_use_role_form(self):
        text = self.DOC.read_text()
        assert "roles/server-runner.md" in text, \
            "refinement-contract.md: server-runner must use roles/ form"
        assert "roles/fix-coder.md" in text, \
            "refinement-contract.md: fix-coder must use roles/ form"


class TestDelegateLeafCapabilityValidate:
    """delegate-leaf pre-step must check role requires: against derived leaf tools."""
    SKILL = _skill_path("delegate-leaf")

    def test_capability_validate_step_present(self):
        _, body = parse_frontmatter(self.SKILL)
        assert "CAPABILITY_MISMATCH" in body or "requires:" in body, \
            "delegate-leaf must document CAPABILITY_MISMATCH reject for requires: mismatch"


# --- Task 9 (PR3): version bump to 4.0.0, CHANGELOG entry, top-level README roster counts ---


class TestPluginVersion400:
    """Version bump for relay 4.0.0 PR3 change-set."""

    def test_version_is_400(self, plugin_json):
        from packaging.version import Version
        assert Version(plugin_json["version"]) >= Version("4.0.0"), (
            f"plugin.json version must be 4.0.0 after PR3 change-set; "
            f"got {plugin_json['version']!r}"
        )


class TestChangelog400:
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_changelog_has_400_entry(self):
        body = self.CHANGELOG.read_text()
        assert "## 4.0.0" in body, "CHANGELOG.md must have a ## 4.0.0 entry"

    def test_changelog_mentions_roster_shrink(self):
        body = self.CHANGELOG.read_text()
        assert "27" in body and "7" in body, \
            "CHANGELOG 4.0.0 entry must mention roster change 27→7"

    def test_changelog_mentions_leaf_worker_and_reader(self):
        body = self.CHANGELOG.read_text()
        assert "leaf-worker" in body and "leaf-reader" in body, \
            "CHANGELOG 4.0.0 must mention the two new leaf agents"

    def test_changelog_mentions_roles_directory(self):
        body = self.CHANGELOG.read_text()
        assert "roles/" in body, "CHANGELOG 4.0.0 must mention the roles/ directory"

    def test_changelog_mentions_breaking_capability_deltas(self):
        body = self.CHANGELOG.read_text()
        # §3 two breaking rows: panel web-research dropped; browser via Bash
        assert "panel" in body.lower() or "web" in body.lower(), \
            "CHANGELOG 4.0.0 must mention the panel capability change"
        assert "Playwright" in body or "playwright" in body, \
            "CHANGELOG 4.0.0 must mention the Playwright mechanism change"

    def test_changelog_mentions_24_bindings(self):
        body = self.CHANGELOG.read_text()
        assert "24 bindings" in body or "24 role" in body, \
            "CHANGELOG 4.0.0 must mention the 24 bindings"


class TestReadmeRosterCounts400:
    README = PLUGIN_ROOT / "README.md"

    def test_says_7_agents_total(self):
        text = self.README.read_text()
        assert "7 agents total" in text

    def test_says_22_roles(self):
        text = self.README.read_text()
        assert "22 roles" in text

    def test_says_24_bindings(self):
        text = self.README.read_text()
        assert "24 bindings" in text

    def test_old_agent_counts_absent(self):
        text = self.README.read_text()
        assert "22 agents total" not in text
        assert "27 agents total" not in text
        assert "19 presets-bound" not in text


class TestVersion4330:
    """Relay 4.33.0 — a run that holds a missing step can no longer print `clean`.

    The report node counted the records it did not find, printed the count, and then
    decided the result from `EXIT` and `LABEL` alone. A mandatory step that never ran
    was invisible to the result. Run `wf_6f6f4d1a-4d3` printed `clean` next to
    `RELAY_VERIFY_MISSING=1` after its review step never reached `post`.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.33.0")[1].split("## 4.32.0")[0]
        return re.sub(r"\s+", " ", body)

    @pytest.mark.parametrize(
        "token",
        [
            "RELAY_VERIFY_MISSING",
            "RELAY_VERIFY_REASON=incomplete-round",
            "wf_6f6f4d1a-4d3",
            "test_a_round_with_a_missing_step_is_never_clean",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_entry_states_the_gap_it_leaves_open(self):
        """The gate stops a false clean. It does not make the review step run. An entry
        that claimed the whole defect was closed would overstate what shipped."""
        entry = self._entry()
        assert "It does not make the review step run" in entry

    def test_the_script_gates_clean_on_the_missing_count(self):
        """The rule has to live in the script, not only in the entry that describes it."""
        body = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        assert '[ "$missing" -eq 0 ]' in body
        assert "incomplete-round steps=" in body

    def test_the_skill_states_the_rule_as_a_gate(self):
        """A rule that says only what `missing` is not gets satisfied by never reading
        it, which is exactly how the defect survived."""
        body = (
            PLUGIN_ROOT / "skills" / "verifying-until-clean" / "SKILL.md"
        ).read_text()
        norm = re.sub(r"\s+", " ", body)
        assert "a run that holds any missing" in norm.lower()
        assert "cannot print `clean`" in norm


class TestVersion4340:
    """Relay 4.34.0 — a recorded step failure can no longer print `clean`.

    The 4.33.0 gate only checked for a missing key. A step that ran and recorded
    its own failure, such as `SIMPLIFY=failed:no-reply`, still counted as present,
    so the run could still print `clean` over a step that had already failed. The
    gate is now a positive allow-list over the recorded value, not a list of known
    failure strings, so a value the script has not yet invented is blocked too.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.34.0")[1].split("## 4.33.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4340(self):
        # Superseded exact pin: 4.35.0 carries this line forward (TestVersion4350
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.34.0")

    @pytest.mark.parametrize(
        "token",
        [
            "RELAY_VERIFY_FAILED",
            "allow-list",
            "unverified",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_script_gates_clean_on_the_failed_count(self):
        """The rule has to live in the script, not only in the entry that describes it."""
        body = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        assert "RELAY_VERIFY_FAILED" in body
        assert "failed-step steps=" in body


class TestVersion4350:
    """Relay 4.35.0 — a step that is entered twice can no longer overwrite its own
    record.

    Run `wf_59fede2c-9e2` forked into two live chains inside one session. Both
    chains ran the `review` step: the second chain deleted the first chain's
    reply, appended a second and a third terminal line for `REVIEW`, and the
    report's `tail -1` read kept only the last, corrupted line. That run ended
    `unverified` only because the 4.34.0 `write_state` call had already poisoned
    the state file; the report itself printed `FAILED=0`. Under a passing state
    line the same record makes both the 4.33.0 and the 4.34.0 report print
    `clean`. Guard 5 closes the hole with a write-once claim, taken with an
    atomic `mkdir`, and the report gate now counts terminal lines, not only the
    last value, and prints `conflict:` when a key holds more than one.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.35.0")[1].split("## 4.34.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4350(self):
        # Superseded exact pin: 4.36.0 carries this line forward (TestVersion4360
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.35.0")

    @pytest.mark.parametrize(
        "token",
        [
            "wf_59fede2c-9e2",
            "already-done",
            "conflict:",
            "guard 5",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_script_holds_the_claim(self):
        """The write-once claim has to live in the script, not only in the entry
        that describes it."""
        body = (PLUGIN_ROOT / "scripts" / "verify-loop-node.sh").read_text()
        assert "claim_step()" in body
        assert "step_done()" in body
        assert "recorded_status()" in body
        assert 'mkdir "$(done_marker' in body
        assert "NODE_STATUS=already-done" in body
        assert "conflict:" in body
        assert "Five mechanical guards" in body


class TestVersion4360:
    """Relay 4.36.0 — the feature spine writes its plan and commits its work.

    #86: the spine refined a plan that no node wrote. #78: no node committed the
    work the implement leaf made. The `feature` row gains a conditional
    `write-plan` node, and every row gains a `commit` node before `verify`.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.36.0")[1].split("## 4.35.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4360(self):
        # Superseded exact pin: 4.37.0 carries this line forward (TestVersion4370
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.36.0")

    @pytest.mark.parametrize(
        "token",
        [
            "#86",
            "#78",
            "write-plan",
            "commit",
            "plan_path",
            "SUBJECT_MISSING",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4370:
    """Relay 4.37.0 — using-relay points at the one spine authority.

    #77: `using-relay` listed a spine that disagreed with the §4.2.1 branch
    table, so a model that read `using-relay` built the wrong Workflow. The
    node list and the stale pull-request promise are deleted; a pointer to
    §4.2.1 in `commands/implement.md` replaces both. Relay opens no pull
    request — a person must open it.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.37.0")[1].split("## 4.36.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4370(self):
        # Superseded exact pin: 4.38.0 carries this line forward (TestVersion4380
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.37.0")

    @pytest.mark.parametrize(
        "token",
        [
            "#77",
            "§4.2.1",
            "pull request",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4380:
    """Relay 4.38.0 — the Workflow generator moves into relay:running-implement-spine.

    Steps 3, 3.5, and 4 of `commands/implement.md` — tier resolution, Workflow
    generation, the verify-node guard, the optional verify-until-clean tail,
    `record-run-intent.sh`, and `verify-run-completeness.sh` — move verbatim into a
    new `user-invocable: false` skill. `/relay:implement` keeps Steps 0 through 2,
    the §4.2.1 branch table, and the retro, and now calls the skill and reads its
    one fenced JSON output block.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.38.0")[1].split("## 4.37.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4380(self):
        # Superseded exact pin: 4.39.0 carries this line forward (TestVersion4390
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.38.0")

    @pytest.mark.parametrize(
        "token",
        [
            "running-implement-spine",
            "Step 3.5",
            "run_id",
            "_KNOWN",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4390:
    """Relay 4.39.0 — the relay:implementing-spec adapter (#75).

    `apk/bin/check-deps.sh` probes on disk for `skills/implementing-spec/SKILL.md`
    and blocks when it is absent. This skill is that file: an adapter that gates
    the spec, asks nothing, keeps the branch it finds, and delegates the whole
    run to `relay:running-implement-spine`. It returns `{status, pr_url?}`;
    `pr_url` is always absent, because relay opens no pull request.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.39.0")[1].split("## 4.38.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4390(self):
        # Superseded exact pin: 4.39.1 carries this line forward (TestVersion4391
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.39.0")

    @pytest.mark.parametrize(
        "token",
        [
            "#75",
            "implementing-spec",
            "pr_url",
            "pull request",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4391:
    """Relay 4.39.1 — rewire `relay:running-implement-spine` to its own inputs.

    4.38.0 moved the verify-until-clean tail into a shared skill but left it gated
    on `/relay:implement`-only facts (Step 0's `enabled=1`, `$RELAY_ENGINE`, "the
    last Step 0 axis line"). `relay:implementing-spec` runs neither Step 0 nor Step
    1, so the tail was unreachable on that path and a healthy `apk` run reported
    `error`. The skill now gates on its own `verify` and `engine` inputs, and
    declares a new `axis_source` input for Step 3.5's bookkeeping call.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.39.1")[1].split("## 4.39.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4391(self):
        # Superseded exact pin: 4.39.2 carries this line forward (TestVersion4392
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.39.1")

    @pytest.mark.parametrize(
        "token",
        [
            "axis_source",
            "verify",
            "engine",
            "relay:implementing-spec",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4392:
    """Relay 4.39.2 — `relay:implementing-spec` reads its inputs as `apk` sends them.

    4.39.0 shipped the adapter claiming `apk` calls it as a `skill()` Workflow node
    with one three-key object. Both halves are wrong: `skill()` is not a Workflow
    primitive, `apk` forbids that call form in its own contract test, and
    `apk/phases/build.md` dispatches `agent(prompt, {agentType, schema})` with
    `spec_path`, `branch_hint`, and `closes_issue` as plain `key: value` lines in the
    prompt. A reader told to look for an object could find no input at all.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    SKILL = PLUGIN_ROOT / "skills" / "implementing-spec" / "SKILL.md"
    SPINE = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.39.2")[1].split("## 4.39.1")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4392(self):
        # Superseded exact pin: 4.39.3 carries this line forward (TestVersion4393 ...)
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.39.2")

    @pytest.mark.parametrize(
        "token",
        [
            "agent(prompt",
            "key: value",
            "skill()",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_adapter_shows_the_real_line_format(self):
        body = self.SKILL.read_text()
        assert "spec_path: " in body, (
            "the adapter must show the literal `key: value` line format, because that "
            "is how apk passes its inputs"
        )
        assert "key: value" in body

    def test_the_adapter_does_not_claim_a_skill_node_call(self):
        body = re.sub(r"\s+", " ", self.SKILL.read_text())
        assert "calls this skill as a `skill()` Workflow node" not in body
        assert "passes one object with three keys" not in body

    def test_the_adapter_names_a_concrete_round_cap(self):
        body = re.sub(r"\s+", " ", self.SKILL.read_text())
        assert "RELAY_VERIFY_ROUNDS" in body, (
            "running-implement-spine declares `rounds` as required, so the adapter "
            "must name a value rather than ask for 'a round cap'"
        )

    def test_the_gates_rule_keys_on_the_verify_input_not_the_flag(self):
        body = re.sub(r"\s+", " ", self.SPINE.read_text())
        assert "verify-loop=false unless the verify input is true" in body
        assert "verify-loop=false unless --verify was passed" not in body

    def test_the_spine_skill_does_not_call_itself_a_command(self):
        body = re.sub(r"\s+", " ", self.SPINE.read_text())
        assert "this command generates no second" not in body
        assert "the one skippable role on this command" not in body


class TestVersion4393:
    """Relay 4.39.3 — the spine records the caller that actually ran.

    4.38.0 moved Step 3.5 out of `commands/implement.md` and into
    `relay:running-implement-spine`, and carried its `--command implement` across
    verbatim. 4.39.0 then gave that skill a second caller. From that point every
    `apk`-driven run through `relay:implementing-spec` was recorded as a
    `/relay:implement` run, and `scripts/retro-run.sh` printed
    `RELAY_RETRO_COMMAND=implement` for a run that command never started.

    Same class of gap as the ones 4.39.1 and 4.39.2 closed for `engine`, `axis_source`
    and `--gates`: a value that was true while one caller existed, and became a lie
    when the second one arrived. `record-run-intent.sh` already takes any `--command`
    value, so the fix is one more declared input and one value from each caller.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    SPINE = PLUGIN_ROOT / "skills" / "running-implement-spine" / "SKILL.md"
    ADAPTER = PLUGIN_ROOT / "skills" / "implementing-spec" / "SKILL.md"
    COMMAND = PLUGIN_ROOT / "commands" / "implement.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.39.3")[1].split("## 4.39.2")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4393(self):
        # Superseded exact pin: 4.40.0 carries this line forward (TestVersion4400
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.39.3")

    @pytest.mark.parametrize(
        "token",
        ["RELAY_RETRO_COMMAND", "record-run-intent.sh", "implementing-spec"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_spine_declares_a_command_input(self):
        inputs = self.SPINE.read_text().split("## Inputs")[1].split("\n## ")[0]
        assert re.search(r"^- `command` —", inputs, re.M), (
            "running-implement-spine must declare `command` as an input; it has two "
            "callers and the run record must name the one that ran"
        )

    def test_the_spine_does_not_hardcode_the_command(self):
        body = self.SPINE.read_text()
        assert "--command implement" not in body, (
            "Step 3.5 must pass the `command` input. A hardcoded `implement` records "
            "every relay:implementing-spec run as a /relay:implement run."
        )
        assert '--command "<this run\'s command input>"' in body

    def test_the_l3_command_passes_its_own_name(self):
        body = re.sub(r"\s+", " ", self.COMMAND.read_text())
        assert "`command` (the literal `implement`" in body

    def test_the_adapter_passes_its_own_name(self):
        body = self.ADAPTER.read_text()
        assert "command=implementing-spec" in body
        assert not re.search(r"\bcommand=implement\b", body), (
            "the adapter must not pass `implement` as its command — that is the value "
            "this release exists to stop being recorded for an apk-driven run"
        )

    def test_the_stated_input_count_matches_the_declared_inputs(self):
        """The command names a count in prose. Parse it out, so a new input that is
        added to the skill and not to the command's list fails here."""
        words = {
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
        }
        word = re.search(r"Pass all (\w+) inputs", self.COMMAND.read_text()).group(1)
        assert word in words, f"add {word!r} to the word map"
        inputs = self.SPINE.read_text().split("## Inputs")[1].split("\n## ")[0]
        declared = len(re.findall(r"^- `[a-z_]+`", inputs, re.M))
        assert words[word] == declared, (
            f"commands/implement.md says {word} inputs, but "
            f"running-implement-spine declares {declared}"
        )
class TestVersion4400:
    """Relay 4.40.0 — correctness fixes in the dispatch prose, and three critics
    that no longer filter their own findings.

    The acpx preamble told a blocked fire-and-forget child to return a key-value
    failure token. The watcher classifies on `^BLOCKED:` as the first non-empty
    line, so those tokens matched the generic envelope regex and were captured as
    stray values instead of routing to the blocked bucket. The same paragraph
    promised a panel round-trip for a context request that no code path performs.

    The two simulators and the code reviewer were told to report only what they
    judged worth reporting. The caller owns the severity filter, so a critic that
    pre-filters loses findings no downstream stage can recover.

    `RELAY_MAX_TURNS` was counted inside the driver env-var groups in
    delegate-and-watch and outside them in dispatching-acpx-agents. No driver
    reads it; it is a sidecar value for the watcher, and both skills now say so.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.40.0")[1].split("## 4.39.3")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4400(self):
        # Superseded exact pin: 4.41.0 carries this line forward (TestVersion4410
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.40.0")

    @pytest.mark.parametrize(
        "token",
        [
            "BLOCKED:",
            "When not to dispatch",
            "RELAY_MAX_TURNS",
            "pre-filters nothing",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_preamble_routes_a_block_on_the_first_line(self):
        """The fix has to live in the preamble the child actually reads, not only
        in the entry that describes it."""
        body = (
            PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "preamble.md"
        ).read_text()
        assert "BLOCKED: <reason>" in body
        assert "first line of your final turn" in body
        # The stale tokens routed to the wrong bucket; they must not come back.
        assert "STATUS=" not in body

    def test_relay_max_turns_is_a_sidecar_value_in_both_skills(self):
        """The two skills disagreed on whether a driver reads it. Neither does."""
        claim = "not a driver env var"
        for skill in ("dispatching-acpx-agents", "delegate-and-watch"):
            body = (PLUGIN_ROOT / "skills" / skill / "SKILL.md").read_text()
            assert "RELAY_MAX_TURNS" in body, skill
            assert claim in body, skill

    def test_the_critics_do_not_pre_filter(self):
        """A critic that drops its own findings loses them for every later stage."""
        for role in ("spec-simulator", "plan-simulator"):
            body = (PLUGIN_ROOT / "roles" / f"{role}.md").read_text()
            assert "do not pre-filter" in body, role
            assert "Skip clear requirements silently" not in body, role
            # The calibrated mechanism stays; the clause arguing against
            # reporting does not.
            assert "UNVERIFIED:" in body, role
            assert "costs more than a missed one" not in body, role

    def test_the_code_reviewer_does_not_pre_filter(self):
        """Same defect as the simulators, different wording — the agent body
        needs its own guard or it is the one critic that can regress silently."""
        body = (PLUGIN_ROOT / "agents" / "code-reviewer.md").read_text()
        assert "do not pre-filter" in body
        assert "blockers and importants only" not in body

    def test_ui_generator_names_the_precedence_on_acpx_dispatch(self):
        """The role and the preamble reach one child with opposite commit rules."""
        body = (PLUGIN_ROOT / "roles" / "ui-generator.md").read_text()
        assert "no-commit rule" in body
        assert "leave the commit to" in body


class TestVersion4410:
    """Relay 4.41.0 — unpinned prose cuts across agents, roles, and skills.

    Thirty-five prompt files lost restated copy: reasoning frameworks that
    restated a JSON schema field by field, rules stated three or four times in
    one role, command tables restated as prose, and two near-identical worktree
    state sections. No mechanic changed and no test was edited except this
    ratchet, so a cut that removed a pinned string fails the suite on its own.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.41.0")[1].split("## 4.40.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4410(self):
        # Superseded exact pin: 4.42.0 carries this line forward (TestVersion4420
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.41.0")

    @pytest.mark.parametrize(
        "token",
        ["prose", "strategist", "ensuring-worktree-isolation", "refining"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_strategist_keeps_its_one_scope_sentence(self):
        """The cut replaced a four-item framework with one sentence; that sentence
        is the only thing that still scopes the strategist to the gatherer."""
        body = (PLUGIN_ROOT / "agents" / "strategist.md").read_text()
        assert "Reason only over the gatherer's findings" in body

    def test_the_refining_skill_carries_no_inferred_tags(self):
        body = (PLUGIN_ROOT / "skills" / "refining" / "SKILL.md").read_text()
        assert "[inferred]" not in body

    @pytest.mark.parametrize("skill", ["refining-plans", "refining-specs"])
    def test_the_thin_shims_say_they_inherit(self, skill):
        body = (PLUGIN_ROOT / "skills" / skill / "SKILL.md").read_text()
        assert "No invariant overrides" in body


class TestVersion4420:
    """Relay 4.42.0 — the five L3 commands lose their shared-block essays.

    drive, execute, implement, refine, and diagnose were built from about nine
    near-verbatim shared blocks, each carrying its design history in full. The
    history is now one clause per block; every mechanic, every pinned sentence,
    and every executed bash line is unchanged. verify.md keeps its executed
    fence byte for byte.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.42.0")[1].split("## 4.41.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4420(self):
        # Superseded exact pin: 4.43.0 carries this line forward (TestVersion4430
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.42.0")

    @pytest.mark.parametrize(
        "token",
        ["shared block", "implement.md", "verify.md", "mechanic"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_retro_target_rule_survives_as_one_comment(self):
        """Issue #110 moved the `--retro` extraction (including this comment) out
        of every command body and into scripts/l3-preflight.sh, one copy each."""
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        assert "_retro_target=" in script
        assert "wf_<id>" in script

    @pytest.mark.parametrize(
        "command", ["diagnose", "drive", "execute", "implement", "refine"]
    )
    def test_every_command_still_advertises_retro(self, command):
        """The extraction moved to the script; each command's own argument-hint
        must still advertise --retro so a user sees it without opening the script."""
        fm, _ = parse_frontmatter(PLUGIN_ROOT / "commands" / f"{command}.md")
        hint = str(fm.get("argument-hint", ""))
        assert "--retro" in hint


class TestVersion4430:
    """Relay 4.43.0 — shared contracts live in one place each.

    The writer-role landing contract, the dispatch wrapper block, and the driver
    env-var table each had three to five near-verbatim copies across the
    dispatch skills. `docs/dispatch-contract.md` is now the only full copy; the
    skills keep their deltas and their pinned tokens. The one-shot execution
    paragraph moved into both preambles, so every child reads it once and the
    seven writer roles keep only their own checklist.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    ONE_SHOT = (
        "You run in one-shot exec mode: the turn ends when your final text ends, "
        "so finish the work before you write it, and do not end the turn on "
        "narration."
    )

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.43.0")[1].split("## 4.42.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4430(self):
        # Superseded exact pin: 4.44.0 carries this line forward (TestVersion4440
        # owns the current exact pin).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.43.0")

    @pytest.mark.parametrize(
        "token",
        ["dispatch-contract.md", "one-shot", "CODEX_CONFIG", "preamble"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_canonical_env_table_agrees_with_the_skills(self):
        """The doc used to omit CODEX_CONFIG and imply codex had eight vars."""
        body = (PLUGIN_ROOT / "docs" / "dispatch-contract.md").read_text()
        assert "CODEX_CONFIG" in body
        assert "ACPX_MAX_TURNS" not in body
        assert "ACPX_NUDGE_PROMPT" not in body

    @pytest.mark.parametrize("skill", ["dispatching-acpx-agents", "dispatching-bg-agents"])
    def test_both_preambles_carry_the_one_shot_paragraph_once(self, skill):
        body = (PLUGIN_ROOT / "skills" / skill / "preamble.md").read_text()
        assert body.count(self.ONE_SHOT) == 1, skill

    @pytest.mark.parametrize(
        "role",
        [
            "fix-coder",
            "implementer",
            "plan-fixer",
            "plan-writer",
            "scenario-writer",
            "spec-fixer",
            "test-writer",
        ],
    )
    def test_every_writer_role_states_the_mode_in_the_same_words(self, role):
        body = (PLUGIN_ROOT / "roles" / f"{role}.md").read_text()
        assert body.count(self.ONE_SHOT) == 1, role


class TestVersion4440:
    """Relay 4.44.0 — verifying-until-clean states each rule once.

    The skill loads once per verify run. It carried its terminal states twice,
    the parser trap apart from the verdict contract it belongs to, and a
    55-line commit-scope shell block inline. Each now has one home; the commit
    block is a script with its own test.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    SKILL = PLUGIN_ROOT / "skills" / "verifying-until-clean" / "SKILL.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.44.0")[1].split("## 4.43.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4440(self):
        # Superseded exact pin: 4.46.0 carries this line forward (TestVersion4460
        # holds the exact pin; this one only asserts the floor).
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.44.0")

    @pytest.mark.parametrize(
        "token",
        ["verifying-until-clean", "verify-commit-scope.sh", "narration, never evidence"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_commit_scope_script_exists_and_the_skill_calls_it(self):
        script = PLUGIN_ROOT / "scripts" / "verify-commit-scope.sh"
        assert script.is_file()
        assert "verify-commit-scope.sh" in self.SKILL.read_text()

    def test_the_terminal_states_have_one_home(self):
        """The three-state block used to appear twice; the report node owns it."""
        body = self.SKILL.read_text()
        assert body.count("RELAY_VERIFY_RESULT=clean|findings|unverified") == 1

    def test_the_skill_is_under_the_5a_ceiling(self):
        # 4.48.0: the L3-preflight-script sentence merged in alongside 4.47.0's
        # own edits to this file, so the ceiling moves with both additions.
        words = len(self.SKILL.read_text().split())
        assert words <= 5720, words


class TestVersion4450:
    """Relay 4.45.0 — the codex ladder drops from three tiers to two.

    `gpt-5.6-luna` was the cheap slot for code-writing roles executing against
    an already-vetted plan. Those roles now take `gpt-5.6-terra`, the everyday
    judgment tier, and the luna slot retires on both engines at once — codex
    and its `opencode-go/minimax-m3` mirror.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    PRESETS = PLUGIN_ROOT / "bindings" / "presets.yaml"
    LADDER = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.45.0")[1].split("## 4.44.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4450(self):
        # Superseded exact pin: 4.48.0 carries this line forward (TestVersion4480
        # owns the current exact pin). Same relaxed idiom as TestVersion4150.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.45.0")

    @pytest.mark.parametrize(
        "token",
        ["gpt-5.6-luna", "gpt-5.6-terra", "opencode-go/minimax-m3"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    @pytest.mark.parametrize("retired", ["gpt-5.6-luna", "opencode-go/minimax-m3"])
    def test_no_role_pins_a_retired_tier(self, retired):
        """A pin nothing serves surfaces only at dispatch, as an engine-side
        error in a worker nobody is watching. Catch it here instead."""
        assert retired not in self.PRESETS.read_text(), (
            f"presets.yaml still pins {retired!r} on some role"
        )

    def test_the_header_comment_describes_two_tiers(self):
        """The header is the only prose a reader of the bindings file gets. It
        named three tiers while listing two, and named terra twice."""
        header = self.PRESETS.read_text().split("roles:")[0]
        assert "two GPT-5.6 tiers" in header
        assert "three GPT-5.6 tiers" not in header

    def test_the_ladder_doc_and_the_presets_agree_on_the_tier_count(self):
        """These two drifted for three weeks: the pins moved, the reader's map
        did not. Tie them together so the next tier change cannot repeat it."""
        tiers = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
        pinned = {t for t in tiers if t in self.PRESETS.read_text()}
        documented = {t for t in tiers if t in self.LADDER.read_text()}
        assert pinned == documented, (
            f"presets.yaml pins {sorted(pinned)} but the ladder doc lists "
            f"{sorted(documented)}"
        )


class TestVersion4470:
    """Relay 4.47.0 — the default engine/agent layer is per command, and
    `/relay:implement` + `/relay:verify` default to `acpx` + `claude`."""

    PARSER = PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh"
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    # The two commands that move their default off in-session.
    ACPX_DEFAULT_CMDS = ("implement", "verify")
    # The three that keep it. A default that spread to these would send every refine
    # and every drive run out of process without anyone asking for it.
    IN_SESSION_CMDS = ("refine", "execute", "drive")

    def test_plugin_version_4470(self):
        # Superseded exact pin: 4.48.0 carries this line forward (TestVersion4480
        # owns the current exact pin). Same relaxed idiom as TestVersion4150.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.47.0")

    def test_changelog_has_4470_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.47.0", "RELAY_DEFAULT_ENGINE", "RELAY_DEFAULT_AGENT",
            "--engine acpx --agent claude", "source: default",
        ):
            assert token in body, f"CHANGELOG 4.47.0 entry missing {token!r}"

    def test_parser_reads_both_default_variables(self):
        body = self.PARSER.read_text()
        assert '_relay_def_engine="$(_re_lc "${RELAY_DEFAULT_ENGINE:-}")"' in body
        assert '_relay_def_agent="$(_re_lc "${RELAY_DEFAULT_AGENT:-}")"' in body

    def test_parser_clears_both_default_variables(self):
        """One command's default must not reach the next command in the same shell.
        Same contract as the two model flag variables."""
        body = self.PARSER.read_text()
        assert "unset RELAY_DEFAULT_ENGINE RELAY_DEFAULT_AGENT" in body

    def test_the_default_engine_falls_back_to_in_session(self):
        """The command default is a substitution on the SAME line, so there is one
        default site, not two that can drift."""
        body = self.PARSER.read_text()
        assert '_relay_engine="${_relay_def_engine:-in-session}"' in body

    def test_the_default_agent_is_gated_on_the_engine_source(self):
        """An explicit `--engine smart-routing` must still derive its own agent. Drop
        this gate and that flag fails an invariant the user did not trip."""
        body = self.PARSER.read_text()
        assert '[ "$_engine_src" = "default" ] && [ -n "$_relay_def_agent" ]' in body

    def test_an_invalid_command_default_names_its_origin(self):
        """A typo in a command body is a plugin bug. Reporting it as a user typo is
        the silent-failure shape this repo keeps hitting."""
        body = self.PARSER.read_text()
        assert "from this command's built-in default" in body

    @pytest.mark.parametrize("name", ACPX_DEFAULT_CMDS)
    def test_command_exports_the_acpx_default(self, name):
        # 4.48.0: the export moved out of the command .md body and into
        # scripts/l3-preflight.sh's <name> case block; the .md body now only
        # forwards $ARGUMENTS to the script.
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/scripts/l3-preflight.sh" {name} "$ARGUMENTS"' in body
        block = _l3_case_block((PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text(), name)
        assert block is not None, f"scripts/l3-preflight.sh: no {name}) case block found"
        assert 'export RELAY_DEFAULT_ENGINE="acpx"' in block
        assert 'export RELAY_DEFAULT_AGENT="claude"' in block

    @pytest.mark.parametrize("name", ACPX_DEFAULT_CMDS)
    def test_the_exports_precede_the_parse(self, name):
        """An export after the source line reaches nothing and changes nothing —
        exactly the silent no-op the two model flags had to be fixed for."""
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        block = _l3_case_block(script, name)
        assert block is not None, f"scripts/l3-preflight.sh: no {name}) case block found"
        assert block.index('export RELAY_DEFAULT_ENGINE="acpx"') < block.index(
            'source "$HERE/parse-engine-agent.sh" "$_engine" "$_agent"'
        )

    @pytest.mark.parametrize("name", IN_SESSION_CMDS)
    def test_the_other_commands_keep_the_in_session_default(self, name):
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        assert "RELAY_DEFAULT_ENGINE" not in body
        assert "RELAY_DEFAULT_AGENT" not in body

    @pytest.mark.parametrize("name", ACPX_DEFAULT_CMDS)
    def test_the_command_states_its_own_default(self, name):
        """A user reading the command must not have to read the parser to learn
        where the run goes."""
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        assert "acpx" in body and "default" in body

    def test_implement_step_025_leads_with_acpx(self):
        body = (PLUGIN_ROOT / "commands" / "implement.md").read_text()
        assert "**Option 1 (listed first = default):** label `acpx (default)`" in body
        # The hybrid split stays reachable from the menu, not only from a flag.
        assert "acpx (hybrid)" in body
        assert "in-session (claude)" in body
        assert "bg-sessions (claude)" in body

    def test_implement_step_025_can_re_resolve_to_in_session(self):
        """Every non-default answer needs its own re-resolution block, or the
        transcript's last axis line disagrees with the run. All three re-resolve
        through the script's --axis-only mode — an inline `source` here would
        trip the same worktree-refusal gate Step 0 itself moved into the script
        to satisfy."""
        body = (PLUGIN_ROOT / "commands" / "implement.md").read_text()
        assert "--axis-only acpx hybrid --source prompt" in body
        assert "--axis-only in-session claude --source prompt" in body
        assert "--axis-only bg-sessions claude --source prompt" in body

    def test_the_verify_loop_skill_no_longer_calls_in_session_the_default(self):
        """The caller owns the default now, so the skill must not name one."""
        body = (
            PLUGIN_ROOT / "skills" / "verifying-until-clean" / "SKILL.md"
        ).read_text()
        assert "`in-session` — the default" not in body

    def test_the_docs_state_the_per_command_default(self):
        for path in (
            PLUGIN_ROOT / "docs" / "architecture.md",
            PLUGIN_ROOT / "skills" / "using-relay" / "SKILL.md",
        ):
            body = path.read_text()
            assert "acpx" in body and "default" in body
            assert "/relay:verify" in body


class TestVersion4460:
    """Relay 4.46.0 — the `category` field on a role, and the two model flags
    `--fixes-model` / `--verification-model` that address a whole category."""

    PRESETS = PLUGIN_ROOT / "bindings" / "presets.yaml"
    PARSER = PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh"
    RESOLVER = PLUGIN_ROOT / "scripts" / "resolve-tier.sh"
    LADDER = PLUGIN_ROOT / "skills" / "selecting-the-right-model" / "SKILL.md"
    ACPX = PLUGIN_ROOT / "skills" / "dispatching-acpx-agents" / "acpx-dispatch.sh"
    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    # The commands that accept the two flags. /relay:verify and /relay:diagnose
    # deliberately do not — see test_verify_and_diagnose_take_no_model_flag.
    FLAG_CMD_NAMES = ("implement", "refine", "execute", "drive")

    CATEGORIES = {
        "fixes": ({"spec-fixer", "plan-fixer", "fix-planner", "fix-coder"}, "sonnet"),
        "verification": (
            {
                "spec-reviewer", "code-reviewer", "doc-reference-reviewer",
                "ui-visual-evaluator", "ui-ux-evaluator",
                "ui-accessibility-evaluator", "ui-code-evaluator",
            },
            "opus",
        ),
    }
    # Narrower than FLAT_MODEL_ENUM on purpose: a flag chooses a model for a group of
    # roles, neither group holds a mechanical role (so no `haiku`), and `inherit` is a
    # per-role property a flag must not erase.
    FLAG_MODEL_ENUM = ("sonnet", "opus", "fable")

    def test_plugin_version_4460(self):
        # Superseded exact pin: 4.47.0 carries this line forward (TestVersion4470
        # owns the current exact pin). Same relaxed idiom as TestVersion4450.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.46.0")

    def test_changelog_has_4460_entry(self):
        body = self.CHANGELOG.read_text()
        for token in (
            "## 4.46.0", "--fixes-model", "--verification-model",
            "category", "fixes_model", "verification_model",
        ):
            assert token in body, f"CHANGELOG 4.46.0 entry missing {token!r}"

    @pytest.mark.parametrize("category", sorted(CATEGORIES))
    def test_category_membership(self, category):
        expected, _ = self.CATEGORIES[category]
        roles = _load_presets()["roles"]
        actual = {s for s, e in roles.items() if e.get("category") == category}
        assert actual == expected

    @pytest.mark.parametrize("category", sorted(CATEGORIES))
    def test_every_role_of_a_category_shares_one_model(self, category):
        """A flag reports one change for the whole category. If the members
        disagreed, the flag would report a change it did not make on some of them,
        and the default the docs state would be true of only part of the group."""
        expected, model = self.CATEGORIES[category]
        roles = _load_presets()["roles"]
        for slug in expected:
            assert roles[slug]["model"] == model, (
                f"{slug} is category {category} and must default to {model}"
            )

    def test_a_role_carries_at_most_one_known_category(self):
        """`category` is a scalar, so no role can be reached by both flags. An
        unknown value would be a flag nothing addresses."""
        roles = _load_presets()["roles"]
        for slug, entry in roles.items():
            cat = entry.get("category")
            assert cat is None or cat in self.CATEGORIES, (
                f"{slug} carries an unknown category {cat!r}"
            )

    def test_uncategorized_roles_stay_uncategorized(self):
        """Neither flag may reach a role outside the two groups. Pinned so that
        adding a category to a role is a deliberate edit with a test to update."""
        roles = _load_presets()["roles"]
        categorized = set().union(*(m for m, _ in self.CATEGORIES.values()))
        for slug in roles:
            if slug not in categorized:
                assert roles[slug].get("category") is None, (
                    f"{slug} gained a category; update TestVersion4460.CATEGORIES"
                )

    @pytest.mark.parametrize("script_attr", ["PARSER", "RESOLVER"])
    def test_both_readers_state_the_same_flag_enum(self, script_attr):
        """The parser validates at Step 0 and the resolver validates standalone.
        A value one accepted and the other rejected would fail mid-run."""
        body = getattr(self, script_attr).read_text()
        assert "sonnet | opus | fable" in body, (
            f"{script_attr} must name the flag enum in its error message"
        )
        assert "haiku | sonnet | opus | inherit" not in body, (
            f"{script_attr} still offers the wide ladder on the flag axis"
        )

    def test_parser_exports_both_axes_and_their_source(self):
        body = self.PARSER.read_text()
        for token in (
            "export RELAY_FIXES_MODEL=",
            "export RELAY_VERIFICATION_MODEL=",
            "export RELAY_MODEL_SOURCE=",
            "unset RELAY_FIXES_MODEL_FLAG RELAY_VERIFICATION_MODEL_FLAG",
        ):
            assert token in body, f"parse-engine-agent.sh missing {token!r}"

    def test_resolver_reads_the_category_column(self):
        body = self.RESOLVER.read_text()
        assert "category:" in body, "the awk table must capture the category field"
        assert "_rt_categorized" in body
        # Both output paths must run the override, or `--all` and a single-role
        # lookup would disagree about the same role.
        assert body.count("| _rt_categorized") == 2, (
            "both the --all table and the single-role lookup must apply the override"
        )

    def test_resolver_header_states_both_axes(self):
        """A flag that reached no row must still be visible in the block that shows
        the rows it did not change."""
        body = self.RESOLVER.read_text()
        assert "fixes-model:" in body
        assert "verification-model:" in body
        assert "reach no in-session row" in body, (
            "with tiers off the header must say the overrides changed nothing"
        )

    @pytest.mark.parametrize("name", FLAG_CMD_NAMES)
    def test_command_parses_both_flags(self, name):
        # 4.48.0: the flag parsing moved out of the command .md body and into
        # scripts/l3-preflight.sh's <name> case block; the .md body now only
        # forwards $ARGUMENTS to the script.
        body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/scripts/l3-preflight.sh" {name} "$ARGUMENTS"' in body
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        block = _l3_case_block(script, name)
        assert block is not None, f"scripts/l3-preflight.sh: no case block for {name!r}"
        assert "export RELAY_FIXES_MODEL_FLAG=" in block, (
            f"scripts/l3-preflight.sh: {name!r} case must pass the flag to the parser "
            "as an environment variable"
        )
        assert "export RELAY_VERIFICATION_MODEL_FLAG=" in block
        assert "[relay] model overrides:" in block, (
            f"scripts/l3-preflight.sh: {name!r} case must echo the resolved overrides, "
            "like the axis line"
        )

    @pytest.mark.parametrize("name", FLAG_CMD_NAMES)
    def test_command_sets_the_flag_variables_before_it_sources_the_parser(self, name):
        """The parser reads these at source time. Exporting them after the source
        line would make both flags silently do nothing."""
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        block = _l3_case_block(script, name)
        assert block is not None, f"scripts/l3-preflight.sh: no case block for {name!r}"
        assert block.index("export RELAY_FIXES_MODEL_FLAG=") < block.index(
            'source "$HERE/parse-engine-agent.sh" "$_engine" "$_agent"'
        )

    @pytest.mark.parametrize("name", FLAG_CMD_NAMES)
    def test_command_hint_names_the_flag_enum(self, name):
        fm, _ = parse_frontmatter(PLUGIN_ROOT / "commands" / f"{name}.md")
        hint = fm.get("argument-hint", "")
        enum = "|".join(self.FLAG_MODEL_ENUM)
        assert f"--fixes-model {enum}" in hint
        assert f"--verification-model {enum}" in hint

    def test_drive_strips_both_flags_from_the_oracle(self):
        """drive reads the oracle path as the token left after the flags are
        stripped. An unstripped flag becomes the oracle path and the run dies."""
        script = (PLUGIN_ROOT / "scripts" / "l3-preflight.sh").read_text()
        block = _l3_case_block(script, "drive")
        assert block is not None, "scripts/l3-preflight.sh: no drive) case block found"
        strip = [ln for ln in block.splitlines() if "--retro[ =]+(wf_" in ln][0]
        assert "--fixes-model[ =]" in strip
        assert "--verification-model[ =]" in strip

    @pytest.mark.parametrize("name", ["verify", "diagnose"])
    def test_verify_and_diagnose_take_no_model_flag(self, name):
        """/relay:verify dispatches no role — its nodes are pinned wrappers around
        commands relay does not own. /relay:diagnose has no Step 0. Offering a flag
        that reaches nothing is worse than not offering it."""
        fm, _ = parse_frontmatter(PLUGIN_ROOT / "commands" / f"{name}.md")
        assert "--fixes-model" not in fm.get("argument-hint", "")
        assert "--verification-model" not in fm.get("argument-hint", "")

    def test_acpx_applies_the_override_on_the_claude_leg_only(self):
        """sonnet/opus/fable are Claude ids. Forwarding one to codex or opencode
        fails engine-side, so those legs keep the modality pin and say so."""
        body = self.ACPX.read_text()
        assert "RELAY_CATEGORY=" in body
        assert "RELAY_FIXES_MODEL:-" in body
        assert "RELAY_VERIFICATION_MODEL:-" in body
        assert "is not a Claude leg" in body, (
            "a non-Claude leg must warn, not silently drop the override"
        )

    def test_bg_dispatch_applies_the_override_too(self):
        """A bg-session is always `claude --bg`, so it is a Claude leg. Without this
        the two flags would resolve, print, and change nothing under
        `--engine bg-sessions` — the exact silent-failure shape they guard against."""
        body = (
            PLUGIN_ROOT / "skills" / "dispatching-bg-agents" / "bg-dispatch.sh"
        ).read_text()
        assert "_bgd_category=" in body
        assert "RELAY_FIXES_MODEL:-" in body
        assert "RELAY_VERIFICATION_MODEL:-" in body
        assert "replaces modalities.claude.model" in body, (
            "the substitution must be announced, not silent"
        )

    def test_the_ladder_doc_names_both_flags_and_the_categories(self):
        body = self.LADDER.read_text()
        for token in ("--fixes-model", "--verification-model",
                      "fixes_model", "verification_model"):
            assert token in body, f"selecting-the-right-model must document {token!r}"
        for category in self.CATEGORIES:
            assert f"`{category}`" in body


class TestVersion4480:
    """Relay 4.48.0 — auto permission mode, bg session cleanup, nested dispatch depth cap.

    `approve-all` now lowers to `auto` and a child that meets a classifier refusal
    writes a typed BLOCKED line and stops. `scripts/bg-cleanup.sh` deletes the
    background sessions a run created, `/relay:implement` gains `--keep-sessions`,
    and nested bg dispatch is capped at depth 1 in bg-dispatch.sh.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.48.0")[1].split("## 4.47.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4480(self):
        # Superseded exact pin: 4.49.0 carries this line forward (TestVersion4490
        # owns the current exact pin). Same relaxed idiom as TestVersion4470.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.48.0")

    @pytest.mark.parametrize(
        "token",
        ["bg-cleanup.sh", "--keep-sessions", "auto", "classifier refused"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_bg_cleanup_script_exists_and_is_executable(self):
        script = PLUGIN_ROOT / "scripts" / "bg-cleanup.sh"
        assert script.exists(), "scripts/bg-cleanup.sh missing"
        assert os.access(script, os.X_OK), "bg-cleanup.sh must be executable"


class TestVersion4490:
    """Relay 4.49.0 — L3 Step 0 moved into scripts/l3-preflight.sh (issue #110).

    Every six-command Step 0 inline bash block — the dependency gate,
    --verify/--rounds validation, --retro extraction, and engine/agent axis
    resolution — refused a session isolated in a git worktree. The block now
    lives in one script, called with one line. worktree-preflight.sh gained a
    --branch-guard mode for the same reason. The script also carries the
    --fixes-model/--verification-model parsing, the
    RELAY_DEFAULT_ENGINE/RELAY_DEFAULT_AGENT exports, and the --keep-sessions
    flag that 4.46.0, 4.47.0 and 4.48.0 added inline, so the move regresses
    no feature.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    L3_PREFLIGHT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.49.0")[1].split("## 4.48.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_plugin_version_4490(self):
        # Superseded exact pin: 4.50.0 carries this line forward (TestVersion4500
        # owns the current exact pin). Same relaxed idiom as TestVersion4480.
        import json

        from packaging.version import Version

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert Version(manifest["version"]) >= Version("4.49.0")

    def test_l3_preflight_script_exists_and_is_executable(self):
        assert self.L3_PREFLIGHT.is_file()
        assert os.access(self.L3_PREFLIGHT, os.X_OK)

    @pytest.mark.parametrize(
        "token",
        ["l3-preflight.sh", "--branch-guard", "worktree", "110"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_script_carries_the_ported_model_flags(self):
        """The script replaced the inline Step 0 block that 4.46.0 and 4.47.0 had
        already extended — the port must be in the script now, not dropped."""
        body = self.L3_PREFLIGHT.read_text()
        assert "export RELAY_FIXES_MODEL_FLAG=" in body
        assert "export RELAY_VERIFICATION_MODEL_FLAG=" in body
        assert "[relay] model overrides:" in body

    def test_the_script_carries_the_ported_default_layer(self):
        body = self.L3_PREFLIGHT.read_text()
        assert 'export RELAY_DEFAULT_ENGINE="acpx"' in body
        assert 'export RELAY_DEFAULT_AGENT="claude"' in body

    def test_the_script_carries_the_ported_keep_sessions_flag(self):
        """4.48.0 added --keep-sessions to the inline block this script replaced."""
        body = self.L3_PREFLIGHT.read_text()
        assert "--keep-sessions" in body
        assert "RELAY_KEEP_SESSIONS=" in body


class TestVersion4520:
    """Relay 4.52.0 — the integration-test harness lands under `tests/integration/`.

    `make itest` runs the gates, e2e, and acpx live-contract tiers. Double-gated:
    the `integration` marker is deselected by default and `RELAY_ITEST=1` is
    required, so CI's bare `pytest tests/` never runs it. The `results/` tree is
    git-ignored.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_plugin_version_is_4520(self):
        import json

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        assert manifest["version"] == "4.52.0"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.52.0")[1].split("## 4.51.0")[0]
        return re.sub(r"\s+", " ", body)

    @pytest.mark.parametrize(
        "token",
        [
            "make itest",
            "integration",
            "RELAY_ITEST",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4510:
    """Relay 4.51.0 — acpx 0.13.2 floor, wide permission grant, structured envelope.

    One floor in `scripts/acpx-floor.sh` enforced by `l3-preflight.sh`; every acpx
    turn carries `--approve-all --permission-policy`; the codex `--agent` override
    is retired; codex effort moves to session config; `acpx-envelope.sh` rebuilds
    the reply from the JSON stream; `delegate-and-watch` gains an `errored` reason
    for a session-config replay failure.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"

    def test_the_4510_entry_is_still_recorded(self):
        """4.52.0 holds the exact version pin; this class keeps 4.51.0's own gates."""
        assert "## 4.51.0" in self.CHANGELOG.read_text()

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.51.0")[1].split("## 4.50.0")[0]
        return re.sub(r"\s+", " ", body)

    @pytest.mark.parametrize(
        "token",
        [
            "acpx-floor.sh",
            "acpx-policy.json",
            "acpx-envelope.sh",
            "ACPX_CODEX_AGENT_OVERRIDE",
            "config_replay_failed",
            "agent-full-access",
        ],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()


class TestVersion4500:
    """Relay 4.50.0 — `--worktree` pre-answers the Step 0.5 isolation gate.

    The four gated L3 commands take `--worktree current|<path>|<branch>` and pass
    it to the gate. worktree-preflight.sh gains `--resolve`, `--create --at`, and
    `--active`; `--classify` widens to any linked worktree; the literal WORKTREE
    path flows into every generated dispatch; implementing-spec gains a `worktree`
    input and a mismatch guard. Closes #112.
    """

    CHANGELOG = PLUGIN_ROOT / "CHANGELOG.md"
    L3_PREFLIGHT = PLUGIN_ROOT / "scripts" / "l3-preflight.sh"
    WT_PREFLIGHT = PLUGIN_ROOT / "scripts" / "worktree-preflight.sh"

    def _entry(self):
        body = self.CHANGELOG.read_text().split("## 4.50.0")[1].split("## 4.49.0")[0]
        return re.sub(r"\s+", " ", body)

    def test_the_4500_entry_is_still_recorded(self):
        """4.51.0 holds the exact version pin; this class keeps 4.50.0's own gates."""
        assert "## 4.50.0" in self.CHANGELOG.read_text()

    @pytest.mark.parametrize(
        "token",
        ["--worktree", "--resolve", "--at <path>", "--active", "#112"],
    )
    def test_the_entry_names_what_shipped(self, token):
        assert token in self._entry()

    def test_the_flag_is_parsed_in_the_preflight_script(self):
        """4.49.0 moved Step 0 into l3-preflight.sh, and the static gate refuses the
        `case`/`if` shapes this parsing needs. So it belongs in the script, never
        inline in a command body."""
        body = self.L3_PREFLIGHT.read_text()
        assert "_extract_worktree()" in body
        assert "RELAY_WT_ARG=" in body

    def test_the_gated_commands_call_the_active_mode_not_an_inline_rev_parse(self):
        for name in ("implement", "refine", "execute", "drive"):
            body = (PLUGIN_ROOT / "commands" / f"{name}.md").read_text()
            assert "worktree-preflight.sh\" --active" in body, name
            assert "rev-parse --show-toplevel" not in body, name

    def test_the_preflight_script_carries_the_three_new_modes(self):
        body = self.WT_PREFLIGHT.read_text()
        for fn in ("_wt_resolve()", "_wt_active()"):
            assert fn in body, fn
        assert "--active)" in body
        assert "--resolve)" in body

    def test_drive_strips_the_flag_from_its_oracle(self):
        """The oracle is the lone token left after the flags are stripped, so a
        --worktree value left in would be read as the oracle path."""
        body = self.L3_PREFLIGHT.read_text()
        oracle = [ln for ln in body.splitlines() if "--verification-model[ =]" in ln
                  and "sed -E" in ln]
        assert oracle, "drive's oracle strip line not found"
        assert "--worktree[ =]" in oracle[0]
