# Think Tank Plugin

Strategic analysis through structured multi-agent deliberation and Socratic debate.

## Overview

The Think Tank plugin enables you to leverage multiple AI strategists with distinct perspectives to analyze complex problems and arrive at optimal implementation decisions. The plugin orchestrates a rigorous 5-phase process:

1. **Context Assessment** - Strategists identify research questions
2. **Independent Research** - Each strategist's questions researched independently
3. **Strategy Proposals** - Each strategist proposes an approach based on their research
4. **Socratic Deliberation** - Structured debate rounds test assumptions and probe trade-offs
5. **Synthesis** - Final recommendation based on deliberation outcomes

## The `/thinktank:debate` Command

Invoke the multi-agent strategic analysis process:

```bash
/thinktank:debate
```

When you run the command, you'll be prompted to:
1. **Confirm or provide a debate topic** - The problem, feature, or decision to analyze
2. **Select active strategist roles** - Choose which perspectives you want (Pragmatist, Innovation-Focused, Research-Driven, Reuse-Focused)
3. **Add custom roles (optional)** - Define additional strategic perspectives if needed

The system will then:

- **Execute Independent Research**: Each selected strategist's questions researched separately
- **Generate Proposals**: Complete implementation strategies with reasoning from each perspective
- **Facilitate Debate**: 3+ rounds of Socratic questioning between selected agents
- **Synthesize Recommendation**: Final approach with trade-offs and reasoning

## The Three Agents

### Researcher Agent (Haiku)
Fast, efficient web researcher who investigates specific questions for strategists.

- Conducts focused research on assigned topics
- Gathers factual, current information
- Documents findings with sources
- Reports objective results

### Implementation Strategist Agent (Sonnet)
Strategic analyst who proposes approaches from a specific perspective.

- Analyzes problems through their strategic lens
- Reviews strategist-specific research
- Proposes complete implementation strategies
- Articulates compelling reasoning
- Defends positions during debate
- Identifies and explains trade-offs

### Debate Coordinator Agent (Sonnet)
Socratic facilitator orchestrating the entire process.

- Dispatches researcher agents
- Gathers independent proposals
- Identifies tensions and conflicts
- Generates Socratic questions
- Facilitates debate rounds
- Synthesizes findings into recommendation

## Process Phases

### Phase 1: Context Assessment
Strategists review the problem and identify the top research questions they need answered to formulate their strategy.

**Output files:**
- `research-needs/pragmatist-questions.md`
- `research-needs/innovation-questions.md`
- `research-needs/research-questions.md`
- `research-needs/reuse-adapt-questions.md`

### Phase 2: Independent Research
For each of the 4 strategists, a dedicated researcher agent investigates only that strategist's questions. Research remains isolated—each strategist only sees their own findings.

**Output files:**
- `research-results/pragmatist-research.md`
- `research-results/innovation-research.md`
- `research-results/research-research.md`
- `research-results/reuse-adapt-research.md`

### Phase 3: Strategy Proposals
Each strategist analyzes their research and proposes a complete implementation strategy, including:
- Their strategic lens and priorities
- How research informs their approach
- Complete implementation strategy
- Why this approach is superior
- Key trade-offs being made
- Specific research findings that support the position

**Output files:**
- `proposals/pragmatist-proposal.md`
- `proposals/innovation-proposal.md`
- `proposals/research-proposal.md`
- `proposals/reuse-adapt-proposal.md`

### Phase 4: Socratic Deliberation
Coordinator facilitates 3+ debate rounds:

1. **Coordinator Analysis** (`debate-plan.md`): Identifies tensions, conflicts, and key areas of disagreement
2. **Debate Rounds**: Coordinator asks Socratic questions challenging assumptions and forcing deeper thinking
3. **Strategist Responses**: Each strategist responds to challenges with substantive reasoning
4. **Synthesis Preparation** (`deliberation/coordinator-analysis.md`): Reviews which arguments held up

**Output files:**
- `deliberation/round-1-questions.md`, `round-1-responses.md`
- `deliberation/round-2-questions.md`, `round-2-responses.md`
- `deliberation/round-3-questions.md`, `round-3-responses.md`
- `deliberation/coordinator-analysis.md`

### Phase 5: Final Synthesis
Coordinator synthesizes all findings into a final recommendation (`RECOMMENDATION.md`):

- **Recommended Approach**: Clear, concise statement
- **Why This Approach**: 3-4 compelling reasons from deliberation
- **Key Trade-offs Accepted**: What we're giving up and why
- **Approaches Considered**: Brief summary of alternatives
- **Critical Success Factors**: 2-3 things that must go right
- **Research Insights Applied**: How findings shaped the decision
- **Debate Insights**: Key turning points or revelations

## Key Design Principles

### Independence Until Deliberation
Each strategist's research is conducted independently with no cross-contamination. All perspectives only merge during the deliberation phase, ensuring truly distinct approaches emerge.

### Socratic Rigor
The coordinator uses Socratic questioning to probe assumptions, not advocacy. Questions challenge each strategist and sometimes come from other strategists' perspectives.

### Real Trade-offs
The process surfaces genuine tensions and trade-offs rather than premature convergence on a single approach.

### Evidence-Based
Every recommendation is grounded in research findings and deliberation outcomes, not intuition.

## Success Criteria

A successful analysis demonstrates:

- ✅ Each strategist asked role-specific research questions
- ✅ Research remained isolated until Phase 4
- ✅ Coordinator identified genuine tensions and conflicts
- ✅ Questions forced agents to reconsider or defend positions
- ✅ Multiple truly distinct approaches emerged
- ✅ Real tensions and trade-offs surfaced in deliberation
- ✅ At least one agent evolved their position
- ✅ Final recommendation better than any single agent's initial proposal
- ✅ Decision rationale is clear and well-supported

## Example Usage

```
Problem: "Should we migrate our monolithic backend to microservices?"

/thinktank:debate

# You'll be prompted to:
# 1. Confirm the debate topic
# 2. Select which strategist roles to activate
# 3. Optionally add custom roles
#
# Then the system will:
# 1. Dispatch selected strategists to identify research questions
# 2. Research independently for each perspective
# 3. Generate proposals from each perspective
# 4. Debate through Socratic questioning
# 5. Produce final recommendation with full reasoning
```

## Output Structure

The command generates an organized directory structure with:

```
research-needs/         # Initial research questions from each strategist
research-results/       # Independent research for each strategist
proposals/              # Strategy proposals from each strategist
deliberation/           # Debate rounds and analysis
RECOMMENDATION.md       # Final recommendation
```

## When to Use

Use the `/debate` command when:

- **Complex technical decisions** need rigorous analysis
- **Multiple valid approaches** could work
- **Trade-offs are significant** and need thorough exploration
- **Stakeholders** have different perspectives
- **Implementation strategy** will affect long-term architecture
- **You want evidence-based recommendations** with clear reasoning

## Tools Used

The plugin uses:
- **Task tool** for agent dispatching
- **Write/Edit** for document generation
- **Read** for context review
- **WebFetch/WebSearch** for research (via researcher agent)
- **AskUserQuestion** for clarifications

## Configuration

No special configuration required. The plugin works out-of-the-box with:
- Haiku model for fast research
- Sonnet model for strategic thinking and debate
- Standard Claude Code tools

## License

MIT
