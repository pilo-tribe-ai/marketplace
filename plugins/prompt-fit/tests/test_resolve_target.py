"""Target resolution. The file list it prints is the whole scope of a review."""

import shutil
import subprocess

import pytest


def make_plugin(root):
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (root / "commands").mkdir()
    (root / "commands" / "go.md").write_text("Run it.\n", encoding="utf-8")
    (root / "agents").mkdir()
    (root / "agents" / "worker.md").write_text("Work.\n", encoding="utf-8")
    (root / "skills" / "doing").mkdir(parents=True)
    (root / "skills" / "doing" / "SKILL.md").write_text("Do it.\n", encoding="utf-8")
    (root / "README.md").write_text("docs\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text("docs\n", encoding="utf-8")
    return root


def paths_of(result):
    return [item["path"] for item in result["files"]]


def roles_of(result):
    return {item["role"] for item in result["files"]}


def test_a_single_file_resolves_to_itself(resolver, tmp_path):
    path = tmp_path / "draft.md"
    path.write_text("Run it.\n", encoding="utf-8")
    result = resolver.resolve(str(path))
    assert result["kind"] == "file"
    assert result["count"] == 1


def test_a_plugin_resolves_its_commands_agents_and_skills(resolver, tmp_path):
    root = make_plugin(tmp_path / "myplugin")
    result = resolver.resolve(str(root))
    assert result["kind"] == "plugin"
    assert roles_of(result) == {"command", "agent", "skill"}
    assert result["count"] == 3


def test_a_plugin_skips_its_readme_and_changelog(resolver, tmp_path):
    root = make_plugin(tmp_path / "myplugin")
    names = [p.rsplit("/", 1)[-1] for p in paths_of(resolver.resolve(str(root)))]
    assert "README.md" not in names
    assert "CHANGELOG.md" not in names


def test_a_skill_folder_resolves_its_skill_and_its_reference(resolver, tmp_path):
    root = tmp_path / "doing"
    root.mkdir()
    (root / "SKILL.md").write_text("Do it.\n", encoding="utf-8")
    (root / "reference").mkdir()
    (root / "reference" / "corpus.md").write_text("Material.\n", encoding="utf-8")
    result = resolver.resolve(str(root))
    assert result["kind"] == "skill"
    assert result["count"] == 2
    assert roles_of(result) == {"skill", "skill-reference"}


def test_a_project_resolves_its_memory_and_its_claude_tree(resolver, tmp_path):
    root = tmp_path / "project"
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("Rules.\n", encoding="utf-8")
    (root / ".claude" / "commands" / "go.md").write_text("Run it.\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "notes.md").write_text("Not a prompt.\n", encoding="utf-8")
    result = resolver.resolve(str(root))
    assert result["kind"] == "project"
    assert roles_of(result) == {"memory", "command"}
    assert result["count"] == 2, "src/notes.md is outside the prompt tree"


def test_a_plain_folder_resolves_every_markdown_file(resolver, tmp_path):
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "one.md").write_text("Run it.\n", encoding="utf-8")
    (root / "two.txt").write_text("Run it.\n", encoding="utf-8")
    result = resolver.resolve(str(root))
    assert result["kind"] == "directory"
    assert result["count"] == 2


def test_a_missing_path_raises(resolver, tmp_path):
    with pytest.raises(resolver.ResolveError, match="does not exist"):
        resolver.resolve(str(tmp_path / "gone"))


def test_a_folder_with_no_prompt_file_raises(resolver, tmp_path):
    """A run that reviews nothing must never report success."""
    root = tmp_path / "empty"
    root.mkdir()
    (root / "script.py").write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(resolver.ResolveError, match="no prompt file"):
        resolver.resolve(str(root))


def test_a_folder_over_the_cap_raises_rather_than_truncating(resolver, tmp_path):
    root = tmp_path / "many"
    root.mkdir()
    for n in range(resolver.FILE_CAP + 1):
        (root / f"file{n:03d}.md").write_text("Run it.\n", encoding="utf-8")
    with pytest.raises(resolver.ResolveError, match="over the cap"):
        resolver.resolve(str(root))


def test_a_folder_at_the_cap_resolves(resolver, tmp_path):
    root = tmp_path / "many"
    root.mkdir()
    for n in range(resolver.FILE_CAP):
        (root / f"file{n:03d}.md").write_text("Run it.\n", encoding="utf-8")
    assert resolver.resolve(str(root))["count"] == resolver.FILE_CAP


def test_a_requirements_file_is_not_a_prompt(resolver, tmp_path):
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "requirements.txt").write_text("pytest==8.0\n", encoding="utf-8")
    (root / "real.md").write_text("Run it.\n", encoding="utf-8")
    assert resolver.resolve(str(root))["count"] == 1


def test_skipped_folders_are_not_walked(resolver, tmp_path):
    root = tmp_path / "prompts"
    (root / "node_modules").mkdir(parents=True)
    (root / "node_modules" / "junk.md").write_text("Run it.\n", encoding="utf-8")
    (root / "real.md").write_text("Run it.\n", encoding="utf-8")
    assert resolver.resolve(str(root))["count"] == 1


def test_the_exit_code_is_two_on_a_missing_path(resolver, tmp_path, capsys):
    assert resolver.main([str(tmp_path / "gone")]) == 2


def test_the_exit_code_is_zero_on_a_resolved_target(resolver, tmp_path):
    path = tmp_path / "draft.md"
    path.write_text("Run it.\n", encoding="utf-8")
    assert resolver.main([str(path)]) == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_state_separates_clean_dirty_and_untracked(resolver, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run = lambda *args: subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    )
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "test")
    (root / "clean.md").write_text("Run it.\n", encoding="utf-8")
    (root / "dirty.md").write_text("Run it.\n", encoding="utf-8")
    run("add", ".")
    run("commit", "-qm", "first")
    (root / "dirty.md").write_text("Run it twice.\n", encoding="utf-8")
    (root / "new.md").write_text("Run it.\n", encoding="utf-8")

    states = {
        item["path"].rsplit("/", 1)[-1]: item["git"]
        for item in resolver.resolve(str(root))["files"]
    }
    assert states["clean.md"] == "tracked-clean"
    assert states["dirty.md"] == "tracked-dirty"
    assert states["new.md"] == "untracked"
