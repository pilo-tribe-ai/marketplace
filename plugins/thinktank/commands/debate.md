---
description: Conduct structured multi-agent analysis to determine optimal implementation approach
agent: debate-coordinator
allowed-tools: Task(*), Write(*), Read(*), Edit(*), AskUserQuestion(*), WebFetch(*), Grep(*), Glob(*)
---

# Think Tank Debate

## Initial Setup

### Step 1: Confirm Topic

First, check if there's a clear problem or topic in the conversation context. If so, confirm it with the user. Otherwise, ask them to provide the topic.

Use AskUserQuestion:

```json
{
  "questions": [
    {
      "question": "What topic or problem should we analyze in this Think Tank debate?",
      "header": "Debate Topic",
      "multiSelect": false,
      "options": [
        {"label": "Enter topic", "description": "Provide the problem, feature, or decision to analyze"}
      ]
    }
  ]
}
```

Store the confirmed topic as `DEBATE_TOPIC`.

---

### Step 2: Select Active Roles

Present the standard roles and allow users to select which agents they want to activate for this debate.

Use AskUserQuestion:

```json
{
  "questions": [
    {
      "question": "Which strategist perspectives do you want active in this debate?",
      "header": "Active Roles",
      "multiSelect": true,
      "options": [
        {"label": "Pragmatist", "description": "Fastest path to working solution with minimal complexity"},
        {"label": "Innovation-Focused", "description": "Elegant design, optimal outcomes, long-term extensibility"},
        {"label": "Research-Driven", "description": "Empirical evidence and proven best practices"},
        {"label": "Reuse-Focused", "description": "Leverage existing solutions, libraries, and community tools"}
      ]
    }
  ]
}
```

Store selected roles as `ACTIVE_ROLES`.

---

### Step 3: Custom Roles (Optional)

Ask if user wants to define additional custom roles.

Use AskUserQuestion:

```json
{
  "questions": [
    {
      "question": "Do you want to add custom strategist roles?",
      "header": "Custom Roles",
      "multiSelect": false,
      "options": [
        {"label": "Yes, add custom roles", "description": "Define additional perspectives for this debate"},
        {"label": "No, use selected roles", "description": "Proceed with standard roles"}
      ]
    }
  ]
}
```

If user selects "Yes", ask:

```json
{
  "questions": [
    {
      "question": "Define each custom role. Format: [Role Name]: [Description of strategic lens]",
      "header": "Custom Role Definitions",
      "multiSelect": false,
      "options": [
        {"label": "Enter custom roles", "description": "One role per line (e.g., 'Security-First: Focus on security constraints')"}
      ]
    }
  ]
}
```

Parse custom roles and append to `ACTIVE_ROLES`.

---

### Step 4: Confirm Debate Setup

Summarize the debate configuration before proceeding.

Output:
```markdown
# Debate Setup Confirmed

**Topic:** [DEBATE_TOPIC]

**Active Strategist Roles:**
- [Role 1]
- [Role 2]
- [Role 3]
...

Starting debate with [N] strategist perspectives.
```

---

## Phase 1: Initial Strategist Context Assessment

**DISPATCH Implementation Strategist Agents** for ONLY the selected roles, each with their distinct lens:

**Task for each selected agent:**
- Review the problem context: `[DEBATE_TOPIC]`
- Understand your role and perspective
- Identify the **top research topics/questions** you need answered to formulate your strategy
- Explain WHY each topic matters for your approach

Document their research needs in separate files:
- `research-needs/[ROLE_NAME]-questions.md` (one per selected role)

Example files (if all roles selected):
- `research-needs/pragmatist-questions.md`
- `research-needs/innovation-questions.md`
- `research-needs/research-driven-questions.md`
- `research-needs/reuse-focused-questions.md`

---

## Phase 2: Independent Research Execution

**For EACH selected strategist agent (N research cycles):**

1. **DISPATCH a dedicated Researcher Agent** for that specific strategist
2. Research agent investigates ONLY that strategist's questions
3. Research findings are documented in isolated files:
   - `research-results/[ROLE_NAME]-research.md` (one per selected role)

**CRITICAL**: Each research agent operates independently. No cross-contamination. Each strategist will only see their own research results.

---

## Phase 3: Strategy Proposals with Independent Research Context

**DISPATCH each selected Implementation Strategist Agent** with ONLY:
- Their original research questions
- Their own dedicated research findings (not others')
- Reminder of their strategic lens

Each agent must now:
- Analyze how their research informs their approach
- Propose a complete implementation strategy
- Present their most compelling argument for WHY their approach is superior
- Identify key trade-offs they're making
- Reference specific research findings that support their position

Document each perspective in:
- `proposals/[ROLE_NAME]-proposal.md` (one per selected role)

---

## Phase 4: Coordinated Socratic Deliberation

### Step 4.1: Deploy Debate Coordinator

**DISPATCH Debate Coordinator Agent** with:
- All strategy proposals (from selected roles only)
- The confirmed debate topic: `[DEBATE_TOPIC]`
- Instruction to identify:
  - Key points of tension and disagreement
  - Unexamined assumptions in each proposal
  - Critical trade-offs that need deeper exploration
  - Areas where proposals conflict or complement each other

Coordinator documents their analysis in `debate-plan.md`

### Step 4.2: Structured Debate Rounds (3 rounds minimum)

**For each round:**

1. **Coordinator generates Socratic questions** for each selected strategist
   - Questions should challenge assumptions
   - Questions should probe weaknesses
   - Questions should come "from" another specific agent's perspective
   - Questions should force deeper thinking

2. **DISPATCH each selected strategist agent** with:
   - All proposals from Phase 3
   - All previous round responses
   - Their specific question(s) from the coordinator
   - Instruction to respond substantively

3. Questions should probe:
   - Unexamined assumptions
   - Hidden costs or risks
   - Scalability concerns
   - Implementation complexity vs. benefit
   - Real-world constraints
   - Conflicts between approaches
   - "What would you say to [Agent X]'s concern about [Y]?"

4. **Coordinator reviews responses** and prepares next round questions

Document each round in:
- `deliberation/round-1-questions.md`
- `deliberation/round-1-responses.md`
- `deliberation/round-2-questions.md`
- `deliberation/round-2-responses.md`
- `deliberation/round-3-questions.md`
- `deliberation/round-3-responses.md`

### Step 4.3: Coordinator Synthesis Preparation

**DISPATCH Coordinator one final time** to:
- Review all debate rounds
- Identify which arguments held up under scrutiny
- Identify which concerns were resolved vs. remain valid
- Note areas of convergence and remaining disagreement
- Recommend which approach(es) emerged strongest

Document in `deliberation/coordinator-analysis.md`

---

## Phase 5: Final Synthesis & Recommendation

Using the coordinator's analysis and all deliberation context, synthesize findings into `RECOMMENDATION.md`:

### Structure:
- **Recommended Approach**: [Clear, concise statement]
- **Why This Approach**: [3-4 compelling reasons based on deliberation]
- **Key Trade-offs Accepted**: [What we're giving up and why it's acceptable]
- **Approaches Considered**: [Brief summary of alternatives from active roles]
- **Critical Success Factors**: [2-3 things that must go right]
- **Research Insights Applied**: [How key findings shaped the decision]
- **Debate Insights**: [Key turning points or revelations from the deliberation]

Keep this document under 500 words - focus on clarity and decision rationale.

---

## Critical Requirements
- ✅ ALWAYS use agent dispatching (never simulate internally)
- ✅ Each strategist gets ONLY their own research (no cross-contamination until Phase 4)
- ✅ One research cycle per selected strategist role
- ✅ Perspectives merge ONLY at deliberation phase
- ✅ Coordinator facilitates debate but does NOT advocate for a position
- ✅ Coordinator questions must be substantive, Socratic, and challenging
- ✅ Each strategist must respond to challenges, not just restate positions
- ✅ Final recommendation must be defensible based on the deliberation
- ✅ Maintain full context across all agent interactions during deliberation
- ✅ Support custom roles with same rigor as standard roles

## Success Criteria
- Topic clearly defined and confirmed
- Correct strategist roles activated (user's selection honored)
- Custom roles treated with same rigor as standard roles
- Each strategist asked role-specific research questions
- Research remained isolated until Phase 4
- Coordinator identified genuine tensions and conflicts
- Questions forced agents to reconsider or defend their positions
- Multiple truly distinct approaches emerged (no premature convergence)
- Real tensions and trade-offs were surfaced in deliberation
- At least one agent meaningfully evolved their position
- Final recommendation is better than any single agent's initial proposal
- Decision rationale is clear and well-supported
