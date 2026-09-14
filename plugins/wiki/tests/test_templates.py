"""Static checks over the template tree and the plugin manifest -- no
scaffolding, no subprocess. See test_scaffold_empty_bundle.py for the
end-to-end acceptance gate."""
import re

from conftest import SCAFFOLD_MODULE

# The single source of truth for these lists is scaffold.py; importing them
# here keeps this token-hygiene gate in lockstep with what the scaffolder
# actually writes, instead of a hand-copied list that could silently drift.
VERBATIM_FILES = SCAFFOLD_MODULE.VERBATIM_FILES
RENDERED_FILES = SCAFFOLD_MODULE.RENDERED_FILES
VALID_TOKENS = set(SCAFFOLD_MODULE.TOKEN_NAMES)
TOKEN_RE = re.compile(r"\{\{([A-Za-z_]+)\}\}")


def test_all_verbatim_files_exist(plugin_root):
    verbatim = plugin_root / "templates" / "verbatim"
    for rel in VERBATIM_FILES:
        assert (verbatim / rel).is_file(), f"missing verbatim template: {rel}"


def test_all_rendered_files_exist(plugin_root):
    rendered = plugin_root / "templates" / "rendered"
    for rel in RENDERED_FILES:
        assert (rendered / rel).is_file(), f"missing rendered template: {rel}"


def test_claude_md_block_exists(plugin_root):
    assert (plugin_root / "templates" / "claude-md-block.md").is_file()


def test_no_file_under_verbatim_holds_a_token(plugin_root):
    verbatim = plugin_root / "templates" / "verbatim"
    for path in verbatim.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "{{" not in text, f"{path} is verbatim but holds a '{{{{' token"


def test_every_token_under_rendered_is_one_of_the_six(plugin_root):
    rendered = plugin_root / "templates" / "rendered"
    found = set()
    for path in rendered.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            found |= set(TOKEN_RE.findall(text))
    claude_block = (plugin_root / "templates" / "claude-md-block.md").read_text(encoding="utf-8")
    found |= set(TOKEN_RE.findall(claude_block))
    unknown = found - VALID_TOKENS
    assert not unknown, f"unknown token(s) found under templates/rendered/: {unknown}"


def test_rendered_output_holds_no_non_ascii(plugin_root):
    """ASCII only applies to what ends up as bundle prose (the rendered/
    templates plus the CLAUDE.md append block) -- check_links.py --strict
    flags non-ASCII text under bundle/. templates/verbatim/ is exempt: it
    holds scripts and tests, not bundle prose, and they legitimately hold
    non-ASCII in a comment (check_links.py's own docstring) and in a test
    fixture that exists specifically to exercise the non-ASCII rule."""
    rendered = plugin_root / "templates" / "rendered"
    paths = [p for p in rendered.rglob("*") if p.is_file()]
    paths.append(plugin_root / "templates" / "claude-md-block.md")
    offenders = []
    for path in paths:
        try:
            path.read_bytes().decode("ascii")
        except UnicodeDecodeError:
            offenders.append(str(path.relative_to(plugin_root)))
    assert not offenders, f"non-ASCII byte(s) found in: {offenders}"


def test_plugin_json_has_expected_fields(plugin_json):
    expected_fields = {
        "name", "displayName", "version", "description", "author",
        "homepage", "repository", "license", "keywords",
    }
    assert set(plugin_json.keys()) == expected_fields
    assert plugin_json["name"] == "wiki"
    assert set(plugin_json["author"].keys()) == {"name", "email"}
    assert isinstance(plugin_json["keywords"], list) and plugin_json["keywords"]
