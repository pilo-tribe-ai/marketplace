# Changelog

All notable changes to git are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## 4.0.0 — 2026-08-22

### Fixed

- **The ownership banner now reaches the user when you resume a rebase.** The runtime
  verify found this, and the cause was the fork, not the wording. A fork returns only its
  last message. On the resume path the session printed the banner in one message and the
  resolution options in the next, so the fork threw the banner away and the user saw only
  the options. Three rounds of stronger prose ("CRITICAL", "Step 0", an output contract)
  changed nothing. Putting the banner inside the Step 4 template — the block the session
  copies when it asks the question — fixed it on the first try. The skill now states the
  fork rule where it bites: everything the user needs in order to answer must sit in the
  same message as the question.
- **The banner reads the target branch from a file that exists.** Phase 3 said to read
  `.git/rebase-merge/onto_name`. That file is absent in this git version; the directory
  holds `onto`, a raw SHA. The step now falls back to `onto` and turns it into a name with
  `git name-rev`, and it says to print the short SHA in place of guessing a branch name.
- **The recent-branch list drops `refs/remotes/origin/HEAD`.** It printed as a branch named
  `origin`, which is a pointer, not a branch you can rebase onto.

### Changed

- **BREAKING — the three rebase skills are one skill.** `/git:rebase-main` and
  `/git:rebase-continue` are gone. The argument selects the mode:

  | Before | Now |
  | --- | --- |
  | `/git:rebase-main` | `/git:rebase` |
  | `/git:rebase <branch>` | `/git:rebase <branch>` |
  | `/git:rebase-continue` | `/git:rebase --continue` |

  `/git:rebase --continue` already existed, so the continue skill was a duplicate from the
  start. The other two shared one conflict workflow, and both reached it by reading
  `skills/rebase/SKILL.md` at run time. That cross-file read is what broke in 3.0.0: a
  wrong `allowed-tools` made the read fail, and the run continued with no ownership
  banner and no error. One file has no cross-file read.

- **BREAKING — a bare `/git:rebase` now fetches and rebases onto the default branch.** It
  used to ask which branch to use. The bare run is the common case, so it is the default,
  and it needs no argument at all.

  This also closes a sharp edge. The old menu option "main/master branch" rebased onto
  `origin/main` **with no fetch**, so it could put your branch on top of a stale ref. The
  default mode always fetches first.

- **There is no `--main` argument, by choice.** `/git:rebase main` means "rebase onto the
  local branch `main`". A `--main` flag would sit two characters away from it and behave
  differently — a fetch against no fetch — on the most used path.

- **A branch name that does not resolve no longer dead-ends.** Phase 2B lists the branches
  that were used most recently and asks, in place of printing an error and stopping.

- **Phase 2B protects uncommitted work.** The named-branch mode runs the same stash,
  commit, or abort question that the default mode runs. Before this, only the default
  mode did.

## 3.0.0 — 2026-08-22

### Removed

- **BREAKING — the plugin keeps the rebase skills only.** Measured use decided this:
  across the full prompt history, `/git:rebase-main` had 34 runs and `/git:rebase` 11,
  while the four worktree operations had none and `/git:merge` had one. These files are
  gone:

  | Removed | Use instead |
  | --- | --- |
  | `/git:worktree-list` | `git worktree list` |
  | `/git:worktree-create` | `git worktree add <path> -b <branch>` |
  | `/git:worktree-delete` | `git worktree remove <path>` |
  | `/git:worktree-update` | `git fetch` and `git pull` inside the worktree |
  | `/git:merge` | `git merge`, or `/git:rebase` |
  | `git:conflict-resolver` | the conflict workflow inside `/git:rebase` |

  `git:conflict-resolver` went with `/git:merge`, its only caller. The rebase skills
  carry their own conflict workflow, so nothing they do depends on it.
- **`SKILL.md` at the plugin root is gone.** It never registered as a skill, and it
  duplicated `README.md`. `README.md` is now the only document.

### Fixed

- **`/git:rebase-continue` can read the workflow it is told to follow.** Its
  `allowed-tools` held `Bash(git *)` and `Bash(cat .git/*)` only, but its body says to
  follow Phase 3 of `skills/rebase/SKILL.md`. A live run proved the damage: the session
  reported "I don't have permission to read the referenced skill file", then resolved the
  conflict with no REBASE OWNERSHIP REFERENCE banner, no `OURS`/`THEIRS` branch names, and
  no recommendation — the whole value of the workflow, lost without an error. It also had
  no `Edit`, so it could not finish a resolution by hand. It now carries the same tools as
  `/git:rebase`, and Phase 2 says to Read the file first and to stop when that read fails,
  in place of continuing without the banner.

### Changed

- The `git` agent no longer says it is a worktree specialist. It is a small, fast agent
  for plain git commands. No skill dispatches it.
- `plugin.json` description and keywords name the rebase workflow.

## 2.0.0 — 2026-08-22

### Changed

- **Every command is now a skill.** The eight files in `commands/` moved to
  `skills/<name>/SKILL.md`. The bodies did not change, only the frontmatter and the
  names.
- **BREAKING — the operation names use a dash in place of the second colon.** A skill
  registers only from a single-level directory. `skills/worktree/list/SKILL.md` stays
  invisible to the Skill tool, so the nested names could not stay:

  | Before | After |
  | --- | --- |
  | `/git:worktree:list` | `/git:worktree-list` |
  | `/git:worktree:create` | `/git:worktree-create` |
  | `/git:worktree:delete` | `/git:worktree-delete` |
  | `/git:worktree:update` | `/git:worktree-update` |
  | `/git:rebase:main` | `/git:rebase-main` |
  | `/git:rebase:continue` | `/git:rebase-continue` |

  `/git:rebase` and `/git:merge` keep their names.
- **`/git:rebase` and `/git:rebase-main` stay forked skills.** Both keep
  `context: fork`, so the long rebase transcript stays out of the calling conversation
  and only the final status block comes back. The prose in both files now says skill in
  place of command.

### Fixed

- **`/git:worktree-list` is user-invocable.** The command carried
  `user-invocable: false`, which contradicted the README. The skill drops that field.
- **`/git:merge` calls the conflict resolver by its full name.** The body said
  `skill: "conflict-resolver"`, which does not resolve from inside a plugin. It now says
  `skill: "git:conflict-resolver"`, and `allowed-tools` matches.
