# Resolving the repo, the PR, and GitHub access

Shared by every pr-flow executor skill. Resolve once per run and hold the variables; later steps
read them instead of re-querying.

## Contents
- Resolve the repo and PR
- Probe access (gh vs MCP)

## Resolve the repo and PR

Derive everything from the working directory. Never hardcode a repo, never prompt for one.

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
ME="$(gh api user -q .login)"
TARGET="${PR:-$(git rev-parse --abbrev-ref HEAD)}"   # the [pr-number] arg, else this branch
PR_JSON="$(gh pr view "$TARGET" --repo "$REPO" \
  --json number,headRefName,baseRefName,headRefOid,state,isDraft,author)" || PR_JSON=""
N="$(jq -r '.number'         <<<"$PR_JSON")"
HEAD_REF="$(jq -r '.headRefName' <<<"$PR_JSON")"
BASE_REF="$(jq -r '.baseRefName' <<<"$PR_JSON")"
HEAD="$(jq -r '.headRefOid'  <<<"$PR_JSON")"         # full 40-char OID
```

Pass `"$TARGET"` positionally. `gh pr view` **requires a positional argument whenever `--repo` is
passed** and errors `argument required when using the --repo flag` on an empty `${PR:-}`.

Add whatever extra fields your skill needs to this one call rather than re-querying later.

Stop and say so when: `gh repo view` and `git remote get-url origin` both fail to yield an
`owner/repo` (the directory isn't a GitHub repo), or no PR resolves and none was passed.

## Probe access (gh vs MCP)

- **`gh` CLI** — working if `gh auth status` exits 0. On failure, retry once as
  `env -u GH_TOKEN gh auth status`; a stale `GH_TOKEN` in the environment is the usual cause.
  Use whichever invocation authenticated for every later call.
- **GitHub MCP** — counts only if a cheap identity call (`get_me`) returns a real answer. A
  server that is listed but erroring does not count, so verify before relying on it.

Default to `gh` when both work; an unattended loop must not stop to ask. `scheduling-pr-reviews`
is the exception — it is interactive at setup time and asks the user. Only one working → use it
and name it in the report. Neither → stop and tell the user to run `gh auth login` or fix the
MCP server.
