"""Static checks over the template tree and the plugin manifest -- no
scaffolding, no subprocess. See test_scaffold.py for the end-to-end gate."""
import json
import re

import yaml as _yaml

import adr_plugin_conftest as _cf

load_vendored = _cf.load_vendored

adr_lib = load_vendored("adr_lib")
adr_new = load_vendored("adr_new")
adr_index = load_vendored("adr_index")

TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
SCAFFOLD_TOKENS = {"DIR", "REGISTER", "TODAY"}
AUTHOR_TOKENS = {"TITLE", "DATE", "STATUS", "AREA", "PREFIX"}


def blocks(plugin_root):
    return {name: (plugin_root / "templates" / f"{name}.md").read_text(encoding="utf-8")
            for name in ("claude-md-root-block", "claude-md-corpus")}


def test_plugin_json_has_expected_fields(plugin_json):
    expected = {"name", "displayName", "version", "description", "author",
                "homepage", "repository", "license", "keywords"}
    assert set(plugin_json.keys()) == expected
    assert plugin_json["name"] == "adr"
    assert plugin_json["version"] == "0.1.0"
    assert plugin_json["license"] == "MIT"
    assert set(plugin_json["author"].keys()) == {"name", "email"}
    assert isinstance(plugin_json["keywords"], list) and plugin_json["keywords"]


def test_the_plugin_is_listed_in_the_marketplace(plugin_root):
    marketplace = json.loads(
        (plugin_root.parent.parent / ".claude-plugin" / "marketplace.json")
        .read_text(encoding="utf-8"))
    names = [entry["name"] for entry in marketplace["plugins"]]
    assert "adr" in names
    assert marketplace["metadata"]["version"] == "1.8.0"


def test_both_blocks_carry_the_reversibility_bar(plugin_root):
    for name, text in blocks(plugin_root).items():
        assert "expensive to undo" in text, f"{name} does not state the bar"


def test_both_blocks_carry_the_proposed_instruction(plugin_root):
    for name, text in blocks(plugin_root).items():
        assert "status: proposed" in text, f"{name} does not say to write `proposed`"
        assert "Do not stop to ask" in text, f"{name} does not say to keep working"


def test_both_blocks_carry_the_register_first_instruction(plugin_root):
    root, corpus = blocks(plugin_root).values()
    assert "{{REGISTER}}" in root and "before you change an architectural boundary" in root.lower()
    assert "README.md" in corpus and "Open only the ADRs that apply" in corpus


def test_the_corpus_block_forbids_hand_editing_between_the_markers(plugin_root):
    corpus = blocks(plugin_root)["claude-md-corpus"]
    assert "Do not edit `README.md` between the generated markers" in corpus


def test_only_known_tokens_appear_in_the_scaffolded_templates(plugin_root):
    for name in ("claude-md-root-block", "claude-md-corpus", "register-seed"):
        path = plugin_root / "templates" / f"{name}.md"
        assert not set(TOKEN_RE.findall(path.read_text("utf-8"))) - SCAFFOLD_TOKENS


def test_the_adr_template_matches_what_adr_new_writes(plugin_root):
    """A template that drifts from the writer teaches a shape no script
    accepts."""
    text = (plugin_root / "templates" / "adr-template.md").read_text(encoding="utf-8")
    front, body = adr_lib.split_frontmatter(text)
    assert front is not None
    keys = [line.split(":")[0] for line in front.splitlines() if not line.startswith(" ")]
    assert keys == list(adr_lib.KEY_ORDER)
    assert "id:" not in front
    for heading in adr_new.BODY_HEADINGS:
        assert heading in body


def test_the_adr_template_uses_only_author_tokens(plugin_root):
    text = (plugin_root / "templates" / "adr-template.md").read_text(encoding="utf-8")
    assert set(TOKEN_RE.findall(text)) <= AUTHOR_TOKENS


def test_the_register_seed_markers_match_the_generator(plugin_root):
    text = (plugin_root / "templates" / "register-seed.md").read_text(encoding="utf-8")
    assert adr_index.BEGIN_RE.search(text) and adr_index.END_RE.search(text)
    assert adr_index.block_of(text) is not None


def test_the_readme_names_the_commands_this_node_ships(plugin_root):
    text = (plugin_root / "README.md").read_text(encoding="utf-8")
    assert "/adr:setup" in text
    assert "expensive to undo" in text                      # the bar
    assert "python3 -m pytest plugins/adr/tests" in text     # plugin-side suite
    assert "templates/verbatim/tests" in text                # vendored suite
    assert "separately" in text or "two commands" in text


def test_the_changelog_records_the_manifest_version(plugin_root, plugin_json):
    text = (plugin_root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert plugin_json["version"] in text


# --- Task 40: the optional CI gate -------------------------------------------

def gate(plugin_root):
    return _yaml.safe_load(
        (plugin_root / "templates" / "gate" / "adr-gate.yml").read_text("utf-8"))


def test_the_gate_runs_the_deterministic_tier_with_no_install_step(plugin_root):
    text = (plugin_root / "templates" / "gate" / "adr-gate.yml").read_text("utf-8")
    assert "python3 scripts/adr/adr_lint.py" in text
    assert "python3 scripts/adr/adr_index.py --check" in text
    assert "pip install" not in text          # no install step, by design
    assert "pytest" not in text               # the vendored suite is a manual command


def test_the_gate_scopes_the_proposed_check_to_the_changed_files(plugin_root):
    """Run against the whole corpus it would fail every PR that captures a new
    decision, because capture always writes status: proposed."""
    text = (plugin_root / "templates" / "gate" / "adr-gate.yml").read_text("utf-8")
    assert "--changed" in text
    assert "git diff --name-only" in text and "base_ref" in text


def test_the_model_job_is_guarded_by_the_key_and_never_fails_the_check(plugin_root):
    data = gate(plugin_root)
    model = data["jobs"]["model"]
    assert "ANTHROPIC_API_KEY" in _yaml.dump(model)
    assert model.get("continue-on-error") is True
    assert "/adr:check" in _yaml.dump(model)


def test_the_gate_actually_triggers_on_pull_request(plugin_root):
    """A workflow with no `on:` key never runs -- YAML's bare `on` key parses
    as the boolean True under `yaml.safe_load`, so this reads `data[True]`
    rather than `data["on"]`. [inferred]"""
    data = gate(plugin_root)
    assert "pull_request" in data[True]  # [inferred]
