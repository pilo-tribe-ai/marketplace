---
description: Lens-driven Socratic exploration of product requirements — pick a lens (personas, journeys, scope...) or get guided to the next one in logical order
argument-hint: "[lens]"
model: opus
agent: prd-analyst
allowed-tools: AskUserQuestion, Read, Write, Edit, Grep, Glob
---

# Explore — Lens-Driven Product Discovery

Explore one product lens at a time through Socratic questioning. The lens order follows product-discovery practice: understand the problem, then the people, then their journeys, then the solution, then its boundaries, then how to measure it.

## Before anything

Read both shared specifications:

1. `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` — PRD format, lens catalog, prerequisites
2. `${CLAUDE_SKILL_DIR}/../shared/product-hat.md` — the product-level guardrail

**The product hat is always on.** Apply the deflection procedure whenever the conversation drifts into implementation.

## Step 1: Locate or bootstrap the PRD

1. Read `docs/product/prd.md`.
2. **If it does not exist**: check for legacy `docs/prd/*.md` files. If found, run the legacy migration procedure from `prd-schema.md`. If not found, bootstrap:
   - Ask for the product name and a one-line description (one AskUserQuestion, free text via "Other" is fine).
   - Write the skeleton: frontmatter with all lenses `not-started`, the title, and the one-paragraph summary.
3. Parse the frontmatter to learn which lenses are covered.

## Step 2: Pick the lens

### If an argument was given

`{{lens}}` names the lens (e.g., `personas`, `journeys`, `scope`). Match it to the lens catalog. Unknown name → show the menu instead.

### If no argument was given

First ask what the goal of this session is, then offer the lenses that fit. Use AskUserQuestion:

- **Recommend** the first spine lens that is not `complete` — that is the logical next step. Put it first, marked "(Recommended)".
- List other available lenses: spine lenses whose prerequisites are met, and satellites whose prerequisites are met.
- Mark covered lenses as done in the descriptions so the user sees progress.
- Briefly state the order logic in the question (e.g., "Journeys need Personas first").

### The soft gate

If the chosen lens has an unmet prerequisite:

1. Say which prerequisite is missing and why the order matters (e.g., "Journeys describe how a persona moves through the product — without personas there is no one to walk the journey").
2. Recommend exploring the prerequisite first.
3. If the user overrides: run a **minimal bootstrap** — capture just enough of the prerequisite inline (e.g., name the personas in one question) and record it as `in-progress`, so the chosen lens has something to attach to. Then proceed.

## Step 3: Explore through Socratic questioning

Apply the Socratic method from your agent definition (one question at a time, options with meaningful differences, build on answers, challenge gently). Track coverage inside the lens; stop at diminishing returns.

Use the lens guide below. The bullets are the ground the lens must cover — not a fixed script. Derive concrete options from the user's earlier answers and the existing PRD content.

### Lens guides

#### Problem — frame the opportunity
*Grounding: problem framing, Amazon working-backwards*
- What problem exists, in one sentence a customer would say?
- Who feels this problem, and how much does it cost them (time, money, frustration)?
- How do they cope today — tools, workarounds, doing nothing?
- Why is now the right time to solve it?
- How large is the opportunity?
- **Done when**: a sharp problem statement, the cost of the problem, current alternatives, and the "why now" are captured.

#### Personas — know the people
*Grounding: personas, jobs-to-be-done*
- Which user segments exist, and which one is primary?
- For each persona: role, goals, and the jobs they are trying to get done?
- What are their biggest pain points with current alternatives?
- What criteria drive their choice of a solution?
- What constraints do they operate under (budget, time, skills, organization)?
- **Done when**: each persona has a name, goals, jobs-to-be-done, pains, and decision criteria.

#### Journeys — walk each persona's path
*Grounding: journey mapping*
- Pick one persona at a time. What triggers their journey?
- What steps do they take today, and where does each step hurt?
- What should the future journey look like with the product?
- Which moments matter most (first impression, moment of value, moment of truth)?
- How does the persona know they succeeded at the end?
- **Done when**: each primary persona has a current-state pain map and a future-state journey with its key moments.

#### Capabilities — define what the product does
*Grounding: Kano model (must-be vs. delighter), user-story thinking*
- Which capabilities remove the worst journey pains? (Trace each to a journey or persona.)
- For each capability: what must the product do — behavior, not construction?
- Which are must-haves and which are delighters?
- How do capabilities work together in a flow?
- What should happen in unusual situations — at the level of user-visible behavior?
- **Done when**: each capability has a behavior description traced to the pain it removes.

#### Scope — draw the boundary
*Grounding: MoSCoW, walking skeleton / MVP*
- What is the smallest set of capabilities that delivers the core value end to end?
- For each capability: Must / Should / Could / Won't for the first release?
- What are the explicit non-goals?
- What phases follow the first release, in one line each?
- What criteria gate the first release?
- **Done when**: an MVP boundary, a non-goals list, and a rough phase sketch exist.

#### Success Metrics — define what good looks like
*Grounding: North Star metric, counter-metrics*
- What single metric best captures the value delivered (North Star)?
- Which metric per goal shows progress (acquisition, activation, retention, revenue)?
- Which counter-metrics guard against gaming the primary ones?
- What targets and timelines make these measurable?
- **Done when**: a North Star, supporting KPIs with targets, and counter-metrics are captured.

#### Business Model (satellite)
*Grounding: lean canvas*
- What is the value proposition, in the customer's words?
- How does the product earn money — model, tiers, value metric?
- What would customers pay, and compared to what alternative?
- How is the product positioned against competitors?
- **Done when**: value proposition, pricing model, and positioning are captured.

#### Go-to-Market (satellite)
- Who gets the product first, and why them?
- Through which channels do they discover it?
- What is the core message per persona?
- What does activation look like for a new user?
- **Done when**: launch audience, channels, and messaging are captured.

#### Risks & Assumptions (satellite)
*Grounding: riskiest-assumption testing*
- Which assumptions, if wrong, kill the product?
- Classify each: do people want it (desirability)? does the business work (viability)? can users use it (usability)?
- How can the riskiest ones be tested cheaply?
- **Done when**: ranked assumptions with a validation idea for the riskiest ones.

## Step 4: Close the session

Stop when the lens's "done when" is met, or at diminishing returns, or when the user signals to stop.

Summarize the findings of this session in a few bullets, then:

**Recommend**: "Run `/prd:save` to write these findings into `docs/product/prd.md` under the [Lens] section. After that, the next lens in order is [next lens]."

If the spine is complete (all six lenses), also mention: "The PRD is ready for planning — run `/prd:plan` to build the roadmap."
