---
description: Perform technical analysis on a story to identify gaps, clarify requirements, and update documentation
argument-hint: "[issue-number]"
model: sonnet
context: fork
agent: github
allowed-tools: AskUserQuestion(*), Bash(git *), Bash(gh *), Bash(jq *), mcp__github__*(*), mcp__plugin_github_github__*(*), Read(*), Write(*), Edit(*), Grep(*), Glob(*), Task(*)
---

# Technical Analysis for GitHub Issues

Perform deep technical analysis on a story/issue to identify gaps, clarify requirements, gather decisions, and update roadmap and GitHub accordingly.

## Acceptance Criteria

```gherkin
Feature: Technical Analysis for GitHub Issues

  Scenario: Analyze story with existing GitHub issue
    Given a repository with .claude/github-milestones.json configured
      And a roadmap at docs/planning/roadmap.md containing Story 5.4
      And GitHub issue #45 exists for Story 5.4
    When I run /github:issue:technical-analysis 5.4
    Then the discoverer agent analyzes the story definition
      And I am prompted for each gap requiring clarification
      And decisions are recorded for roadmap update
      And I am asked to confirm before updates
      And the roadmap is updated with my decisions
      And the GitHub issue is updated with refined requirements

  Scenario: Analyze story without GitHub issue
    Given a repository with .claude/github-milestones.json configured
      And a roadmap at docs/planning/roadmap.md containing Story 5.4
      And no GitHub issue exists for Story 5.4
    When I run /github:issue:technical-analysis 5.4
    Then analysis proceeds with roadmap-only context
      And a new issue is created after analysis completes

  Scenario: Story not found in roadmap
    Given a repository with .claude/github-milestones.json configured
      And a roadmap at docs/planning/roadmap.md
      And Story 9.9 does not exist in roadmap
    When I run /github:issue:technical-analysis 9.9
    Then an error message is displayed
      And suggestions for verification are provided

  Scenario: Configuration not found
    Given no .claude/github-milestones.json exists
    When I run /github:issue:technical-analysis 5.4
    Then an error message explains the missing configuration
      And instructions to run /github:milestone:create are shown
```

## Prerequisites

### Required Configuration
- `.claude/github-milestones.json` - Created by `/github:milestone:create`
  ```json
  {
    "owner": "your-org",
    "repo": "your-repo",
    "milestoneNumber": 1
  }
  ```

### Required Files
- `docs/planning/roadmap.md` - Roadmap with stories in this format:
  ```markdown
  ### Story 5.4: [Story Title]

  **Description**: Brief description of the story

  **Acceptance Criteria**:
  - [ ] Criterion 1
  - [ ] Criterion 2

  **Conditions of Satisfaction**:
  - Measurable outcome 1
  - Measurable outcome 2

  **Size**: [XS/S/M/L/XL]

  **Dependencies**: [List or "None"]
  ```

## Core Policies

- **Repository**: Auto-detected from `.claude/github-milestones.json`
- **Roadmap**: Located at `docs/planning/roadmap.md`
- **Agent Pattern**: Sequential dispatch of specialized agents
- **User Confirmation**: MANDATORY before any updates
- **Tool Preference**: Prefer GitHub MCP tools **if a server is available**, otherwise the `gh` CLI; Task for agent dispatch

## Arguments

**ARGUMENTS**: Story identifier in any of these formats:
- Story number: `5.4`
- Story reference: `Story 5.4: Title`
- Issue number: `#45`

## Implementation

### Phase 1: Story Context Gathering

#### Step 1.1: Read Configuration and Roadmap

```javascript
// Read repo config
const config = await Read(".claude/github-milestones.json");
// Extract: owner, repo, milestoneNumber

// Read roadmap for story definition
const roadmap = await Read("docs/planning/roadmap.md");
```

If `.claude/github-milestones.json` not found:
```
⚠️ No milestone configuration found at .claude/github-milestones.json

Please create this file with:
{
  "owner": "your-org",
  "repo": "your-repo",
  "milestoneNumber": 1
}

Or run /github:milestone:create first.
```

#### Step 1.2: Extract Story Definition

Parse the roadmap to find the story matching `$ARGUMENTS`. Extract:
- Story number and title
- Current description
- Acceptance criteria (Gherkin if present)
- Conditions of satisfaction
- Dependencies/subtasks
- Size estimate

**If story not found:**
```
❌ Story not found in roadmap

Searched for: $ARGUMENTS
Location: docs/planning/roadmap.md

Please verify:
- Story number is correct
- Story exists in roadmap
- Try searching with different identifier
```

#### Step 1.3: Search GitHub for Related Issues

**If a GitHub MCP server is available:**
```javascript
await mcp__github__search_issues({
  query: "[story identifier] in:title",
  owner: config.owner,
  repo: config.repo
});
```

**Otherwise, use the gh CLI:**
```bash
gh issue list \
  --repo "${config.owner}/${config.repo}" \
  --search "[story identifier] in:title" \
  --state all \
  --json number,title,url,body
```

**If no issue found:**
```
⚠️ No GitHub issue found for story $ARGUMENTS

Continuing with roadmap-only analysis.
A new issue will be created after analysis.
```

### Phase 2: Technical Analysis Agent

**Dispatch**: Discoverer agent (`firework:discoverer`)

This agent is purpose-built for gap identification between stated and actual requirements, with aggressive scope deferral to catch missing items.

```javascript
await Task({
  subagent_type: "firework:discoverer",
  description: "Analyze story requirements gaps",
  prompt: `
    Analyze story: [story title]

    Story Definition:
    [extracted story content from roadmap]

    GitHub Issue (if exists):
    [issue body]

    Local Context:
    - Read CLAUDE.md for project conventions
    - Read existing code patterns in relevant directories

    Perform comprehensive analysis:

    1. **Acceptance Criteria Assessment**
       - Is the acceptance criteria well-defined and testable?
       - Are Gherkin scenarios complete with Given/When/Then?
       - What scenarios are missing?
       - Flag any vague or ambiguous criteria

    2. **Conditions of Satisfaction Assessment**
       - Are conditions measurable and verifiable?
       - Are quantitative targets defined where needed?
       - What conditions are missing?

    3. **Technical Inputs Identification**
       - What data/state must be available before starting?
       - What APIs, services, or systems must be ready?
       - What dependencies from other stories must complete first?
       - What documentation or specifications are needed?

    4. **Invariants & Constraints**
       - Architectural patterns that must be maintained
       - Coding standards and conventions
       - Security/compliance constraints
       - Invariants the implementation must preserve

    5. **Architectural Decisions**
       - What design decisions need to be made?
       - Are there technology choices required?
       - Are there integration patterns to decide?
       - What trade-offs need evaluation?

    6. **Code Impact Analysis**
       - Which directories/files will likely be modified?
       - What new files will need to be created?
       - What existing patterns should be followed?
       - What tests will need to be added/modified?

    7. **Deliverables Inventory**
       - What code artifacts will be produced?
       - What documentation updates are needed?
       - What configuration changes are required?

    Output: Structured inventory categorized by:
    - 🔴 Critical (blocks start)
    - 🟡 Important (affects quality)
    - 🟢 Nice-to-have (refinement)
  `
});
```

### Phase 3: Strategic Clarification

For EACH inventory item requiring user input, dispatch strategist agent:

```javascript
await Task({
  subagent_type: "firework:strategist",
  description: "Analyze [item] options",
  prompt: `
    Analyze: [inventory item]

    Context: [summary of story and why this matters]

    Tasks:
    1. Research alternatives/options
    2. Identify pros/cons of each
    3. Formulate a clear recommendation
    4. Prepare options for user question
  `
});
```

#### Step 3.1: Present to User via AskUserQuestion

For each item needing clarification, present structured question:

```json
{
  "questions": [
    {
      "question": "[Context] - [Clear question]?",
      "header": "[Short label]",
      "multiSelect": false,
      "options": [
        {
          "label": "[Option 1] (Recommended)",
          "description": "[Why this is recommended]"
        },
        {
          "label": "[Option 2]",
          "description": "[Trade-off explanation]"
        },
        {
          "label": "[Option 3]",
          "description": "[Trade-off explanation]"
        }
      ]
    }
  ]
}
```

**Example:**
```
Context: Story 5.4 requires expert-validated conversations. The number of
conversations per reason code affects dataset quality vs. timeline.

Question: "How many golden conversations should be created per reason code?"

Options:
- 3-5 per code (Recommended) - Balanced coverage with state variations
- 2 per code - Minimum viable, one happy path + one edge case
- Variable by complexity - 2-3 for simple, 5-10 for complex codes
```

#### Step 3.2: Record Decisions

After each user answer, record:
- The question asked
- The decision made
- The rationale (if provided)

Store in memory for Phase 4 updates.

### Phase 4: Update Documentation

**MANDATORY**: Confirm before any updates.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 PROPOSED UPDATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Roadmap Changes:
- [Change 1]
- [Change 2]

GitHub Updates:
- Update issue #[number]: [summary]
- Create sub-issue: [title]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Use AskUserQuestion:
- **"Apply these updates?"**
  - ✅ Yes, apply all updates
  - 📝 Yes, but let me review the roadmap diff first
  - ❌ No, cancel

#### Step 4.1: Update roadmap.md

Apply all gathered decisions to the story definition:
- Update description if scope changed
- Refine acceptance criteria with specifics
- Update conditions of satisfaction with quantitative targets
- Add/modify subtasks based on decisions
- Adjust size estimate if needed
- Update dependencies

```javascript
await Edit({
  file_path: "docs/planning/roadmap.md",
  old_string: "[original story section]",
  new_string: "[updated story section with decisions]"
});
```

#### Step 4.2: Update GitHub Issues

**If a GitHub MCP server is available:**
```javascript
// If story issue exists, update it
await mcp__github__issue_write({
  method: "update",
  owner: config.owner,
  repo: config.repo,
  issue_number: existingIssue.number,
  body: "[updated description with decisions]"
});

// Create sub-issues if story was broken down
for (const subtask of newSubtasks) {
  await mcp__github__issue_write({
    method: "create",
    owner: config.owner,
    repo: config.repo,
    title: subtask.title,
    body: subtask.description,
    milestone: config.milestoneNumber
  });
}
```

**Otherwise, use the gh CLI:**
```bash
# If story issue exists, update it
gh issue edit [existingIssue.number] \
  --repo "${config.owner}/${config.repo}" \
  --body "[updated description with decisions]"

# Create sub-issues if story was broken down (loop over each new subtask)
gh issue create \
  --repo "${config.owner}/${config.repo}" \
  --title "[subtask.title]" \
  --body "[subtask.description]" \
  --milestone "[config.milestoneNumber]"
```

### Phase 5: Summary Report

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ TECHNICAL ANALYSIS COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Story: [identifier] - [title]

ANALYSIS RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Items Analyzed: [count]
Decisions Made: [count]
Issues Created: [count]
Issues Updated: [count]

DECISIONS CAPTURED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. [Decision 1]: [choice made]
2. [Decision 2]: [choice made]
...

ROADMAP CHANGES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- [Change 1]
- [Change 2]
...

GITHUB UPDATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Updated: #[issue] - [title]
Created: #[issue] - [title]
...

NEXT STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Review changes: git diff docs/planning/roadmap.md
• Story is ready for implementation
• Consider running /github:issue:create for any new sub-stories
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Inventory Categories

The analysis agent categorizes findings into:

### Technical Inputs
- Data requirements
- API/service dependencies
- Story dependencies
- Documentation needs

### Invariants
- Architectural patterns to maintain
- Code style requirements
- Security constraints
- Performance requirements

### Architectural Decisions
- Technology choices
- Integration patterns
- Data model decisions
- API design decisions

### Code Impact
- Files to modify
- Files to create
- Patterns to follow
- Tests to add

### Deliverables
- Code artifacts
- Documentation updates
- Configuration changes

## Error Handling

### Configuration Not Found
```
❌ Configuration file not found

Expected: .claude/github-milestones.json

Please create this file or run:
/github:milestone:create
```

### Story Not Found
```
❌ Story not found in roadmap

Searched for: [identifier]
Location: docs/planning/roadmap.md

Please verify:
- Story number is correct
- Story exists in roadmap
- Try searching with different identifier
```

### Agent Dispatch Failed
```
❌ Failed to dispatch [agent name]
Error: [error message]

Retrying with fallback approach...
```

### GitHub API Error
```
❌ GitHub API error

Error: [error message]

Please check:
- A GitHub MCP server connection, or `gh auth status` if using the CLI
- Repository permissions
- Network connectivity
```

## Example Usage

```bash
# Analyze specific story by number
/github:issue:technical-analysis 5.4

# Analyze by full story reference
/github:issue:technical-analysis Story 5.4: Build golden dataset

# Analyze by issue number
/github:issue:technical-analysis #45
```

## Dependencies

- A GitHub MCP server (preferred if available) **or** the `gh` CLI authenticated
- Discoverer agent (firework:discoverer) - gap identification
- Strategist agent (firework:strategist) - approach generation
- Roadmap at `docs/planning/roadmap.md`
- Config at `.claude/github-milestones.json`
