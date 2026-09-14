---
description: Create a GitHub milestone with issue assignment
argument-hint: "[title] [due-date]"
disable-model-invocation: true
allowed-tools: AskUserQuestion(*), Bash(git *), Bash(gh *), Bash(jq *), mcp__github__*(*), mcp__plugin_github_github__*(*), Read(*), Write(*), Grep(*)
---

# Create GitHub Milestone

Create a GitHub milestone with optional due date and issue assignment.

**Source Documentation**: [GitHub REST API - Milestones](https://docs.github.com/en/rest/issues/milestones)

## Core Policies

- **Repository**: Auto-detected from git remote (cached after first use)
- **User Confirmation**: MANDATORY before any creation
- **Tool Preference**: Milestone operations use `gh api` (no MCP tool exists for milestones). Issue assignment prefers GitHub MCP tools **if a server is available**, otherwise `gh api`.
- **Due Date Format**: ISO 8601 format (`YYYY-MM-DDTHH:MM:SSZ`)
- **Issue Assignment**: Optional assignment of existing issues to milestone

**Note**: GitHub milestone endpoints are accessed via `gh api` (the REST API directly), since neither the `gh` CLI nor the GitHub MCP server exposes a dedicated milestone tool.

## Configuration

Preferences cached in `.claude/github-milestones.json`:

```json
{
  "owner": "org-name",
  "repo": "repo-name"
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
- **"Which repository should milestones be created in?"**
  - Option: Enter owner/repo (e.g., "myorg/myrepo")

#### Step 0.2: Cache Configuration

Write to `.claude/github-milestones.json`:
```json
{
  "owner": "[OWNER]",
  "repo": "[REPO]"
}
```

**On subsequent runs**, read from cache and use those values.

### Phase 1: List Existing Milestones

Show user existing milestones for context using GitHub REST API:

```bash
# List milestones via gh CLI
gh api "/repos/${OWNER}/${REPO}/milestones?state=all&per_page=10" \
  --jq '.[] | {number, title, state, due_on, open_issues, closed_issues}'
```

Display summary:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 EXISTING MILESTONES

Open:
  #1: v1.0 (Due: 2025-03-15) - 4 open, 8 closed
  #2: v2.0 (Due: 2025-06-01) - 12 open, 0 closed

Closed:
  #3: v0.9 (Completed: 2024-12-01) - 0 open, 15 closed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Phase 2: Gather Information

Use `AskUserQuestion` to gather information through structured questions.

#### Question 1: Milestone Title

**"What is the title for this milestone?"**

Free text input. Common patterns:
- Version numbers: `v1.0`, `v2.0.0`, `Release 3.5`
- Sprints: `Sprint 23`, `Q1 2025`
- Features: `Authentication MVP`, `Mobile Launch`

Examples: "v1.0", "Q1 2025 Goals", "MVP Launch"

#### Question 2: Milestone Description

**"What is the description for this milestone? (Optional - leave blank to skip)"**

Free text input. Should describe:
- Goals and objectives
- Key deliverables
- Success criteria

#### Question 3: Due Date

**"When is this milestone due? (Optional)"**

| Option | Description |
|--------|-------------|
| 📅 Set due date | Enter a specific date |
| ⏭️ No due date | Create without deadline |

**If "Set due date" selected**, ask for date:
- **"Enter due date (format: YYYY-MM-DD or YYYY-MM-DD HH:MM)"**
  - Examples: "2025-03-15", "2025-03-15 17:00"
  - Convert to ISO 8601: `YYYY-MM-DDTHH:MM:SSZ`
  - If no time provided, default to end of day: `23:59:59Z`

#### Question 4: Initial State

**"What should be the initial state of this milestone?"**

| Option | Description |
|--------|-------------|
| 🟢 Open | Active milestone (default) |
| 🔴 Closed | Completed or inactive |

#### Question 5: Issue Assignment (Optional)

**"Would you like to assign existing issues to this milestone?"**

| Option | Description |
|--------|-------------|
| ✅ Yes | Select issues to assign |
| ⏭️ No | Create milestone without issues |

**If "Yes" selected**:

1. List open issues:
```bash
gh issue list --repo [owner]/[repo] --limit 20 --json number,title,labels
```

2. Present multi-select question:
**"Select issues to assign to this milestone:"**
- Show issue format: `#[number]: [title] ([labels])`
- Allow multiple selections
- Option: "No issues" to skip

### Phase 2.5: Confirmation

Show preview of milestone to be created:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 MILESTONE PREVIEW

Title: v1.0
Description: [first 100 chars]... or "None"
State: Open/Closed
Due Date: 2025-03-15 23:59:59 UTC or "No deadline"
Issues to Assign: #42, #45, #67 or "None"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Create this milestone?
```

Options: "Yes, create it" / "No, cancel"

### Phase 3: Create Milestone

**If user confirms**, execute in sequence:

#### Step 1: Create Milestone via GitHub REST API

According to [GitHub REST API documentation](https://docs.github.com/en/rest/issues/milestones), create milestone using `gh api`:

```bash
# Build JSON payload
PAYLOAD=$(jq -n \
  --arg title "[confirmed title]" \
  --arg state "[open or closed]" \
  --arg description "[description or empty string]" \
  --arg due_on "[ISO 8601 date or empty string]" \
  '{
    title: $title,
    state: $state,
    description: (if $description == "" then null else $description end),
    due_on: (if $due_on == "" then null else $due_on end)
  }')

# Create milestone
RESULT=$(gh api "/repos/${OWNER}/${REPO}/milestones" \
  -X POST \
  --input - <<< "$PAYLOAD")

# Extract values
MILESTONE_NUMBER=$(echo "$RESULT" | jq -r '.number')
MILESTONE_URL=$(echo "$RESULT" | jq -r '.html_url')
MILESTONE_ID=$(echo "$RESULT" | jq -r '.id')
```

**API Request Body** (from official docs):
```json
{
  "title": "v1.0",
  "state": "open",
  "description": "Tracking milestone for version 1.0",
  "due_on": "2012-10-09T23:39:01Z"
}
```

**Note**: Field is `due_on` not `due_date` per GitHub REST API specification.

#### Step 2: Assign Issues to Milestone (if selected)

For each selected issue, assign it to the milestone.

**If a GitHub MCP server is available:**
```javascript
await mcp__github__issue_write({
  method: "update",
  owner: config.owner,
  repo: config.repo,
  issue_number: [issue_number],
  milestone: milestone.number
});
```

**Otherwise, via the REST API:**
```bash
# Assign issue to milestone (milestone field takes the milestone number)
gh api "/repos/${OWNER}/${REPO}/issues/[issue_number]" \
  -X PATCH \
  -F milestone=${MILESTONE_NUMBER}
```

### Phase 4: Report Success

Display creation summary with visual formatting:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ MILESTONE CREATED SUCCESSFULLY

Milestone #[number]: [title]
URL: [milestone_html_url]
State: [Open/Closed]
Due Date: [formatted date] or "No deadline"
Description: [Yes/No]
Assigned Issues: [count] issues assigned or "None"

Issues assigned:
  #42: Fix authentication bug
  #45: Add user profile page
  #67: Update documentation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Phase 5: Next Steps

Suggest common follow-up actions:

```
Next steps:
• View milestone: [html_url]
• List milestone issues: /github:issue:list milestone:[number]
• Create issue for milestone: /github:issue:create (then assign to milestone #[number])
```

## Command Argument Handling

If invoked **with arguments** (e.g., `/github:milestone:create v1.0 Release`):
- Use first argument as default title
- Skip Question 1 (title), but still ask for confirmation
- Proceed with all other questions

## Error Handling

### Milestone Creation Failed
```
❌ Failed to create milestone
Error: [error message]

Please check:
- Repository permissions
- Milestone title uniqueness
- Network connectivity
- `gh` CLI authentication (`gh auth status`) — milestone operations always use `gh api`
```

### Issue Assignment Failed
```
⚠️ Milestone created but issue assignment failed

Milestone URL: [url]
Failed to assign issues: #42, #45

Manual steps to assign issues:
1. Visit [milestone_url]
2. Search for issues by number
3. Click "Add issue" for each one
```

### Invalid Due Date Format
```
❌ Invalid due date format

Expected format: YYYY-MM-DD or YYYY-MM-DD HH:MM
Examples:
- 2025-03-15
- 2025-03-15 17:00
```

### Configuration Not Found
```
⚠️ No cached configuration found at .claude/github-milestones.json
Running first-time setup...
```

## Configuration Management

To reset configuration (choose different repo):
```bash
rm .claude/github-milestones.json
```

Then re-run the command to go through setup again.

## Dependencies

- `gh` CLI authenticated (required for `gh api` milestone operations and listing issues)
- A GitHub MCP server (optional — preferred for issue assignment if available)
- jq for JSON parsing
- Git repository with GitHub remote

## API Reference

This command uses the following GitHub REST API endpoints:

- **POST** `/repos/{owner}/{repo}/milestones` - Create milestone
  - Required: `title` (string)
  - Optional: `state` (open/closed), `description` (string), `due_on` (ISO 8601)
  - Response: milestone object with `number`, `html_url`, `id`

- **PATCH** `/repos/{owner}/{repo}/issues/{issue_number}` - Assign issue to milestone
  - Field: `milestone` (integer - milestone number)

- **GET** `/repos/{owner}/{repo}/milestones` - List milestones
  - Query params: `state`, `sort`, `direction`, `per_page`, `page`

Source: https://docs.github.com/en/rest/issues/milestones

## Example Usage

```bash
# Interactive mode (all questions)
/github:milestone:create

# With title hint
/github:milestone:create v2.0 Launch

# Version milestone
/github:milestone:create v1.5.0

# Sprint milestone
/github:milestone:create Sprint 23
```

## Best Practices

1. **Naming Convention**
   - Version milestones: `v1.0`, `v2.0.0`
   - Sprint milestones: `Sprint [number]`, `Q[quarter] [year]`
   - Feature milestones: `[Feature Name] MVP/Launch`

2. **Due Dates**
   - Set realistic deadlines based on team velocity
   - Use end-of-sprint or end-of-quarter dates
   - Consider time zones (UTC is default)

3. **Issue Assignment**
   - Assign issues that are scoped and ready
   - Don't overload milestones (aim for achievable scope)
   - Review and adjust as work progresses

4. **Milestone States**
   - Keep active milestones `open`
   - Close milestones when complete
   - Use descriptions to document outcomes when closing
