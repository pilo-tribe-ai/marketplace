# Changelog

All notable changes to github are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## 3.0.1 — 2026-08-22

### Fixed

- **`/github:issue:create` no longer points at a deleted command.** It told the user to
  run `/git:worktree:create`. The git plugin 3.0.0 dropped every worktree operation, so
  the three references now show the plain `git worktree add` command instead.
