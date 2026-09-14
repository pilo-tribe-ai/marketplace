---
description: Iteratively estimate stories using T-shirt sizing through guided questioning
argument-hint: "[roadmap] [feature]"
model: haiku
context: fork
agent: roadmap-analyst
allowed-tools: AskUserQuestion, Read, Edit, Grep
---

# Estimate Stories - T-Shirt Sizing

Guide the team through estimating stories one at a time using T-shirt sizes (S/M/L).

## Your Task

1. Read the roadmap.md and find all stories for the specified feature
2. For each story, present context and suggest an estimate
3. Use AskUserQuestion to gather the team's estimate
4. Update roadmap.md with the agreed estimates

## Estimation Scale

| Size | Points | Typical Scope |
|------|--------|---------------|
| **S** | 1 | Simple, well-understood, < 1 day of work |
| **M** | 3 | Moderate complexity, some unknowns, 1-3 days |
| **L** | 5 | Complex, significant effort, 3-5 days or needs splitting |

## Process

### Step 1: Read Context

1. Read the roadmap at `{{roadmap}}` (default `docs/product/roadmap.md` when no argument is given)
2. Find feature `{{feature}}` and extract all stories
3. Count total stories to estimate

**Present**: "Feature {{feature}} has [N] stories to estimate. Let's go through them one at a time."

### Step 2: Estimation Loop

**For each story**, do the following:

#### 2.1 Present the Story

Display:
- Story ID and title
- Full user story (As a... I want... So that...)
- Acceptance criteria
- Any technical notes
- Progress: "Story [X] of [N]"

#### 2.2 Provide Your Suggested Estimate

Based on:
- Acceptance criteria complexity
- Technical considerations noted
- Comparison to other stories
- Industry patterns

Present your suggestion with reasoning:

> "Based on [reasoning], I suggest this is a **[S/M/L]** story."

#### 2.3 Ask for Team's Estimate

**Question**: "What's your estimate for this story?"
- **Header**: "Size"
- **Options**:
  - **S (Small)** - Simple, well-understood, less than 1 day
  - **M (Medium)** - Moderate complexity, 1-3 days
  - **L (Large)** - Complex, 3-5 days (consider splitting)
  - **? (Discuss)** - Need more information or discussion

#### 2.4 Handle Responses

**If S, M, or L selected:**
- Record the estimate
- Move to next story

**If "Discuss" selected:**

Ask clarifying questions:
- "What aspect of this story is unclear?"
  - Options: Scope / Technical approach / Acceptance criteria / Dependencies

Then probe deeper based on selection:
- For **Scope**: "What's the minimum viable version?"
- For **Technical**: "What technical unknowns exist?"
- For **Criteria**: "Which criterion is unclear?"
- For **Dependencies**: "What does this depend on?"

After discussion, re-ask for estimate.

#### 2.5 Challenge Large Estimates

**If L is selected**, always ask:

**Question**: "Large stories often benefit from splitting. Should we split this story?"
- **Options**:
  - Keep as L - complexity is inherent, can't simplify
  - Split into 2 stories - clear division exists
  - Spike first - need research before estimating
  - Revisit scope - acceptance criteria too broad

If splitting, help define the split and estimate each part.

### Step 3: Update roadmap.md

After each story is estimated, update the roadmap:

```markdown
    - [ ] S{{feature}}.1: [Story title]
      - As a [persona], I want to [action] so that [benefit]
      - Acceptance Criteria:
        - [ ] [Criterion 1]
        - [ ] [Criterion 2]
      - Size: **S** | Points: **1**
```

### Step 4: Summary

After all stories are estimated, present:

```
## Estimation Summary for {{feature}}

| Story | Title | Size | Points |
|-------|-------|------|--------|
| S{{feature}}.1 | [title] | S | 1 |
| S{{feature}}.2 | [title] | M | 3 |
| S{{feature}}.3 | [title] | L | 5 |

**Total Points**: [sum]
**Estimated Sprints**: [total / velocity] (assuming velocity of ~10 points/sprint)
```

**Question**: "Does this estimation feel right for the feature?"
- **Options**:
  - Yes, looks good
  - Some stories need re-estimation
  - Total is too high - need to reduce scope
  - Total is suspiciously low - are we missing complexity?

### Step 5: Note on Status Table

Estimation changes do not affect the roadmap status table. The table tracks completion status (from checkboxes), not estimates. No table regeneration is needed after estimation.

If you also marked stories as complete during estimation, the status table should be regenerated — but that is the responsibility of the stories-identify skill, not this skill.

## Estimation Guidance

### Signs of a Small (S) Story
- Single acceptance criterion
- No database changes
- UI-only or API-only (not both)
- Similar to something built before
- No external dependencies

### Signs of a Medium (M) Story
- 2-3 acceptance criteria
- Some database changes
- Touches UI and API
- Some unknowns but manageable
- Limited external dependencies

### Signs of a Large (L) Story
- 4+ acceptance criteria
- Significant database changes
- Complex UI interactions
- Multiple unknowns
- External dependencies or integrations
- **Consider splitting!**

### Red Flags (Story Needs Refinement)
- "And" in the story title (multiple stories bundled)
- Vague acceptance criteria
- Unknown technical approach
- No clear done state
- Depends on unestimated work

## Completion

When all stories are estimated:

**Recommend**: "Feature {{feature}} is fully estimated at [N] points. Next steps:
- Run `/prd:stories-estimate {{roadmap}} [next-feature]` to estimate another feature
- Review the full roadmap to see milestone totals
- Begin sprint planning with estimated stories"
