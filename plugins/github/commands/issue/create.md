---
description: Create a GitHub issue with automatic project assignment
argument-hint: "[title]"
disable-model-invocation: true
allowed-tools: AskUserQuestion(*), Bash(git *), Bash(gh *), mcp__github__*(*), mcp__plugin_github_github__*(*), Read(*), Write(*), Grep(*)
---

# Create GitHub Issue

Create a GitHub issue with smart label matching and optional project assignment.

## Core Policies

- **Repository**: Auto-detected from git remote (cached after first use)
- **Project**: Optional assignment to org/repo project (cached after first use)
- **User Confirmation**: MANDATORY before any creation
- **Tool Preference**: Prefer GitHub MCP tools for issues/labels **if a GitHub MCP server is available**; otherwise use the `gh` CLI. Projects use the `gh` CLI either way.
- **Smart Labels**: Auto-match or prompt to create if no match found

## Configuration

Preferences cached in `.claude/github-issues.json`:

```json
{
  "owner": "org-name",
  "repo": "repo-name",
  "projectNumber": 2,
  "projectName": "Project Name"
}
```

## Implementation

### Phase 0: Configuration Setup

**On first run**, detect and cache configuration:

#### Step 0.1: Detect Repository

```bash
# Extract owner and repo from git remote
REMOTE_URL=$(git remote get-url origin)
# Parse: git@github.com:owner/repo.git or https://github.com/owner/repo.git
```

If detection fails, ask user:
- **"Which repository should issues be created in?"**
  - Option: Enter owner/repo (e.g., "myorg/myrepo")

#### Step 0.2: Detect Projects (Optional)

```bash
# List available projects for the org/repo
gh project list --owner [OWNER]
```

Present question:
- **"Should issues be automatically added to a project?"**
  - Option: "Yes, select a project"
  - Option: "No, skip project assignment"

If "Yes", show discovered projects and ask user to select.

#### Step 0.3: Cache Configuration

Write to `.claude/github-issues.json`:
```json
{
  "owner": "[OWNER]",
  "repo": "[REPO]",
  "projectNumber": [NUMBER or null],
  "projectName": "[NAME or null]"
}
```

**On subsequent runs**, read from cache and use those values.

### Phase 1: Setup

Detect available tooling. If a GitHub MCP server is configured (tools matching `mcp__github__*` / `mcp__plugin_github_github__*` are present), prefer it for issue/label operations and enable the `labels` toolset if supported:

```javascript
// Only if a GitHub MCP server is available
mcp__github__enable_toolset({ toolset: "labels" })
```

Otherwise, confirm the `gh` CLI is authenticated:

```bash
gh auth status
```

### Phase 2: Gather Information

If command is invoked **without arguments**, use `AskUserQuestion` to gather information through structured questions.

#### Question 1: Issue Type

**"What type of issue is this?"**

| Option | Description |
|--------|-------------|
| 🐛 Bug | Something isn't working |
| ✨ Feature | New functionality request |
| ⚡ Enhancement | Improvement to existing feature |
| 📝 Documentation | Docs changes needed |
| 📋 Task | General work item |

Store selection for label matching.

#### Question 2: Issue Title

**"What is the title for this issue?"**

Free text input. Should be clear and concise (5-10 words).

#### Question 3: Problem/Context

**"What is the problem or context for this issue?"**

Free text input. This becomes the main body of the issue.

#### Question 4: Acceptance Criteria (Optional)

**"What needs to be true for this to be complete? (Optional - leave blank to skip)"**

Free text input. If provided, format as checklist in issue body:
```markdown
## Acceptance Criteria
- [ ] Criteria 1
- [ ] Criteria 2
```

#### Question 5: Label Selection (Smart Matching)

**FIRST**: Query existing labels and parse .github/ISSUE_TEMPLATE:

**If a GitHub MCP server is available:**
```javascript
// Get all repo labels
const labels = await mcp__github__list_labels({ owner, repo });
```

**Otherwise, use the gh CLI:**
```bash
# Get all repo labels
gh label list --repo [owner]/[repo] --limit 100 --json name,description,color
```

In both cases, also check for `.github/ISSUE_TEMPLATE/*.yml` files and parse any label hints from templates.

**SECOND**: Attempt smart match based on issue type:

| Issue Type | Match Pattern |
|------------|---------------|
| Bug | Look for: `bug`, `Bug`, `🐛 bug`, `type: bug` (case-insensitive) |
| Feature | Look for: `feature`, `Feature`, `✨ feature`, `type: feature` |
| Enhancement | Look for: `enhancement`, `improvement`, `Improvement` |
| Documentation | Look for: `documentation`, `docs`, `📝 documentation` |
| Task | Look for: `task`, `Task`, `chore` |

**THIRD**: Present options based on match strength:

**If STRONG match found** (exact or fuzzy match with >80% confidence):
- Use `AskUserQuestion` with multiSelect
- Pre-select matched label(s)
- Show all other labels as options
- Include "Create new label" and "No label" options

**If NO strong match found**:
- Use `AskUserQuestion` with single select
- **"No matching label found for [Issue Type]. What would you like to do?"**
  - Option: "Create new label '[suggested-name]'" (e.g., "bug", "feature")
  - Option: "Choose from existing labels"
  - Option: "Skip label (no label)"

**If user selects "Create new label"**:
- Ask for label name (pre-filled with suggested name)
- Ask for label description (optional)
- Ask for label color:
  - Bug → `d73a4a` (red)
  - Feature → `0075ca` (blue)
  - Enhancement → `a2eeef` (light blue)
  - Documentation → `0075ca` (blue)
  - Task → `d4c5f9` (purple)

Create the label — **via MCP if available**:
```javascript
await mcp__github__create_label({
  owner, repo,
  name: "[label-name]",
  description: "[description]",
  color: "[color-hex]"
});
```

**Otherwise, via the gh CLI:**
```bash
gh label create "[label-name]" \
  --repo [owner]/[repo] \
  --description "[description]" \
  --color "[color-hex]"
```

### Phase 2.5: Confirmation

Show preview of issue to be created:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 ISSUE PREVIEW

Title: [title]
Type: [type]
Body: [first 100 chars]...
Acceptance Criteria: [Yes/No]
Labels: [label names]
Project: [projectName] (#[projectNumber]) or "None"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Create this issue?
```

Options: "Yes, create it" / "No, cancel"

### Phase 3: Create Issue

**If user confirms**, execute in sequence:

#### Step 1: Create Issue

**If a GitHub MCP server is available:**
```javascript
const issue = await mcp__github__issue_write({
  method: "create",
  owner: config.owner,
  repo: config.repo,
  title: "[confirmed title]",
  body: "[formatted body with acceptance criteria]",
  labels: ["selected-label"]
});
// Extract: issue.number, issue.html_url
```

**Otherwise, use the gh CLI:**
```bash
# --label may be repeated for multiple labels; omit if none selected
ISSUE_URL=$(gh issue create \
  --repo [owner]/[repo] \
  --title "[confirmed title]" \
  --body "[formatted body with acceptance criteria]" \
  --label "[selected-label]")
# gh prints the new issue URL on stdout; derive the number from the URL
```

#### Step 2: Add to Project (if configured)

**Only if** `config.projectNumber` is not null:

```bash
# Use the issue URL captured above (gh: $ISSUE_URL; MCP: issue.html_url)
gh project item-add [projectNumber] --owner [owner] --url "$ISSUE_URL" --format json
```

**Note**: No custom fields set. Projects typically auto-populate Status="Todo".

### Phase 4: Report Success

Display creation summary with visual formatting:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ ISSUE CREATED SUCCESSFULLY

Issue #[number]: [title]
URL: [issue_url]
Labels: [label names] or "None"
Project: [projectName] (#[projectNumber]) or "None"

To work on this issue in an isolated workspace:
git worktree add ../issue-[number]-[short-description] -b issue/[number]-[short-description]

Example: git worktree add ../issue-42-fix-auth-timeout -b issue/42-fix-auth-timeout
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Phase 5: Offer Worktree Creation

After displaying the success report, use `AskUserQuestion`:

**"Would you like to create a git worktree to work on this issue?"**

| Option | Description |
|--------|-------------|
| ✅ Yes | Add a git worktree for this issue |
| ⏭️ No | Stay in current workspace |

**If user selects "Yes"**:
- Suggest worktree name based on issue: `issue/[number]-[kebab-case-title]`
- Execute: `git worktree add ../issue-[number]-[short-description] -b issue/[number]-[short-description]`

## Command Argument Handling

If invoked **with arguments** (e.g., `/github:issue:create Fix auth timeout bug`):
- Use argument as default title
- Skip Question 2 (title), but still ask for confirmation
- Proceed with all other questions

## Error Handling

### Issue Creation Failed
```
❌ Failed to create issue
Error: [error message]

Please check:
- Repository permissions
- Network connectivity
- A GitHub MCP server connection, or `gh auth status` if using the CLI
```

### Project Integration Failed
```
⚠️ Issue created but project integration failed

Issue URL: [url]

Manual steps to add to project:
1. Visit https://github.com/orgs/[owner]/projects/[projectNumber]
2. Click "+ Add item"
3. Paste issue URL or search for #[number]
```

### Label Creation Failed
```
⚠️ Could not create label "[name]"
Continuing without label...
```

### Configuration Not Found
```
⚠️ No cached configuration found at .claude/github-issues.json
Running first-time setup...
```

## Configuration Management

To reset configuration (choose different repo/project):
```bash
rm .claude/github-issues.json
```

Then re-run the command to go through setup again.

## Dependencies

- A GitHub MCP server (preferred if available) **or** the `gh` CLI authenticated (with `project` scope if using projects)
- jq for JSON parsing (if using projects)
- Git repository with GitHub remote

## Example Usage

```bash
# Interactive mode (all questions)
/github:issue:create

# With title hint
/github:issue:create Add dark mode support to chat interface

# Bug report shortcut
/github:issue:create Fix: API timeout on large responses
```
