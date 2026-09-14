"""Freshness gate for docs/architecture.md and docs/contributing.md (4.18.0).

Onboarding documentation rots faster than anything else in a plugin, because
nothing breaks when it goes stale — it just quietly starts lying to the next
contributor.

Relay already has an answer to that: prose is source code here, so it is tested
like source code. `roles/README.md` must literally contain "22 roles";
`docs/agent-roster.md` must contain "7 agents total". This module extends the same
mechanism to the two narrative documents, pinning the specific claims that go stale:

  * every repo-relative link resolves to a real file;
  * every referenced script path exists;
  * the agent / role / skill counts match the directories;
  * the tier rungs named in the doc are exactly the rungs presets.yaml uses;
  * the axis enum values match parse-engine-agent.sh.

Each test also guards against going vacuous — a regex that silently matches nothing
would turn this whole module into a no-op, which is the failure mode it exists to
prevent.
"""

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
DOCS = PLUGIN_ROOT / "docs"
ARCHITECTURE = DOCS / "architecture.md"
CONTRIBUTING = DOCS / "contributing.md"

NARRATIVE_DOCS = (ARCHITECTURE, CONTRIBUTING)

MD_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
# Backticked paths that look like repo files: a/b.ext
CODE_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:sh|py|js|md|json|yaml))`")


def _counts():
    return {
        "agents": len(list((PLUGIN_ROOT / "agents").glob("*.md"))),
        "roles": len(list((PLUGIN_ROOT / "roles").glob("*.md"))) - 1,  # minus README
        "skills": len([p for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir()]),
    }


@pytest.mark.parametrize("doc", NARRATIVE_DOCS, ids=lambda p: p.name)
class TestDocExists:
    def test_present_and_substantial(self, doc):
        assert doc.is_file(), f"{doc.name} is missing"
        assert len(doc.read_text()) > 2000, f"{doc.name} is too short to be the real thing"


@pytest.mark.parametrize("doc", NARRATIVE_DOCS, ids=lambda p: p.name)
class TestLinksResolve:
    def test_relative_links_resolve(self, doc):
        text = doc.read_text()
        targets = [t for t in MD_LINK.findall(text) if not t.startswith(("http", "#"))]
        assert targets, f"{doc.name}: no relative links found — guard has gone vacuous"
        broken = []
        for t in targets:
            target = t.split("#", 1)[0]
            if not target:
                continue
            if not (doc.parent / target).resolve().exists():
                broken.append(t)
        assert not broken, f"{doc.name}: broken relative links: {broken}"

    def test_backticked_paths_exist(self, doc):
        """Catches a doc that still names a file after a rename."""
        text = doc.read_text()
        candidates = set(CODE_PATH.findall(text))
        # Only check paths that look repo-rooted (contain a directory separator)
        # and that we would expect to live inside the plugin.
        checkable = {
            c for c in candidates
            if "/" in c and c.split("/", 1)[0] in
            {"agents", "roles", "skills", "commands", "docs", "scripts", "tests", "bindings", "tools"}
        }
        assert checkable, f"{doc.name}: no checkable backticked paths — guard has gone vacuous"
        missing = sorted(c for c in checkable if not (PLUGIN_ROOT / c).exists())
        assert not missing, f"{doc.name}: references non-existent paths: {missing}"


class TestArchitectureCountsMatchTree:
    def test_count_row_is_current(self):
        """The agent/role count row must match the directories."""
        c = _counts()
        expected = f"| count | {c['agents']} | {c['roles']} |"
        text = ARCHITECTURE.read_text()
        assert expected in text, (
            f"architecture.md count row is stale. Expected {expected!r} "
            f"(agents={c['agents']}, roles={c['roles']})."
        )

    def test_agent_roster_count_agrees(self):
        """The roster doc and the tree must not disagree with each other."""
        c = _counts()
        roster = (DOCS / "agent-roster.md").read_text()
        assert f"{c['agents']} agents total" in roster, (
            f"docs/agent-roster.md must state '{c['agents']} agents total'"
        )

    def test_skill_inventory_numbers_are_current(self):
        """`_counts()['skills']` was computed and never asserted, while
        architecture.md claimed the gate checked skill counts. Either the claim or
        the check had to go; the check is the useful half.

        contributing.md names where each skill constant lives and how many entries it
        holds, because those constants are what a contributor must edit when adding a
        skill. Pin each number to the constant it describes, and pin their sum to the
        directory count so a skill in NO constant is caught too — ten were.
        """
        import re as _re
        c = _counts()
        contributing = CONTRIBUTING.read_text()

        sizes = {}
        for const, path in (
            ("EXPECTED_SKILLS", "test_plugin.py"),
            ("L2_NAMES", "test_l2_skills_present.py"),
            ("RESOLUTION_POLICY_SKILLS", "test_l2_skills_present.py"),
        ):
            src = (PLUGIN_ROOT / "tests" / "unit" / "skill-structure" / path).read_text()
            m = _re.search(rf"{const}\s*=\s*[\{{\[](.*?)[\}}\]]", src, _re.S)
            assert m, f"could not locate {const} in {path}"
            sizes[const] = len(_re.findall(r'"[a-z0-9-]+"', m.group(1)))

        for const, n in sizes.items():
            assert f"`{const}` ({n})" in contributing, (
                f"contributing.md must state {const} holds {n} entries; "
                f"found none matching '`{const}` ({n})'"
            )

        # +1 for classifying-task-kind, which sits in no constant by design.
        assert sum(sizes.values()) + 1 == c["skills"], (
            f"skill constants cover {sum(sizes.values()) + 1} skills but "
            f"{c['skills']} directories exist — a skill is in no constant"
        )


class TestArchitectureTierRungsMatchPresets:
    def test_named_rungs_are_the_rungs_in_use(self):
        presets = (PLUGIN_ROOT / "bindings" / "presets.yaml").read_text()
        in_use = set(re.findall(r"^\s*model:\s*(haiku|sonnet|opus|inherit)\s*$", presets, re.M))
        assert in_use, "no flat model: rungs found in presets.yaml — guard has gone vacuous"

        text = ARCHITECTURE.read_text()
        missing = sorted(r for r in in_use if f"`{r}`" not in text)
        assert not missing, (
            f"architecture.md does not document tier rungs currently in use: {missing}"
        )

    def test_doc_names_no_retired_rung(self):
        """A rung dropped from presets must be dropped from the doc too."""
        presets = (PLUGIN_ROOT / "bindings" / "presets.yaml").read_text()
        in_use = set(re.findall(r"^\s*model:\s*(haiku|sonnet|opus|inherit)\s*$", presets, re.M))
        text = ARCHITECTURE.read_text()
        # Only inspect the tier table region, so prose mentioning a model elsewhere
        # does not trip the check.
        start = text.find("| Rung | Criterion |")
        assert start != -1, "architecture.md tier table heading not found — doc restructured?"
        table = text[start:text.find("\n\n", start)]
        documented = set(re.findall(r"`(haiku|sonnet|opus|inherit)`", table))
        assert documented <= in_use, (
            f"architecture.md tier table names retired rungs: {sorted(documented - in_use)}"
        )


class TestArchitectureAxisMatchesParser:
    """The enum in the doc must match the enum the parser actually accepts."""

    def _parser_enums(self):
        src = (PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh").read_text()
        engine = re.search(r"case \"\$_relay_engine\" in ([^)]+)\)", src)
        agent = re.search(r"case \"\$_relay_agent\" in ([^)]+)\)", src)
        assert engine and agent, "could not read axis enums from parse-engine-agent.sh"
        return (
            [v.strip() for v in engine.group(1).split("|")],
            [v.strip() for v in agent.group(1).split("|")],
        )

    def test_engine_values_documented(self):
        engines, _ = self._parser_enums()
        assert engines, "no engine values parsed — guard has gone vacuous"
        text = ARCHITECTURE.read_text()
        missing = [e for e in engines if f"`{e}`" not in text]
        assert not missing, f"architecture.md omits accepted engine values: {missing}"

    def test_agent_values_documented(self):
        _, agents = self._parser_enums()
        assert agents, "no agent values parsed — guard has gone vacuous"
        text = ARCHITECTURE.read_text()
        missing = [a for a in agents if f"`{a}`" not in text]
        assert not missing, f"architecture.md omits accepted agent values: {missing}"


class TestReadmeLinksTheNarrativeDocs:
    """An unreferenced doc is a doc nobody finds."""

    def test_readme_links_architecture_and_contributing(self):
        readme = (PLUGIN_ROOT / "README.md").read_text()
        for target in ("docs/architecture.md", "docs/contributing.md"):
            assert target in readme, f"README.md must link {target}"


class TestContributingNamesRealCommands:
    def test_referenced_test_scripts_exist(self):
        text = CONTRIBUTING.read_text()
        shell_suites = re.findall(r"(tests/unit/skill-structure/test_\w+\.sh)", text)
        assert shell_suites, "contributing.md names no shell suites — guard has gone vacuous"
        missing = sorted(s for s in set(shell_suites) if not (PLUGIN_ROOT / s).exists())
        assert not missing, f"contributing.md names non-existent shell suites: {missing}"

    def test_version_example_matches_manifest(self):
        """The worked example must use the version actually shipping."""
        import json
        version = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )["version"]
        text = CONTRIBUTING.read_text()
        assert f'assert manifest["version"] == "{version}"' in text, (
            f"contributing.md version example must show the current version {version!r}"
        )


# --------------------------------------------------------------------------- #
# Architecture Decision Records
#
# The point of an ADR is that a past decision stays readable after it stops being
# true. That only works if `status:` is maintained — an unmaintained status field is
# worse than none, because it projects false currency. relay already had that failure:
# docs/superpowers/specs/2026-06-24-…-design.md still reads
# "Status: design (approved in substance)" for the Step 0.0 session rename, which
# shipped in v4.5.0 and was removed two releases later.
# --------------------------------------------------------------------------- #

ADR_DIR = DOCS / "adr"
ADR_INDEX = ADR_DIR / "README.md"
VALID_STATUSES = {"proposed", "accepted", "deprecated", "superseded"}
ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")


def _adr_files():
    return sorted(p for p in ADR_DIR.glob("*.md") if ADR_FILE.match(p.name))


def _adr_frontmatter(path: Path) -> dict:
    """Minimal `key: value` frontmatter reader — avoids a yaml dep for four keys."""
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    out = {}
    for line in block.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


class TestAdrSetIsWellFormed:
    def test_adr_dir_and_index_exist(self):
        assert ADR_DIR.is_dir(), "docs/adr/ is missing"
        assert ADR_INDEX.is_file(), "docs/adr/README.md is missing"

    def test_there_are_adrs(self):
        assert _adr_files(), "no ADRs found — this guard has gone vacuous"

    @pytest.mark.parametrize("path", _adr_files(), ids=lambda p: p.stem)
    def test_filename_is_numbered_slug(self, path):
        assert ADR_FILE.match(path.name), (
            f"{path.name}: ADR filenames must be NNNN-kebab-slug.md"
        )

    def test_numbering_is_sequential_and_unique(self):
        nums = [int(ADR_FILE.match(p.name).group(1)) for p in _adr_files()]
        assert nums == sorted(nums), "ADR numbers must be in order"
        assert len(nums) == len(set(nums)), f"duplicate ADR numbers: {nums}"
        assert nums == list(range(1, len(nums) + 1)), (
            f"ADR numbering must run 0001..{len(nums):04d} with no gaps; got {nums}"
        )

    @pytest.mark.parametrize("path", _adr_files(), ids=lambda p: p.stem)
    def test_has_title_heading(self, path):
        body = path.read_text().split("---", 2)[-1]
        assert re.search(r"^# \S", body, re.M), f"{path.name}: missing a `# Title` heading"


class TestAdrStatusLifecycle:
    @pytest.mark.parametrize("path", _adr_files(), ids=lambda p: p.stem)
    def test_status_is_present_and_valid(self, path):
        fm = _adr_frontmatter(path)
        status = fm.get("status")
        assert status in VALID_STATUSES, (
            f"{path.name}: status {status!r} must be one of {sorted(VALID_STATUSES)}"
        )

    @pytest.mark.parametrize("path", _adr_files(), ids=lambda p: p.stem)
    def test_superseded_names_an_existing_successor(self, path):
        fm = _adr_frontmatter(path)
        if fm.get("status") != "superseded":
            pytest.skip("not superseded")
        target = fm.get("superseded-by")
        assert target, f"{path.name}: status is superseded but no `superseded-by:` given"
        assert list(ADR_DIR.glob(f"{target}-*.md")), (
            f"{path.name}: superseded-by {target!r} names no existing ADR"
        )


class TestAdrIndexMatchesDisk:
    def test_index_lists_every_adr(self):
        listed = set(re.findall(r"\((\d{4})-[a-z0-9-]+\.md\)", ADR_INDEX.read_text()))
        on_disk = {ADR_FILE.match(p.name).group(1) for p in _adr_files()}
        assert on_disk, "no ADRs on disk — guard has gone vacuous"
        assert listed == on_disk, (
            f"docs/adr/README.md is out of sync. Listed but absent: "
            f"{sorted(listed - on_disk)}; on disk but unlisted: {sorted(on_disk - listed)}"
        )

    def test_index_status_column_matches_frontmatter(self):
        """Compare the status CELL, not the whole row.

        This previously asked `status not in row`, which is satisfied by the status
        word appearing anywhere — including inside the decision title. An ADR called
        e.g. "Treat a deprecated rung as ..." would then mask a wrong status column,
        which is the one thing this check exists to catch.
        """
        text = ADR_INDEX.read_text()
        mismatched = []
        for path in _adr_files():
            num = ADR_FILE.match(path.name).group(1)
            status = _adr_frontmatter(path).get("status")
            row = next((ln for ln in text.splitlines() if f"({num}-" in ln), None)
            if row is None:
                mismatched.append(f"{num}: no index row")
                continue
            # `| [NNNN](...) | Title | status |` — cells between the outer pipes.
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) < 3:
                mismatched.append(f"{num}: index row has {len(cells)} cells, expected 3")
                continue
            if cells[-1] != status:
                mismatched.append(
                    f"{num}: index says {cells[-1]!r}, frontmatter says {status!r}"
                )
        assert not mismatched, (
            f"docs/adr/README.md status column disagrees with frontmatter: {mismatched}"
        )


class TestArchitectureLinksTheAdrs:
    def test_architecture_points_at_the_adr_index(self):
        assert "adr/README.md" in ARCHITECTURE.read_text(), (
            "architecture.md must link the ADR index — it is the entry point readers reach first"
        )


# --------------------------------------------------------------------------- #
# The plugin README
#
# This is the first page anyone reads, and it had drifted furthest: it claimed five
# commands while seven exist, documented the dispatch axis as positional arguments
# after it became flags, omitted `smart-routing` from both enums, and carried a
# worked example (`/relay:implement acpx hybrid specs/x.md`) that a user copying it
# would have had silently parsed as task text.
# --------------------------------------------------------------------------- #

PLUGIN_README = PLUGIN_ROOT / "README.md"
COMMANDS_DIR = PLUGIN_ROOT / "commands"

NUMBER_WORDS = {
    5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


class TestPluginReadmeMatchesTree:
    def _command_slugs(self):
        return sorted(p.stem for p in COMMANDS_DIR.glob("*.md"))

    def test_command_count_word_is_current(self):
        slugs = self._command_slugs()
        word = NUMBER_WORDS.get(len(slugs))
        assert word, f"add {len(slugs)} to NUMBER_WORDS"
        text = PLUGIN_README.read_text()
        assert f"Relay exposes {word} commands" in text, (
            f"README.md must say 'Relay exposes {word} commands' — {len(slugs)} exist: {slugs}"
        )

    def test_every_command_is_listed(self):
        text = PLUGIN_README.read_text()
        missing = [s for s in self._command_slugs() if f"/relay:{s}" not in text]
        assert not missing, f"README.md does not mention commands: {missing}"

    def test_axis_documented_as_flags_not_positionals(self):
        """The workflow commands take --engine/--agent; only setup is positional."""
        text = PLUGIN_README.read_text()
        assert "| `--engine` |" in text and "| `--agent` |" in text, (
            "README.md argument table must document --engine/--agent as flags"
        )
        assert "| `engine` | `in-session`, `acpx` |" not in text, (
            "README.md still carries the pre-4.11 positional argument table"
        )

    def test_axis_values_match_the_parser(self):
        src = (PLUGIN_ROOT / "scripts" / "parse-engine-agent.sh").read_text()
        engine = re.search(r"case \"\$_relay_engine\" in ([^)]+)\)", src)
        agent = re.search(r"case \"\$_relay_agent\" in ([^)]+)\)", src)
        assert engine and agent, "could not read axis enums from parse-engine-agent.sh"
        values = [v.strip() for v in engine.group(1).split("|")]
        values += [v.strip() for v in agent.group(1).split("|")]
        text = PLUGIN_README.read_text()
        missing = sorted({v for v in values if f"`{v}`" not in text})
        assert not missing, f"README.md omits accepted axis values: {missing}"

    def test_no_positional_spec_path_example(self):
        """`allows_spec_path` is False for every command; the example would mislead."""
        text = PLUGIN_README.read_text()
        assert "acpx hybrid specs/" not in text, (
            "README.md carries a positional spec-path example, but no command accepts "
            "a third positional — it would be parsed as task text"
        )

    def test_superpowers_closed_set_count_is_current(self):
        manifest = (PLUGIN_ROOT / "scripts" / "upstream-superpowers-skills.txt").read_text()
        rows = [
            ln for ln in manifest.splitlines()
            if ln.strip() and not ln.startswith("#") and "obra/superpowers" in ln
        ]
        assert rows, "no obra/superpowers rows parsed — guard has gone vacuous"
        text = PLUGIN_README.read_text()
        assert f"{len(rows)} `obra/superpowers` rows" in text, (
            f"README.md must state the closed upstream set size ({len(rows)})"
        )
