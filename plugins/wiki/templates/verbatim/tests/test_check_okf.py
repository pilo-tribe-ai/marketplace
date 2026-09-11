"""Tests for scripts/check_okf.py, the OKF v0.2 conformance checker."""
import json
from pathlib import Path

import pytest

from conftest import CHECKER, run_checker


@pytest.fixture
def valid_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "wiki"
    (bundle / "concepts").mkdir(parents=True)
    (bundle / "index.md").write_text(
        '---\nokf_version: "0.2"\n---\n\n# Wiki Index\n\n'
        "* [Concepts](concepts/) - metrics and formulas.\n"
    )
    (bundle / "log.md").write_text(
        "# Wiki Update Log\n\n## 2026-08-04\n"
        "* **Initialization**: Established the wiki bundle structure.\n"
    )
    (bundle / "concepts" / "index.md").write_text("# Concepts\n")
    (bundle / "concepts" / "sample-concept.md").write_text(
        "---\n"
        "type: Concept\n"
        "title: Sample Concept\n"
        "description: A test concept.\n"
        "sources:\n"
        "  - id: test-source\n"
        "    resource: /sources/test-source.md\n"
        'generated: { by: "claude-code/sonnet-5", at: "2026-08-04T18:00:00Z" }\n'
        "status: stable\n"
        "---\n\n# Sample Concept\n\nA claim.[^test-source]\n\n"
        "[^test-source]: Test Source\n"
    )
    return bundle


def test_checker_script_exists():
    assert CHECKER.is_file(), "scripts/check_okf.py must exist"


def test_valid_bundle_exits_zero(valid_bundle):
    result = run_checker(valid_bundle)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors" in result.stdout


@pytest.mark.parametrize(
    "path, content, rule",
    [
        (
            "concepts/no-frontmatter.md",
            "# No frontmatter\n\nJust text.\n",
            "missing-frontmatter",
        ),
        (
            "concepts/no-type.md",
            "---\ntitle: No Type\ndescription: test\n---\n\n# No Type\n",
            "missing-type",
        ),
        (
            "concepts/index.md",
            "no heading here\n",
            "index-no-headings",
        ),
        (
            "log.md",
            "# Wiki Update Log\n\n## not-a-date\n* entry\n",
            "log-bad-date-heading",
        ),
        (
            "log.md",
            "# Wiki Update Log\n\n## 2026-01-01\n* old\n\n## 2026-08-04\n* new\n",
            "log-not-newest-first",
        ),
        (
            "log.md",
            '---\nokf_version: "0.2"\n---\n\n# Wiki Update Log\n\n## 2026-08-04\n* entry\n',
            "log-has-frontmatter",
        ),
        (
            "concepts/index.md",
            '---\nokf_version: "0.2"\n---\n\n# Concepts\n',
            "index-frontmatter-not-root",
        ),
        (
            "index.md",
            '---\nokf_version: "0.2"\nextra_key: not-allowed\n---\n\n# Wiki Index\n\n'
            "* [Concepts](concepts/) - metrics and formulas.\n",
            "index-frontmatter-extra-keys",
        ),
        (
            "concepts/sample-concept.md",
            "---\ntype: [unclosed\n---\n\n# Sample Concept\n",
            "unparseable-frontmatter",
        ),
        (
            "concepts/sample-concept.md",
            "---\n- just\n- a\n- list\n---\n\n# Sample Concept\n",
            "frontmatter-not-a-mapping",
        ),
    ],
)
def test_rule_triggers(valid_bundle, path, content, rule):
    (valid_bundle / path).write_text(content)
    result = run_checker(valid_bundle)
    assert result.returncode == 1
    assert rule in result.stdout


def test_json_format_reports_counts(valid_bundle):
    (valid_bundle / "concepts" / "no-type.md").write_text(
        "---\ntitle: No Type\n---\n\n# No Type\n"
    )
    result = run_checker(valid_bundle, "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["errors"] == 1
    assert any(i["rule"] == "missing-type" for i in payload["issues"])


def test_missing_bundle_dir_exits_two(tmp_path):
    result = run_checker(tmp_path / "does-not-exist")
    assert result.returncode == 2


def test_strict_promotes_warnings_to_errors(valid_bundle):
    (valid_bundle / "concepts" / "orphan-source.md").write_text(
        "---\ntype: Source\ntitle: Orphan\ndescription: test\n"
        'generated: { by: "claude-code/sonnet-5", at: "2026-08-04T18:00:00Z" }\n'
        "status: stable\n---\n\n# Orphan\n"
    )
    lenient = run_checker(valid_bundle)
    strict = run_checker(valid_bundle, "--strict")
    assert lenient.returncode == 0
    assert strict.returncode == 1
