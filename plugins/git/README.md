# Git

A Claude Code plugin for interactive git rebase with guided conflict resolution.

## Installation

```bash
# Add the marketplace (if not already added)
/plugin marketplace add 404pilo/claude-code.marketplace

# Install the plugin
/plugin install git@404pilo
```

## Overview

The plugin holds one skill, `/git:rebase`. An argument selects the mode:

| Command | What it does |
| --- | --- |
| `/git:rebase` | Fetch `origin`, find `main` or `master`, and rebase the current branch onto it |
| `/git:rebase <branch>` | Rebase onto the branch you name, with no fetch |
| `/git:rebase --continue` | Go back into a rebase that already started |

The bare run is the common case, so it is the default. It always fetches first, because a
rebase onto a stale `origin/main` is the failure this mode exists to prevent.

A rebase that is already in progress wins over the argument. `/git:rebase` finds the
paused rebase and takes you back to conflict resolution; it does not try to start a second
one.

There is no `--main` argument. `main` and `--main` would sit two characters apart and mean
different things, so the plugin does not have both.

## What it does with a conflict

- Shows a REBASE OWNERSHIP REFERENCE banner, so `OURS` and `THEIRS` are never ambiguous.
  In a rebase they are the opposite of a merge: `OURS` is the branch you rebase onto, and
  `THEIRS` is your own work being replayed
- Shows each conflict with its context, and marks the recommended resolution with ★
- Accept ours, accept theirs, or edit by hand
- Skips a commit or aborts the rebase only after a confirmation
- Checks that no conflict marker is left before it stages a file
- Loops until every conflict is resolved

## Runs as a fork

`/git:rebase` runs in a forked context (`context: fork`). A rebase transcript is long, so
it stays out of the calling conversation. Only the final status block comes back — the
completed block, or a block that says what stopped the run and what the repository state
is now.

## Safety

- Uncommitted work is never rebased over. The skill offers a stash, a commit, or an exit,
  and it restores a stash it made itself
- The skill recommends `git push --force-with-lease`, never `--force`
- A skip or an abort needs a confirmation first
- A branch name that does not resolve gets a list of recent branches, not a dead end

## Agent

### `git` (haiku model)

A fast agent for plain git commands. No skill dispatches it; use it when you want git work
done with a small model.

## Requirements

- Git
- A git repository, with a remote for the bare `/git:rebase`

## License

MIT License - Internal use within 404pilo organization
