"""Tests for scripts/regen_indexes.py, the index generator.

Indexes and each Source page's fed-pages list are derived data: every fact in
them already lives in a page's frontmatter. Generating them removes the class
of drift where a page is added but an index is not updated.
"""
import subprocess
import sys

import pytest

from conftest import WIKI, WIKI_ROOT

REGEN = WIKI_ROOT / "scripts" / "regen_indexes.py"


def run_regen(bundle, *extra_args):
    return subprocess.run(
        [sys.executable, str(REGEN), "--bundle", str(bundle), *extra_args],
        capture_output=True,
        text=True,
    )


PAGE = """---
type: {type}
title: {title}
description: {description}
sources:
  - id: src
    resource: /sources/{source}.md
---

# {title}

Body.
"""


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "wiki"
    for sub in ("sources", "concepts", "entities", "synthesis", "open-questions"):
        (root / sub).mkdir(parents=True)
    (root / "index.md").write_text("---\nokf_version: \"0.2\"\n---\n\n# Wiki Index\n\n* [Concepts](concepts/)\n")
    (root / "log.md").write_text("# Wiki Update Log\n")
    (root / "sources" / "a-source.md").write_text(
        "---\ntype: Source\ntitle: A Source\ndescription: The source.\n"
        "resource: raw/a-source.md\n---\n\n# A Source\n\nIntro.\n\n## Pages this source fed\n"
    )
    (root / "concepts" / "beta.md").write_text(
        PAGE.format(type="Concept", title="Beta", description="Second concept.", source="a-source")
    )
    (root / "concepts" / "alpha.md").write_text(
        PAGE.format(type="Concept", title="Alpha", description="First concept.", source="a-source")
    )
    for sub in ("sources", "concepts", "entities", "synthesis", "open-questions"):
        (root / sub / "index.md").write_text(f"# {sub}\n\nstale\n")
    return root


def test_index_lists_every_page_sorted_with_verbatim_description(bundle):
    run_regen(bundle)
    text = (bundle / "concepts" / "index.md").read_text()
    assert "# Concepts" in text
    assert "* [Alpha](alpha.md) - First concept." in text
    assert "* [Beta](beta.md) - Second concept." in text
    assert text.index("alpha.md") < text.index("beta.md"), "pages are sorted by filename"


def test_index_never_lists_itself(bundle):
    run_regen(bundle)
    assert "](index.md)" not in (bundle / "concepts" / "index.md").read_text()


def test_empty_subdirectory_index_still_has_a_heading(bundle):
    """check_okf.py's index-no-headings rule fails an index with no heading."""
    run_regen(bundle)
    assert (bundle / "entities" / "index.md").read_text().startswith("# Entities")


def test_bundle_root_index_is_left_alone(bundle):
    """wiki/index.md is hand-written and carries okf_version frontmatter."""
    before = (bundle / "index.md").read_text()
    run_regen(bundle)
    assert (bundle / "index.md").read_text() == before


def test_source_page_fed_list_is_rebuilt_from_page_sources(bundle):
    run_regen(bundle)
    text = (bundle / "sources" / "a-source.md").read_text()
    assert "## Pages this source fed" in text
    assert "- [Alpha](../concepts/alpha.md)" in text
    assert "- [Beta](../concepts/beta.md)" in text


def test_source_page_intro_above_the_fed_heading_is_preserved(bundle):
    run_regen(bundle)
    assert "Intro." in (bundle / "sources" / "a-source.md").read_text()


def test_a_page_is_only_listed_under_the_source_that_fed_it(bundle):
    (bundle / "sources" / "b-source.md").write_text(
        "---\ntype: Source\ntitle: B Source\ndescription: Other.\n"
        "resource: raw/b-source.md\n---\n\n# B Source\n\n## Pages this source fed\n"
    )
    (bundle / "entities" / "solo.md").write_text(
        PAGE.format(type="Entity", title="Solo", description="Only from B.", source="b-source")
    )
    run_regen(bundle)
    a_text = (bundle / "sources" / "a-source.md").read_text()
    b_text = (bundle / "sources" / "b-source.md").read_text()
    assert "../entities/solo.md" in b_text
    assert "../entities/solo.md" not in a_text


def test_check_mode_reports_drift_without_writing(bundle):
    stale = (bundle / "concepts" / "index.md").read_text()
    result = run_regen(bundle, "--check")
    assert result.returncode == 1
    assert (bundle / "concepts" / "index.md").read_text() == stale, "--check must not write"


def test_check_mode_passes_once_regenerated(bundle):
    run_regen(bundle)
    assert run_regen(bundle, "--check").returncode == 0


def test_regeneration_is_idempotent(bundle):
    run_regen(bundle)
    first = (bundle / "concepts" / "index.md").read_text()
    run_regen(bundle)
    assert (bundle / "concepts" / "index.md").read_text() == first


def test_missing_bundle_is_a_usage_error(tmp_path):
    assert run_regen(tmp_path / "nope").returncode == 2


def test_real_wiki_bundle_needs_no_regeneration():
    """The committed indexes match what the generator would produce."""
    result = run_regen(WIKI, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
