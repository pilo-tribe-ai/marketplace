"""End-to-end acceptance gate: scaffold into a real git repo, run
regen_indexes.py, then all four gates -- on a zero-page bundle. This is
invariant 5 from the design: the acceptance test for the whole plugin.

Parametrized over two container depths ('docs/wiki/' and 'wiki/') because
the 1-deep case is what proves the vendored conftest.py's walk-up-to-'.git'
fix; before that fix it silently read a CLAUDE.md outside the target repo.
"""
import pytest

from conftest import SCAFFOLD_MODULE, init_git_repo, run_python, run_scaffold

CONTAINERS = ["docs/wiki/", "wiki/"]


def _all_files(repo) -> set:
    return {
        p.relative_to(repo).as_posix()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


@pytest.fixture(params=CONTAINERS, ids=["docs-wiki", "wiki-root"])
def scaffolded(request, tmp_path):
    container = request.param
    repo = init_git_repo(tmp_path / "repo")
    result = run_scaffold(repo, container)
    assert result.returncode == 0, result.stdout + result.stderr
    regen = run_python(repo, f"{container}scripts/regen_indexes.py")
    assert regen.returncode == 0, regen.stdout + regen.stderr
    return repo, container


def test_scaffold_writes_exactly_the_full_manifest(scaffolded):
    repo, container = scaffolded
    expected = {container + rel for rel in SCAFFOLD_MODULE.container_manifest()}
    expected |= {".claude/wiki.json", "CLAUDE.md"}
    actual = _all_files(repo)
    assert actual == expected, (
        f"missing: {sorted(expected - actual)}; unexpected: {sorted(actual - expected)}"
    )


def test_five_type_directories_exist(scaffolded):
    repo, container = scaffolded
    for name in SCAFFOLD_MODULE.TYPE_DIRS:
        assert (repo / container / "bundle" / name).is_dir()


def test_claude_md_holds_agents_md_link(scaffolded):
    repo, container = scaffolded
    text = (repo / "CLAUDE.md").read_text()
    assert f"[AGENTS.md](./{container}AGENTS.md)" in text


def test_no_unrendered_token_survives(scaffolded):
    repo, container = scaffolded
    offenders = []
    for rel in _all_files(repo):
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        if "{{" in text:
            offenders.append(rel)
    assert not offenders, f"unrendered '{{{{...}}}}' token in: {offenders}"


def test_verbatim_files_are_byte_identical_to_their_template(scaffolded):
    repo, container = scaffolded
    for rel in SCAFFOLD_MODULE.VERBATIM_FILES:
        template_bytes = (SCAFFOLD_MODULE.VERBATIM / rel).read_bytes()
        target_bytes = (repo / container / rel).read_bytes()
        assert template_bytes == target_bytes, f"{rel} drifted from its template"


def test_gate_1_check_okf_strict(scaffolded):
    repo, container = scaffolded
    result = run_python(repo, f"{container}scripts/check_okf.py", "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors, 0 warnings" in result.stdout


def test_gate_2_check_links_strict(scaffolded):
    repo, container = scaffolded
    result = run_python(repo, f"{container}scripts/check_links.py", "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 errors, 0 warnings" in result.stdout


def test_gate_3_regen_indexes_check(scaffolded):
    repo, container = scaffolded
    result = run_python(repo, f"{container}scripts/regen_indexes.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 of 5 generated files are out of date" in result.stdout


def test_gate_4_pytest_is_clean(scaffolded):
    repo, container = scaffolded
    result = run_python(
        repo, "-m", "pytest", "-q", "-rs", f"{container}tests", "-p", "no:cacheprovider",
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "failed" not in combined.lower(), combined
    assert "error" not in combined.lower(), combined


def test_second_scaffold_run_refuses_and_modifies_nothing(scaffolded):
    repo, container = scaffolded
    before = {rel: (repo / rel).stat().st_mtime_ns for rel in _all_files(repo)}
    result = run_scaffold(repo, container)
    assert result.returncode == 1, result.stdout + result.stderr
    after = {rel: (repo / rel).stat().st_mtime_ns for rel in _all_files(repo)}
    assert before == after, "a refused second run must not touch any file"


def test_pre_existing_claude_md_is_kept_and_appended_exactly_once(tmp_path):
    repo = init_git_repo(tmp_path / "repo")
    (repo / "CLAUDE.md").write_text("# My repo\n\nHand-written notes.\n")
    result = run_scaffold(repo, "docs/wiki/")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (repo / "CLAUDE.md").read_text()
    assert "# My repo" in text
    assert "Hand-written notes." in text
    assert text.count("[AGENTS.md](./docs/wiki/AGENTS.md)") == 1

    # A second full scaffold run refuses at the container-file check before
    # it would ever reach the CLAUDE.md append step again.
    result2 = run_scaffold(repo, "docs/wiki/")
    assert result2.returncode == 1
    assert (repo / "CLAUDE.md").read_text() == text
