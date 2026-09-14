---
description: Break down a feature into user stories through Socratic questioning
argument-hint: "[roadmap] [feature]"
model: sonnet
context: fork
agent: roadmap-analyst
allowed-tools: AskUserQuestion, Read, Edit, Grep, Bash
---

# Identify Stories - Feature Decomposition

Break down a feature into sprint-sized user stories through collaborative Socratic exploration.

## Your Task

1. Read the roadmap.md and locate the specified feature
2. Reference the source PRD for detailed requirements
3. Through Socratic questioning, identify user stories that implement this feature
4. Update the roadmap.md with the identified stories

**Caller contract**: when invoked from `/prd:plan`, the shared specs are already loaded and the caller regenerates the status table once at the end (skip Step 7).

## Process

### Step 1: Read Context

1. Read the roadmap at `{{roadmap}}` (default `docs/product/roadmap.md` when no argument is given)
2. Find feature `{{feature}}`
3. Understand the feature's description, user value, complexity, and its **Trace** (the PRD requirement IDs it satisfies)
4. Note the parent milestone's success criteria
5. Read the trace and hash rules in `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md`

### Step 2: Present Feature Context

Summarize:
- Feature name and description
- Who benefits (user value)
- Complexity level noted earlier
- Any dependencies

**Question**: "Is this feature well-enough defined to break into stories?"
- **Options**:
  - Yes, proceed
  - Need to clarify scope first
  - Feature is too vague - need more context

### Step 3: Story Discovery

#### 3.1 Identify Story Candidates

**Question**: "What are the key user actions or capabilities within this feature?"
- Provide 3-4 options derived from the feature description
- Frame as "As a user, I can..."

#### 3.2 For Each Story, Explore:

**User Story Format**
Help craft the story in standard format:
- "As a [persona]..."
- "I want to [action]..."
- "So that [benefit]..."

**Acceptance Criteria**
- "What must be true for this story to be considered done?"
- Explore 2-3 specific, testable criteria

**Story Scope**
- "Is this story small enough to complete in one sprint?"
- Options:
  - Yes - fits in a sprint
  - Borderline - might need splitting
  - Too large - definitely needs splitting
  - Spike needed - need research first

**Edge Cases**
- "Are there edge cases or error scenarios to consider?"
- Options: Common path only / Include basic error handling / Full edge case coverage

**Technical Considerations**
- "Are there technical constraints or considerations?"
- Options: None obvious / API changes needed / Database changes / UI complexity

### Step 4: Story Validation

For each story, validate it meets INVEST criteria:

- **I**ndependent - Can be developed without depending on other stories?
- **N**egotiable - Scope can be adjusted based on learning?
- **V**aluable - Delivers value to users or business?
- **E**stimable - Team can estimate the effort?
- **S**mall - Fits within a sprint?
- **T**estable - Has clear acceptance criteria?

**Question**: "Does this story meet the INVEST criteria?"
- **Options**: Yes / Too large / Not independent / Needs clearer criteria

### Step 5: Story Sequencing

**Question**: "In what order should these stories be implemented?"
- Options based on dependencies and value delivery
- Consider: foundations first, then enhancements

### Step 6: Update roadmap.md

Update the feature section with stories:

```markdown
  - Stories:
    - [ ] S{{feature}}.1: [Story title]
      - As a [persona], I want to [action] so that [benefit]
      - Acceptance Criteria:
        - [ ] [Criterion 1]
        - [ ] [Criterion 2]
      - Size: _TBD_ | Points: _TBD_
      - **Trace**: JRN-3 @b4c5d6   <!-- only when narrower than the feature's trace -->
      - Notes: [Any considerations]

    - [ ] S{{feature}}.2: [Story title]
      ...
```

**Trace rule** (defined in `prd-schema.md`): a story inherits its parent feature's trace implicitly — write no Trace line for it. Add a `**Trace**:` line (bold marker, exactly as in the schema) only when the story narrows to a more specific requirement (a journey step, persona, or constraint). Use PRD persona IDs (PER-n) in the "As a" clause where they exist.

### Step 7: Regenerate Status Table

> **Implementation Note:** The full calculation and regeneration rules are defined in `roadmap-table-schema.md`. Reference that file for the complete algorithm. The steps below are a summary.

After adding stories to the roadmap, regenerate the status table:

1. Apply the table schema from `${CLAUDE_SKILL_DIR}/../shared/roadmap-table-schema.md` (read it now if not already loaded)
2. Parse the full roadmap for all milestones, features, and stories
3. Recalculate feature percentages: `completed_stories / total_stories * 100`
4. Recalculate milestone percentages: `average(feature_percentages)`
5. Update statuses based on calculation rules
6. Replace the content between `<!-- ROADMAP-STATUS-TABLE:START -->` and `<!-- ROADMAP-STATUS-TABLE:END -->`
7. Update "Last synced" date

**Note:** The table only shows milestones and features, not individual stories.
Stories affect the percentages of their parent features.

## Exploration Patterns

### Story Discovery Questions

- "What's the first thing a user needs to do?"
- "What's the happy path vs edge cases?"
- "What happens when something goes wrong?"
- "How does the user know the action succeeded?"

### Story Splitting Techniques

When a story is too large, suggest splitting by:
- **Workflow steps** - Break into sequential actions
- **User types** - Different personas get different stories
- **Data variations** - Simple case vs complex case
- **Operations** - CRUD (Create, Read, Update, Delete)
- **Performance** - Basic vs optimized version

### Challenge Questions

- "Is this really one story or multiple bundled together?"
- "What's the simplest version that still delivers value?"
- "Could a junior developer implement this in a sprint?"
- "How will we demo this story?"

## Completion

When stories are added to roadmap.md:

**Recommend**: "Feature {{feature}} now has [N] stories defined. Next steps:
- Run `/prd:stories-estimate {{roadmap}} {{feature}}` to estimate these stories
- Or run `/prd:stories-identify {{roadmap}} [next-feature]` to break down another feature"
