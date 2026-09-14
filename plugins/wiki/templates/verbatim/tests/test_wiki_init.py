"""Tests for the Initialization operation: the wiki bundle skeleton."""
import re

from conftest import WIKI, WIKI_ROOT, run_checker


def test_raw_directory_exists():
    assert (WIKI_ROOT / "raw").is_dir()


def test_wiki_skeleton_directories_exist():
    for sub in ("sources", "entities", "concepts", "synthesis", "open-questions"):
        assert (WIKI / sub).is_dir(), f"bundle/{sub}/ must exist"


def test_wiki_index_declares_okf_version():
    text = (WIKI / "index.md").read_text()
    assert 'okf_version: "0.2"' in text
    assert "# Wiki Index" in text


def test_each_subdirectory_index_has_a_heading():
    expected = {
        "sources": "# Sources",
        "entities": "# Entities",
        "concepts": "# Concepts",
        "synthesis": "# Synthesis",
        "open-questions": "# Open Questions",
    }
    for sub, heading in expected.items():
        text = (WIKI / sub / "index.md").read_text()
        assert text.strip().startswith(heading)


def test_log_has_initialization_entry():
    text = (WIKI / "log.md").read_text()
    assert "# Wiki Update Log" in text
    assert re.search(r"^## \d{4}-\d{2}-\d{2}$", text, re.M), (
        "log.md must have at least one '## YYYY-MM-DD' date heading"
    )
    assert "**Initialization**" in text


def test_checker_passes_on_freshly_initialized_bundle():
    result = run_checker(WIKI)
    assert result.returncode == 0, result.stdout + result.stderr
