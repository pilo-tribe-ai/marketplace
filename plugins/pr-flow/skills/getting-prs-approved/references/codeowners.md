# CODEOWNERS parsing and matching

Answers one question for `getting-prs-approved` Step 1: **who can approve this PR**, so we can
request review from them. Split out because the edge cases below are the difference between a
useful approver list and a useless one.

## Parse

Read CODEOWNERS **from the PR's base branch** — that's the copy GitHub enforces, so a head-branch
copy (including one this very PR edits) would produce a list that doesn't match branch protection.
GitHub checks three locations and uses the first it finds:

```bash
for p in .github/CODEOWNERS CODEOWNERS docs/CODEOWNERS; do
  gh api "repos/$REPO/contents/$p?ref=$BASE_REF" --jq '.content' 2>/dev/null \
    | base64 -d && break
done
```

Each non-blank, non-`#` line is `PATTERN owner…`, where owners are teams (`@org/team`) or
individuals (`@login`).

- **No file in any of the three locations, or an empty one → empty owner set.** A normal repo
  shape, not an error. Fall back to write-access collaborators; don't stop.
- **Keep the catch-all `*` rule.** Tempting to drop as "routing, not a statement about these
  paths" — don't. Under *Require review from Code Owners*, only a code owner's approval flips
  `reviewDecision` to `APPROVED`, so for a repo whose CODEOWNERS is just `* @org/team`, that team
  is the **only** answer. Dropping it sends the request to collaborators who can't unblock the PR,
  and the loop then polls forever without ever reaching the dead-end escalation.

## Match

Test the PR's changed paths (`.files[].path` from the payload already fetched — don't re-query)
against each pattern. `gh pr view --json files` returns at most 100 files; on a larger PR use
`gh api repos/$REPO/pulls/$N/files --paginate --jq '.[].filename'` rather than matching a
truncated list.

| Pattern shape | Meaning |
|---|---|
| Leading `/` (`/docs`) | anchored at the repo root |
| Trailing slash (`docs/adrs/`) | the directory and everything under it |
| No slash at all (`*.tf`, `build`) | matches at **any** directory depth |
| Otherwise (`src/**/api.ts`) | glob; `*` does not cross `/`, `**` does |

Last matching rule wins, per GitHub's own precedence.

## Using the result

Matched owners are eligible approvers. What happens next — the union with write-access
collaborators, the review request, the escalation when nobody is left — is Step 1's job and isn't
repeated here.

Two rules do live here, because they're properties of the owner set rather than the request flow:

- **Drop the PR author and our own login.** GitHub rejects a review request naming the author, and
  self-review is pointless. This empties the *CODEOWNERS* set only — whether to escalate is Step
  1's call on the **union** with collaborators, so don't escalate from here.
- **Team owners keep their `org/team` form, minus the `@`.** `gh pr edit --add-reviewer` takes
  `org/team` for a team and a bare `login` for a user. Passing `@org/team` verbatim fails and
  silently loses every team owner.
