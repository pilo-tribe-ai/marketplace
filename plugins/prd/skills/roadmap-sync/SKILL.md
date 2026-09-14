---
description: Sync roadmap status table by scanning GitHub issues/PRs, verifying code existence, and flagging items whose PRD requirements drifted
argument-hint: "[roadmap-file]"
disable-model-invocation: true
model: sonnet
context: fork
agent: roadmap-analyst
allowed-tools: Agent, AskUserQuestion, Read, Edit, Grep, Glob, Bash
---

# Roadmap Sync

Sync the roadmap status table from two sources: real-world progress (GitHub issues/PRs, code existence) and PRD requirement drift (trace hash mismatches).

## Your Task

Update the roadmap status table in `{{roadmap}}` (default `docs/product/roadmap.md` when no argument is given) by dispatching parallel subagents to gather real-world status data, then run the requirement drift check.

Read the shared specifications first:
- `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` — trace format and hash rules
- `${CLAUDE_SKILL_DIR}/../shared/roadmap-table-schema.md` — statuses, Trace column, drift rules

## Process

### Step 1: Parse Roadmap

1. Read the roadmap file
2. Extract all item IDs: milestones (M1, M2...), features (F1.1, F1.2...), and stories (S1.1.1...)
3. Extract all `**Trace**` entries: requirement IDs and stored `@hash` values
4. Note current statuses in the table for comparison

### Step 2: Dispatch Parallel Subagents

Launch TWO parallel subagents using the Agent tool:

#### Agent 1: GitHub Scanner (Explore type)

Prompt the agent to:
- Search GitHub issues and PRs that reference any of the extracted item IDs
- For each match, record: item ID, GitHub item type (issue/PR), state (open/closed/merged), title
- Use `gh issue list --search "<ID>" --state all --json number,title,state` for issues
- Use `gh pr list --search "<ID>" --state all --json number,title,state,mergedAt` for PRs
- Return a structured summary mapping item IDs to their GitHub status

See `${CLAUDE_SKILL_DIR}/references/sync-sources.md` for search patterns and status inference rules.

#### Agent 2: Code Verifier (Explore type)

Prompt the agent to:
- For each feature and story ID, search the codebase for related files
- Use Grep to search for ID references in code comments and commit messages
- Use Glob to find files/directories matching feature names
- Check for test files corresponding to features
- Return a structured summary mapping item IDs to code existence signals

See `${CLAUDE_SKILL_DIR}/references/sync-sources.md` for verification patterns and status inference rules.

### Step 3: Requirement Drift Check

After both subagents return, execute the drift check procedure from `prd-schema.md` with scope *all* (including its short-circuit when the PRD has not changed since the last sync) and mode *interactive*. The interactive mode asks the user per drifted item, so it must not run while a subagent dispatch is still open. Use the PRD path named in the roadmap header (default `docs/product/prd.md`). The resulting `Needs Review` flags override any status derived in Step 4 — requirement drift beats progress signals.

### Step 4: Merge Progress Results

After both agents return:

1. For each roadmap item, combine signals from both sources
2. Apply the status inference rules from sync-sources.md (read in Step 2):
   - GitHub signals take priority over code signals
   - PR merged = strongest signal for `Completed`
   - PR open = strongest signal for `In Progress`
   - Code existence supports but doesn't override GitHub signals
3. Only change status when evidence is strong — keep current status if signals are weak or conflicting

### Step 5: Recalculate Table

1. Apply the table schema you read at the start (statuses, precedence, progress bars)
2. Apply updated statuses to items
3. Recalculate feature percentages based on story statuses
4. Recalculate milestone percentages based on feature percentages
5. Maintain existing group assignments and ordering

### Step 6: Update Roadmap

1. Replace content between `<!-- ROADMAP-STATUS-TABLE:START -->` and `<!-- ROADMAP-STATUS-TABLE:END -->` with regenerated table
2. Update "Last synced" date to today
3. Optionally update individual item checkboxes in the roadmap body if status changed to Completed (change `- [ ]` to `- [x]`)

### Step 7: Report Changes

Present a summary of changes:

| Item | Previous Status | New Status | Evidence |
|------|----------------|------------|----------|
| F1.1 | In Progress | Completed | PR #42 merged |
| S1.2.1 | Not Started | In Progress | Issue #55 assigned |
| F1.2 | Completed | Needs Review | CAP-1 changed in PRD (hash a1b2c3 → e4f5a6) |

If no changes were detected, report "Roadmap is up to date — no status changes and no requirement drift detected."
