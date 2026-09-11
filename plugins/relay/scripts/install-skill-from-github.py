#!/usr/bin/env python3
"""Install a single skill subdirectory from a (public) GitHub repo into the codex skills dir.

CLI (POSITIONAL — relay ships its own copy):
    install-skill-from-github.py <repo> <subpath> [--dest ~/.codex/skills] [--ref main]

  <repo>     "owner/name" or a full https git URL or a local filesystem path.
  <subpath>  path of the skill dir inside the repo, e.g. "skills/engineering".
  --dest     target skills root (default ~/.codex/skills); the skill lands at <dest>/<basename(subpath)>.
  --ref      branch or tag to fetch (default: the repo default branch).

Runtime deps: python3 + git on PATH + network egress. Public repos only (no auth).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def _clone_url(repo):
    if repo.startswith(("http://", "https://", "git@")):
        return repo
    # Local filesystem path (absolute or relative starting with ./ or /)
    if repo.startswith(("/", "./", "../")) or os.path.isdir(repo):
        return repo
    return f"https://github.com/{repo}.git"


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="install-skill-from-github.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("repo", help="owner/name or full https git URL")
    p.add_argument("subpath", help="skill dir inside the repo, e.g. skills/engineering")
    p.add_argument("--dest", default=os.path.expanduser("~/.codex/skills"),
                   help="target skills root (default ~/.codex/skills)")
    p.add_argument("--ref", default=None, help="branch or tag (default: repo default branch)")
    args = p.parse_args(argv)

    if shutil.which("git") is None:
        print("[install-skill] ERROR: git not found on PATH", file=sys.stderr)
        return 2

    name = os.path.basename(args.subpath.rstrip("/"))
    dest_skill = os.path.join(os.path.expanduser(args.dest), name)

    with tempfile.TemporaryDirectory() as tmp:
        clone = os.path.join(tmp, "repo")
        cmd = ["git", "clone", "--depth", "1"]
        if args.ref:
            cmd += ["--branch", args.ref]
        cmd += [_clone_url(args.repo), clone]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[install-skill] ERROR: git clone failed: {r.stderr.strip()}", file=sys.stderr)
            return 1

        src_skill = os.path.join(clone, args.subpath)
        # Defense-in-depth: a subpath must not escape the cloned repo (path traversal).
        _real_clone = os.path.realpath(clone)
        _real_src = os.path.realpath(src_skill)
        if _real_src != _real_clone and not _real_src.startswith(_real_clone + os.sep):
            print(f"error: subpath escapes the repository: {args.subpath}", file=sys.stderr)
            return 1
        if not os.path.isdir(src_skill):
            print(f"[install-skill] ERROR: {args.subpath} not found in {args.repo}", file=sys.stderr)
            return 1

        # Defense-in-depth: reject any symlink in the skill tree that escapes the
        # clone (an absolute/relative link to a host file would otherwise be planted
        # in the install dir and resolve to host content when the skill is read).
        for _root, _dirs, _files in os.walk(src_skill):
            for _entry in _dirs + _files:
                _full = os.path.join(_root, _entry)
                if os.path.islink(_full):
                    _target = os.path.realpath(_full)
                    if _target != _real_clone and not _target.startswith(_real_clone + os.sep):
                        rel = os.path.relpath(_full, src_skill)
                        print(f"error: skill contains a symlink escaping the repository: {rel}",
                              file=sys.stderr)
                        return 1

        os.makedirs(os.path.dirname(dest_skill), exist_ok=True)
        if os.path.exists(dest_skill):
            shutil.rmtree(dest_skill)
        shutil.copytree(src_skill, dest_skill, symlinks=True, ignore=shutil.ignore_patterns(".git"))

    print(f"[install-skill] installed {name} -> {dest_skill}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
