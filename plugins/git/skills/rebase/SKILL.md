---
name: rebase
description: Rebase the current branch — onto the latest default branch, onto a branch you name, or resume a rebase in progress
argument-hint: "[branch|--continue]"
disable-model-invocation: true
model: sonnet
context: fork
allowed-tools: AskUserQuestion(*), Bash(*), Read(*), Edit(*), Grep(*), Glob(*)
---

You are now operating in **Interactive Git Rebase Mode**. You rebase the current branch,
and you guide the user through every conflict.

## Runs as a Fork

This skill runs in a forked context (`context: fork`). The fork starts with a copy of this
conversation, and it keeps its own context window. Only its last message goes back to the
parent session.

Three rules follow from this:

- **Put the result in the last message.** The parent session does not see the steps you do
  inside the fork. Write the Phase 3 Step 7 status block in full, also when the rebase
  stops early, aborts, or fails. It is the only output the user keeps.
- **One message per hand-off.** Everything the user needs in order to answer you must sit
  in the *same* message as the question. An earlier message is discarded, so a banner, a
  conflict listing, or a recommendation that you print on its own is lost, and the user
  sees only the question that followed it.
- **Read plugin files from `${CLAUDE_PLUGIN_ROOT}`.** The working directory of the fork is
  the user's repository. Plugin-relative paths do not resolve there.

## Output contract

Three rules hold for every run, in every mode. Read them before you do anything else.

1. **The ownership banner sits in the same message as the resolution options.** Phase 3
   Steps 0 to 4 produce one message, in that order: banner, conflict list, the conflict
   itself, your recommendation, then the options. Never send the banner in one message and
   the options in the next — the fork keeps only the last message, so a banner you sent
   earlier reaches nobody. This holds when you resume a rebase you did not start, and it
   holds again for each new conflict after a `git rebase --continue`. Before you ask the
   user to choose, check that the banner is in the message you are about to send.
2. **A run that stops ends with a status block.** Phase 3 Step 7 when the rebase
   completed, Phase 3 Step 8 when it stopped for any other reason. A turn that asks the
   user a question and waits for the answer is not a stop, and needs no status block.
3. **Never guess a branch name.** Read it, or say it is unknown and print the short SHA.

## Phase 0: Select the mode

Read the argument. It selects one mode:

| Argument | Mode | What it does |
| --- | --- | --- |
| none | **Latest default branch** | Fetch `origin`, find `main` or `master`, rebase onto it |
| a branch name | **Named branch** | Rebase onto that branch |
| `--continue` | **Resume** | Go back into a rebase that already started |

Two rules hold for every mode:

- A rebase that is already in progress wins. Phase 1 checks for one first, whatever the
  argument says.
- `main` and `--main` are not the same thing, and there is no `--main` argument. A bare
  run already goes to the latest default branch. `/git:rebase main` rebases onto your
  local branch named `main`, with no fetch.

## Phase 1: Rebase state detection

Always run this check first:

```bash
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
  echo "IN_REBASE"
else
  echo "NOT_IN_REBASE"
fi
```

**If `IN_REBASE`:** print this message, then go to Phase 3 and start at **Step 0**. The
argument does not matter — you cannot start a second rebase on top of one that is paused.
You did not start this rebase, so read the branch names from disk in Step 0 in place of
assuming them.

```
⚠️  An in-progress rebase was detected. Resuming conflict resolution...
```

**If `NOT_IN_REBASE` and the argument was `--continue`:** there is nothing to resume. Print
the Phase 3 Step 8 block, with `Stopped: no rebase in progress`, and these next steps:

- `/git:rebase` — rebase onto the latest default branch
- `/git:rebase <branch>` — rebase onto a branch you name

Then stop.

**If `NOT_IN_REBASE`:** go to Phase 2A when there is no argument, or Phase 2B when the
argument is a branch name.

## Phase 2A: Onto the latest default branch

This is the mode a bare `/git:rebase` runs. The point of it is "onto latest", so it always
fetches first.

### Step 1: Verify the repository

```bash
git rev-parse --is-inside-work-tree
```

If this fails, print the Step 8 block with `Stopped: not a git repository` and stop.

### Step 2: Detect the default branch

```bash
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'
```

If that prints nothing, the remote HEAD is not set. Refresh it, then read it again:

```bash
git remote set-head origin --auto 2>/dev/null
git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'
```

If it is still empty, fall back:

```bash
git show-ref --verify --quiet refs/remotes/origin/main && echo "origin/main"
git show-ref --verify --quiet refs/remotes/origin/master && echo "origin/master"
```

Store the result as `{default-branch}`, for example `origin/main`.

If every step above finds nothing, there is no default branch to rebase onto. Print the
Step 8 block, name the cause — usually no `origin` remote — and stop. Do not guess a
branch name.

### Step 3: Check the current branch

```bash
git rev-parse --abbrev-ref HEAD
```

If the current branch is the default branch, a rebase onto itself does nothing. Say so, and
use AskUserQuestion to offer:

- **Fast-forward pull** — run `git pull --ff-only`
- **Exit** — do nothing

### Step 4: Protect uncommitted work

```bash
git status --porcelain
```

If the output is not empty, do not rebase yet. Use AskUserQuestion to offer:

- **Stash and continue** — `git stash push -u -m "auto-stash before rebase onto {default-branch}"`. Remember that you made this stash; you must restore it in Step 7.
- **Commit first** — stop, so the user can commit
- **Abort** — stop

When you stop here, print the Step 8 block first.

### Step 5: Fetch

```bash
git fetch origin --prune
```

Report what moved:

```bash
git log --oneline HEAD..{default-branch} 2>/dev/null | head -10
```

If `{default-branch}` holds no new commit, there is nothing to rebase onto. Print the Step
8 block with `Stopped: {default-branch} has no new commits`, restore a Step 4 stash if you
made one, and stop.

### Step 6: Confirm and rebase

Show a short summary, and ask for agreement:

```
About to rebase:
  Current branch: {current-branch}
  Onto:           {default-branch} (just fetched)
  New commits:    {count} on {default-branch}

Proceed? (yes/no)
```

On agreement:

```bash
git rebase {default-branch}
```

### Step 7: Check the result

- **No conflict:** restore a Step 4 stash with `git stash pop` when you made one, then go
  to Phase 3 Step 7 and print the final status block. Do not stop at a one-line message —
  the fork returns only the last message. If the stash pop conflicts, go to Phase 3.
- **Conflict:** go to Phase 3, starting at Step 0. After the rebase finishes there,
  restore a Step 4 stash.

## Phase 2B: Onto a branch you name

### Step 1: Validate the name

```bash
git show-ref --verify --quiet refs/heads/{branch} || git show-ref --verify --quiet refs/remotes/{branch}
```

If the name does not resolve, do not fail flat. List the branches that were used most
recently:

```bash
git for-each-ref --sort=-committerdate --format='%(refname:short)|%(committerdate:relative)|%(authorname)' refs/heads refs/remotes
```

Drop the current branch. Drop every `HEAD` entry, including a bare remote name such as
`origin`, which is how `refs/remotes/origin/HEAD` prints — it is a pointer, not a branch.
Drop a remote copy of a local branch you already show. Use AskUserQuestion to offer the three most recent, with the relative date and the
author in each description, plus a fourth option that shows the full list. Take the choice
as the new `{branch}` and validate it again.

If the user cancels, print the Step 8 block with `Stopped: cancelled by user` and stop.

### Step 2: Protect uncommitted work

Run Phase 2A Step 4, without change.

### Step 3: Confirm and rebase

Confirm `Rebasing onto {branch}. Proceed? (yes/no)`, then:

```bash
git rebase {branch}
```

**This mode does not fetch.** You rebase onto the branch as it is on this machine now. When
`{branch}` is a remote-tracking branch such as `origin/develop`, say in the confirmation
that it is only as fresh as the last fetch.

### Step 4: Check the result

Same as Phase 2A Step 7.

## Phase 3: Conflict Resolution Workflow

Phase 3 starts at Step 0 every time you enter it — from Phase 1, from Phase 2A, from
Phase 2B, and again after each `git rebase --continue`. Do the steps in order.

### Step 0: Print the ownership banner

**This banner opens the message that carries the conflict and the options.** Steps 0 to 4
are one message, not five. Print the banner also when you already know which branch is
which, also when the conflict looks obvious, and also when you enter Phase 3 to resume a
rebase that another session started. The user does not have your context; the banner is
how they get it, and a banner in an earlier message never reaches them.

During a rebase, git's `--ours` and `--theirs` are **counterintuitive** compared to a merge:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  REBASE OWNERSHIP REFERENCE

  OURS   = {target-branch} (the branch you're rebasing onto)
  THEIRS = {current-branch} (your commits being replayed on top)

  In a rebase, git temporarily checks out the base branch and
  re-applies your commits one by one. So "ours" is the stable
  base, and "theirs" is your work.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Populate `{target-branch}` and `{current-branch}` by reading:
```bash
# Current branch being rebased — a full ref, for example refs/heads/feature
cat .git/rebase-merge/head-name 2>/dev/null || cat .git/rebase-apply/head-name 2>/dev/null

# Target branch. Not every git version writes onto_name, so fall back to the
# onto SHA and turn it back into a branch name.
cat .git/rebase-merge/onto_name 2>/dev/null \
  || cat .git/rebase-apply/onto_name 2>/dev/null \
  || git name-rev --name-only --refs='refs/heads/*' --refs='refs/remotes/*' \
       "$(cat .git/rebase-merge/onto 2>/dev/null || cat .git/rebase-apply/onto 2>/dev/null)"
```

**Do not guess a branch name.** When both commands above give you nothing, put the short
SHA in the banner and say the name is unknown. A banner that names the wrong branch is
worse than a banner that names a commit — the user resolves the conflict backwards.

### Step 1: Detect and List Conflicts

```bash
git status --porcelain | grep '^UU\|^AA\|^DD\|^AU\|^UA\|^DU\|^UD'
```

Also get context about which commit is being applied:

```bash
# Commit message being applied
cat .git/rebase-merge/message 2>/dev/null || cat .git/rebase-apply/final-commit 2>/dev/null | head -5
```

Present conflicts:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  CONFLICTS DETECTED

The following files have conflicts:
1. path/to/file1.js
2. path/to/file2.py
3. path/to/file3.md

REBASE CONTEXT:
Your branch:    {current-branch}  (THEIRS — your commits)
Rebasing onto:  {target-branch}   (OURS — the stable base)
Commit being applied: {commit-message}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 2: Present Each Conflict

For each conflicted file:

1. **Read the file** to get conflict markers
2. **Parse conflicts** (between `<<<<<<<`, `=======`, `>>>>>>>`)
3. **Present in human-readable format:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 CONFLICT IN: {filename}

📍 Location: Line {line-number}

OURS — {target-branch} (the branch you're rebasing onto):
{ours-code-block}

THEIRS — {current-branch} (your commit being replayed):
{theirs-code-block}

CONTEXT:
{surrounding-code-if-helpful}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Note on conflict markers during rebase:**
- `<<<<<<< HEAD` → This is **OURS** ({target-branch})
- `>>>>>>> {commit-sha}` → This is **THEIRS** ({current-branch} commit)

### Step 3: Provide Recommendations

Analyze and recommend based on:
- Size of changes
- Nature of conflict (addition, deletion, modification)
- Context from surrounding code
- Commit message intent

```
💡 RECOMMENDATION:

{Your analysis: e.g., "The OURS version (main) has a refactored function
signature. Your commit (THEIRS) uses the old signature. Accepting OURS
and porting your feature changes on top would be cleanest."}

SUGGESTED ACTION: {Accept OURS / Accept THEIRS / Manual merge}
★ Recommended: {option label}
```

Always state the recommendation explicitly and mark it with ★.

### Step 4: Present Resolution Options

**Open this message with the ownership banner.** Print the Step 0 banner again here, word
for word, directly above the options — also when you already printed it earlier in this
run. The fork keeps only your last message, so the copy that counts is this one:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  REBASE OWNERSHIP REFERENCE

  OURS   = {target-branch} (the branch you're rebasing onto)
  THEIRS = {current-branch} (your commits being replayed on top)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then use the AskUserQuestion tool. Always include the branch names in the labels so it's unambiguous:

```json
{
  "questions": [
    {
      "question": "How would you like to resolve the conflict in {filename}?",
      "header": "Resolution",
      "multiSelect": false,
      "options": [
        {
          "label": "Accept OURS — {target-branch} (Recommended ★)",
          "description": "Keep the version from {target-branch} (the branch being rebased onto). This is '--ours' in git terms."
        },
        {
          "label": "Accept THEIRS — {current-branch}",
          "description": "Keep your commit's version from {current-branch}. This is '--theirs' in git terms."
        },
        {
          "label": "Manual edit",
          "description": "Resolve the conflict yourself by editing the file. I'll guide you through the process."
        },
        {
          "label": "Show more context",
          "description": "Display more surrounding code to help understand the conflict better before deciding."
        }
      ]
    }
  ]
}
```

**Important:** The "Recommended ★" label should only appear on the actually recommended option based on the analysis in Phase 3 Step 3. Move it to whichever option you recommend. If manual merge is best, label that one as recommended.

**Note:** For advanced options like "Skip this commit" or "Abort rebase", select "Other" and I'll guide you through those operations with appropriate confirmations.

### Step 5: Execute Resolution

**If "Accept OURS" selected:**
```bash
# Keep the version from the base branch (--ours in rebase = target branch)
git checkout --ours {file}
git add {file}
```

**If "Accept THEIRS" selected:**
```bash
# Keep your commit's version (--theirs in rebase = your branch commits)
git checkout --theirs {file}
git add {file}
```

**If "Manual edit" selected:**
- Prompt: "Edit {file} to resolve conflicts, then tell me when done"
- Wait for confirmation
- Validate: Check no remaining conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
- Stage: `git add {file}`

**If "Show more context" selected:**
- Display more lines before/after conflict
- Re-present resolution options (return to Phase 3 Step 4)

**If "Other" (skip/abort):**
- Parse user input for keywords: "skip", "abort"
- **If skip detected:**
  - Confirm: "Are you sure you want to skip this commit? This will skip the current commit being applied."
  - If confirmed: `git rebase --skip`
  - Return to Phase 3 Step 0 if more conflicts, exit if rebase completes
- **If abort detected:**
  - Confirm: "Are you sure you want to abort the rebase? This will restore your repository to its pre-rebase state and discard all rebase progress."
  - If confirmed: `git rebase --abort`
  - Exit rebase mode
- **If unclear:** Ask for clarification and return to Phase 3 Step 4

### Step 6: Continue or Complete

After resolving all conflicts in current commit:

```bash
# Stage all resolved files (should already be staged per-file above)
git add {all-resolved-files}

# Continue rebase
git rebase --continue
```

**Check result:**
- If more conflicts: Return to Phase 3 **Step 0** — print the banner again, with the
  commit context of the new conflict
- If the rebase completes: Go to Phase 3 Step 7 and print the final status block
- If editor opens for commit message: Inform the user and wait

### Step 7: Final Status

When rebase completes:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ REBASE COMPLETE

Branch:        {branch-name}
Rebased onto:  {target-branch}
Commits applied: {count}

Next steps:
- Review changes: git log --oneline -10
- Push (force required): git push --force-with-lease

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 8: Status on an Early Exit

When the run stops before the rebase completes — the user cancels, the branch name is not
valid, the user aborts the rebase, or a command fails — print an equivalent block in place
of the Phase 3 Step 7 block. State what stopped the run, and what the repository state is now:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⛔ REBASE NOT COMPLETED

Branch:   {branch-name}
Stopped:  {reason — cancelled by user / rebase aborted / command failed}
State:    {e.g. "rebase aborted; the repository is back at its pre-rebase state"}

Next steps:
- {the one command or action that moves the user forward}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Key Principles

1. **Always clarify ours/theirs:** In every conflict, explicitly name the branches next to OURS and THEIRS — never leave the user guessing
2. **Recommend explicitly:** Always mark the recommended resolution with ★ in the option label
3. **Fetch in the default mode:** A bare run means "onto latest". A rebase onto a stale `origin/main` is the failure this mode exists to prevent
4. **Show context:** Display enough code to understand conflicts
5. **Loop until done:** After each `git rebase --continue`, check for new conflicts and loop back to Phase 3 Step 1
6. **Validate thoroughly:** Check for remaining markers before staging
7. **Be patient:** Take one conflict at a time, never rush
8. **Close with the status block:** The fork discards everything else, so the last message must state the outcome and the next step

## Safety Features

- Always use `--force-with-lease` instead of `--force` in recommendations
- Confirm before any destructive operation (skip, abort)
- Never rebase over uncommitted work without an explicit choice from the user
- Restore an auto-stash you made, and say when a stash is still held
- Validate no conflict markers remain before staging
- Show full file paths to avoid ambiguity
- Preserve commit messages and authorship

## Communication Style

- **Clear:** Use emojis and formatting for visual clarity
- **Concise:** Present essential information without verbosity
- **Helpful:** Provide recommendations, not just options
- **Unambiguous:** Always name branches next to OURS/THEIRS
- **Actionable:** Always clear about next steps

---

**Begin with Phase 0: read the argument, then run the Phase 1 state check.**
