"""Tests for scripts/check_links.py, the link/orphan/encoding gate.

check_okf.py validates that a bundle is structurally conformant. It does not
validate that a link resolves. These tests cover the checks that catch the
class of breakage OKF conformance is blind to.
"""
import json
import subprocess
import sys

import pytest

from conftest import WIKI, WIKI_ROOT

CHECKER = WIKI_ROOT / "scripts" / "check_links.py"


def run_links(bundle, *extra_args):
    return subprocess.run(
        [sys.executable, str(CHECKER), "--bundle", str(bundle), *extra_args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def bundle(tmp_path):
    """A minimal conformant bundle: one concept linked from one synthesis."""
    root = tmp_path / "wiki"
    (root / "concepts").mkdir(parents=True)
    (root / "synthesis").mkdir()
    (root / "index.md").write_text("---\nokf_version: \"0.2\"\n---\n\n# Wiki Index\n\n* [Concepts](concepts/)\n")
    (root / "log.md").write_text("# Wiki Update Log\n\n## 2026-08-04\n* **Ingest**: seeded.\n")
    (root / "concepts" / "index.md").write_text("# Concepts\n\n* [Alpha](alpha.md) - a concept.\n")
    (root / "concepts" / "alpha.md").write_text(
        "---\ntype: Concept\n---\n\n# Alpha\n\nRolled up in [Sum](../synthesis/sum.md).\n"
    )
    (root / "synthesis" / "index.md").write_text("# Synthesis\n\n* [Sum](sum.md) - a synthesis.\n")
    (root / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\nSee [Alpha](../concepts/alpha.md).\n"
    )
    return root


def test_clean_bundle_passes(bundle):
    result = run_links(bundle)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors, 0 warnings" in result.stdout


def test_broken_link_is_an_error(bundle):
    (bundle / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\nSee [Ghost](../concepts/ghost.md).\n"
    )
    result = run_links(bundle)
    assert result.returncode == 1
    assert "broken-link" in result.stdout
    assert "../concepts/ghost.md" in result.stdout


def test_root_absolute_link_to_a_page_is_an_error(bundle):
    """The bundle convention is links relative to the referring file. A
    leading slash resolves against the repository root in GitHub and VS
    Code, so it 404s for a reader."""
    (bundle / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\nSee [Alpha](/concepts/alpha.md).\n"
    )
    result = run_links(bundle)
    assert result.returncode == 1
    assert "root-absolute-link" in result.stdout
    assert "/concepts/alpha.md" in result.stdout
    assert "repository root" in result.stdout


def test_a_link_that_escapes_the_bundle_is_an_error(bundle):
    (bundle / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\nSee [Raw](../../raw/x.md).\n"
    )
    result = run_links(bundle)
    assert result.returncode == 1
    assert "outside-bundle" in result.stdout


def test_same_directory_and_parent_hop_links_both_resolve(bundle):
    (bundle / "concepts" / "gamma.md").write_text(
        "---\ntype: Concept\n---\n\n# Gamma\n\n"
        "See [Alpha](alpha.md) and [Sum](../synthesis/sum.md).\n"
    )
    (bundle / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\n"
        "See [Alpha](../concepts/alpha.md) and [Gamma](../concepts/gamma.md).\n"
    )
    assert run_links(bundle, "--strict").returncode == 0


def test_orphan_page_is_a_warning_not_an_error(bundle):
    """An index listing a page does not rescue it from being an orphan --
    indexes are generated, so they link everything by construction."""
    (bundle / "concepts" / "beta.md").write_text("---\ntype: Concept\n---\n\n# Beta\n\nBody.\n")
    (bundle / "concepts" / "index.md").write_text(
        "# Concepts\n\n* [Alpha](alpha.md) - a concept.\n"
        "* [Beta](beta.md) - another.\n"
    )
    result = run_links(bundle)
    assert result.returncode == 0, "orphans are a warning, so a plain run still passes"
    assert "orphan-page" in result.stdout
    assert "'concepts/beta.md' has no inbound link" in result.stdout


def test_orphan_warning_fails_under_strict(bundle):
    (bundle / "concepts" / "beta.md").write_text("---\ntype: Concept\n---\n\n# Beta\n\nBody.\n")
    assert run_links(bundle, "--strict").returncode == 1


def test_non_ascii_character_is_a_warning(bundle):
    (bundle / "concepts" / "alpha.md").write_text(
        "---\ntype: Concept\n---\n\n# Alpha\n\nAn em dash — here.\n"
    )
    result = run_links(bundle)
    assert result.returncode == 0
    assert "non-ascii" in result.stdout


def test_external_links_are_ignored(bundle):
    (bundle / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\n"
        "See [Alpha](../concepts/alpha.md) and [ext](https://example.com/x.md).\n"
    )
    assert run_links(bundle).returncode == 0


def test_anchor_only_and_fragment_links_resolve(bundle):
    (bundle / "synthesis" / "sum.md").write_text(
        "---\ntype: Synthesis\n---\n\n# Sum\n\n"
        "See [Alpha](../concepts/alpha.md#claims) and [self](#sum).\n"
    )
    assert run_links(bundle).returncode == 0


def test_directory_links_resolve(bundle):
    assert run_links(bundle).returncode == 0, "wiki/index.md links concepts/ as a directory"


def test_json_format_reports_counts(bundle):
    result = run_links(bundle, "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["errors"] == 0
    assert payload["warnings"] == 0
    assert payload["links_checked"] > 0


def test_missing_bundle_is_a_usage_error(tmp_path):
    assert run_links(tmp_path / "nope").returncode == 2


def test_real_wiki_bundle_is_clean():
    """The gate this whole script exists to hold."""
    result = run_links(WIKI, "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
