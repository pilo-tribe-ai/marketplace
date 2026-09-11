import subprocess
from pathlib import Path

from conftest import PLUGIN_ROOT

SCRIPT = PLUGIN_ROOT / "scripts" / "install-skill-from-github.py"


def _run(args, **kw):
    return subprocess.run(["python3", str(SCRIPT), *args],
                          capture_output=True, text=True, **kw)


class TestInstallSkillCLI:
    def test_exists(self):
        assert SCRIPT.is_file()

    def test_positional_cli_shape(self):
        # --help documents POSITIONAL <repo> <subpath>, not --repo/--path flags
        r = _run(["--help"])
        assert r.returncode == 0
        assert "repo" in r.stdout and "subpath" in r.stdout
        assert "--dest" in r.stdout
        assert "--repo" not in r.stdout and "--path" not in r.stdout

    def test_missing_positionals_errors(self):
        r = _run([])
        assert r.returncode != 0  # argparse usage error

    def test_installs_from_local_git_repo(self, tmp_path):
        # build a throwaway local git repo with a skills/<name> subdir to avoid network
        import shutil
        if shutil.which("git") is None:
            import pytest
            pytest.skip("git unavailable")
        src = tmp_path / "src"
        skill_dir = src / "skills" / "engineering"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: engineering\n---\nbody\n")
        (skill_dir / "helper.md").write_text("helper\n")
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "init"]):
            assert subprocess.run(cmd, cwd=src).returncode == 0
        dest = tmp_path / "codex-skills"
        r = _run([str(src), "skills/engineering", "--dest", str(dest)])
        assert r.returncode == 0, r.stderr
        assert (dest / "engineering" / "SKILL.md").is_file()
        assert (dest / "engineering" / "helper.md").is_file()

    def test_rejects_traversal_subpath(self, tmp_path):
        import shutil
        if shutil.which("git") is None:
            import pytest
            pytest.skip("git unavailable")
        src_repo = tmp_path / "src"
        skill_dir = src_repo / "skills" / "x"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: x\n---\nbody\n")
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "init"]):
            assert subprocess.run(cmd, cwd=src_repo).returncode == 0
        dest = tmp_path / "dest"
        r = _run([str(src_repo), "../../../../etc", "--dest", str(dest)])
        assert r.returncode != 0, "traversal subpath must be rejected"
        assert not (dest / "etc").exists(), "must not copy host files outside the clone"

    def test_rejects_escaping_symlink(self, tmp_path):
        """A skill containing a symlink that resolves outside the clone must be rejected.

        The install script must detect and block any symlink whose realpath escapes the
        cloned repository root — planting such a link in ~/.codex/skills/ would cause the
        host file to be readable at read time, bypassing the path-traversal guard.
        """
        import shutil as _shutil
        if _shutil.which("git") is None:
            import pytest
            pytest.skip("git unavailable")

        # Host file with known content that the skill tree symlink will point at.
        host_secret = tmp_path / "host_secret.txt"
        host_secret.write_text("HOST_SECRET_CONTENT")

        src_repo = tmp_path / "src"
        skill_dir = src_repo / "skills" / "myskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: myskill\n---\nbody\n")
        # Create a symlink inside the skill that points at the host file (outside clone).
        (skill_dir / "link.txt").symlink_to(host_secret)

        for cmd in (["git", "init", "-q"],
                    ["git", "-c", "core.symlinks=true", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "init"]):
            subprocess.run(cmd, cwd=src_repo)

        dest = tmp_path / "codex-skills"
        r = _run([str(src_repo), "skills/myskill", "--dest", str(dest)])
        # install must be rejected (non-zero exit)
        assert r.returncode != 0, "escaping symlink must cause install to be rejected"
        # the escaping link must NOT be planted in the destination
        assert not (dest / "myskill" / "link.txt").exists(), \
            "escaping symlink must not be planted in destination"
        assert not (dest / "myskill" / "link.txt").is_symlink(), \
            "escaping symlink must not be planted in destination"

    def test_preserves_internal_relative_symlink(self, tmp_path):
        """Internal relative symlinks that stay inside the clone must be installed as-is.

        The symlink escape guard must not over-reject benign internal links.
        """
        import shutil as _shutil
        if _shutil.which("git") is None:
            import pytest
            pytest.skip("git unavailable")

        src_repo = tmp_path / "src"
        skill_dir = src_repo / "skills" / "myskill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: myskill\n---\nbody\n")
        # Relative symlink pointing at a sibling inside the same skill dir.
        (skill_dir / "alias.md").symlink_to("SKILL.md")

        for cmd in (["git", "init", "-q"],
                    ["git", "-c", "core.symlinks=true", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "init"]):
            subprocess.run(cmd, cwd=src_repo)

        dest = tmp_path / "codex-skills"
        r = _run([str(src_repo), "skills/myskill", "--dest", str(dest)])
        assert r.returncode == 0, f"internal relative symlink must not be rejected: {r.stderr}"
        # The installed alias must still be a symlink (not dereferenced to a plain file).
        assert (dest / "myskill" / "alias.md").is_symlink(), \
            "internal symlink must be preserved as a symlink after install"
