---
description: Create a new pull request
argument-hint: "[title]"
disable-model-invocation: true
allowed-tools: AskUserQuestion(*), Bash(git status:*), Bash(git branch:*), Bash(git remote:*), Bash(git push:*), Bash(git log:*), Bash(git diff:*), Bash(git show:*), Bash(git rev-parse:*), Bash(gh pr:*), Bash(gh api:*), mcp__github__*(*), mcp__plugin_github_github__*(*), Read(*), Grep(*)
---

# Pull Request Command

Create GitHub pull request with comprehensive description. ONLY command that creates PRs.

## Core Policies

- **Single Purpose**: ONLY command that creates PRs
- **Duplicate Prevention**: Always check for existing PRs first
- **Auto-Assignee**: PR author automatically assigned
- **Tool Preference**: Prefer GitHub MCP tools **if a GitHub MCP server is available** in the environment; otherwise use the `gh` CLI
- **Visual Communication**: Use emojis throughout for clarity and better UX (✅ ❌ 📝 🔄 🔀 📦 🌳 etc.)

## Implementation

**CRITICAL**: This plugin bundles no MCP server. Detect what is available: if GitHub MCP tools (`mcp__github__*` or `mcp__plugin_github_github__*`) are present, prefer them; otherwise use the `gh` CLI (ensure `gh auth status` is authenticated).

### 1. Pre-Flight Validation

```bash
git status --porcelain  # Must be clean
BRANCH=$(git branch --show-current)  # Must be feature branch
git remote -v  # Must have GitHub remote
```

### 2. Check for Existing PR

**If a GitHub MCP server is available**, load and use its search tool:
```javascript
// e.g. ToolSearch("select:mcp__github__search_pull_requests")
await mcp__github__search_pull_requests({
  owner, repo,
  query: `is:open head:${CURRENT_BRANCH}`
})
// Exit if PR exists
```

**Otherwise (no MCP server), use the gh CLI:**
```bash
# Check for an open PR on the current branch
gh pr view --json number,title,url 2>/dev/null
# Exit early if a PR already exists
```

### 3. Analyze Changes

```bash
# Determine base branch (main/master/develop)
BASE=$(git remote show origin | sed -n 's/.*HEAD branch: //p')

# Get commits and diffs
git log $BASE..HEAD --oneline
git diff $BASE..HEAD --stat
```

### 4. Generate Human-Readable Title

**Critical**: NOT conventional commit format

**Good Examples**:
- "Add OAuth integration and user dashboard"
- "Fix authentication issues and improve error handling"
- "Enhance user management with profile editing"

**Bad Examples**:
- ❌ "feat(auth): add oauth integration" (too technical)
- ❌ "fix: various bugfixes" (too vague)

### 5. Generate Description

**Philosophy**: Less is more. Summarize, don't enumerate.

- **Summary**: 2-3 sentences max capturing the essence
- **Key Changes**: 3-5 bullet points of most significant changes only
- **Skip**: Don't list every commit, file change, or minor detail

Focus on why this matters, not exhaustive what changed.

### 6. Ask User Preferences

Use AskUserQuestion tool with emojis for visual clarity. Example format:

```json
{
  "questions": [
    {
      "question": "📝 Should this be a draft PR or ready for review?",
      "header": "PR Status",
      "multiSelect": false,
      "options": [
        {
          "label": "📝 Draft PR",
          "description": "Create as draft (not ready for review yet)"
        },
        {
          "label": "✅ Ready for review",
          "description": "Create as ready for review"
        }
      ]
    },
    {
      "question": "🔄 Should automerge be enabled?",
      "header": "Automerge",
      "multiSelect": false,
      "options": [
        {
          "label": "🔄 Enable automerge",
          "description": "PR will merge automatically when checks pass"
        },
        {
          "label": "⏸️ No automerge",
          "description": "Manual merge required"
        }
      ]
    },
    {
      "question": "🔀 Which merge strategy should be used?",
      "header": "Merge Type",
      "multiSelect": false,
      "options": [
        {
          "label": "📦 Squash and merge",
          "description": "Combine all commits into one"
        },
        {
          "label": "🌳 Create a merge commit",
          "description": "Preserve all commits with merge commit"
        },
        {
          "label": "📝 Rebase and merge",
          "description": "Apply commits linearly without merge commit"
        }
      ]
    }
  ]
}
```

**Store answers:**
- `isDraft` from Question 1
- `enableAutomerge` from Question 2
- `mergeStrategy` from Question 3 (map: "Squash and merge" → `--squash`, "Create a merge commit" → `--merge`, "Rebase and merge" → `--rebase`)

### 7. Push Branch

```bash
git push origin $BRANCH
# OR: git push -u origin $BRANCH (if new)
```

### 8. Create PR

**If a GitHub MCP server is available**, create the PR via its tool:
```javascript
// e.g. ToolSearch("select:mcp__github__create_pull_request")
const pr = await mcp__github__create_pull_request({
  owner, repo,
  title,
  body,
  base: BASE_BRANCH,
  head: HEAD_BRANCH,
  draft: isDraft  // from user question
});
// Automerge has no MCP tool — use `gh pr merge --auto $MERGE_FLAG` afterward
```

**Otherwise (no MCP server), use the gh CLI:**
```bash
# Note: gh CLI has no --ready-for-review flag
# PRs are ready for review by default unless --draft is used
gh pr create \
  --title "$TITLE" \
  --body "$DESCRIPTION" \
  --assignee "@me" \
  $([ "$isDraft" = true ] && echo "--draft")

# Enable automerge if requested (after PR is created)
[ "$enableAutomerge" = true ] && gh pr merge --auto $MERGE_FLAG
```

### 9. Display Result

Show PR URL and summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PULL REQUEST CREATED

Title: {title}
URL: {pr_url}
Status: {Draft/Ready for Review}
Automerge: {Enabled/Disabled}
Merge Strategy: {Squash/Merge/Rebase}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Key Principles

1. **MCP if available, else gh CLI**: Prefer GitHub MCP tools when a server is configured; otherwise use the `gh` CLI
2. **Human Titles**: Generate readable titles, not conventional commit format
3. **Concise Descriptions**: Summarize essence, don't enumerate everything
4. **User Control**: Ask about draft status and automerge preferences
5. **Clean State**: Validate working tree is clean before proceeding
6. **Duplicate Check**: Always check for existing PR first

## Safety Validations

- ✅ Clean working directory
- ✅ On feature branch
- ✅ No duplicate PR exists
- ✅ Human-readable title
- ✅ Author auto-assigned
- ✅ Draft status determined by user
- ✅ Automerge configured per user preference
- ✅ Merge strategy chosen by user

## Communication Style

- **Clear**: Use emojis and formatting for visual clarity
- **Concise**: Present essential information without verbosity
- **Actionable**: Always show the PR URL prominently
- **Flexible**: Support both MCP and CLI gracefully

## Reference

- PR standards: See CLAUDE.md (if exists in repo)
- Commit format: See `/commit` command

---

**Begin by validating git state and checking for existing PRs.**
