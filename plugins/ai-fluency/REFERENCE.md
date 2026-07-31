# AI Fluency Framework — Reference

**Build material, not a runtime artifact.** This is the research base we author
the skills *from* — Delegation, Description, Discernment, and Diligence.
Keep it updated as the framework or our understanding of it changes, and
don't link it from a skill body: a skill that tells Claude to read framework
theory mid-task is paying context for something that doesn't change what it
does. Skills should encode the framework's conclusions as procedure instead.

**Contents:** [Provenance](#provenance) · [The 4 D's](#the-4-ds-verbatim-official-pdf) ·
[Three modes of AI interaction](#three-modes-of-ai-interaction) ·
[Delegation — detail](#delegation--detail) ·
[Description — detail](#description--detail) ·
[Discernment — detail](#discernment--detail) ·
[Diligence — detail](#diligence--detail) ·
[Sourcing caveats](#sourcing-caveats)

## Provenance

The framework is co-authored, not an Anthropic-only artifact:

> Copyright 2025 Rick Dakan, Joseph Feller, and Anthropic. Released under the
> CC BY-NC-SA 4.0 license.

Source: [official framework PDF](https://www-cdn.anthropic.com/b383cf6baddbfc72fdf8b0ed533a518e2872d531.pdf)

**License note:** CC BY-NC-SA 4.0 requires attribution, is non-commercial, and
share-alike. Direct verbatim quoting of course/lesson content should stay
limited and attributed (as below); skill *instructions* we write are our own
operational interpretation, not reproductions of the course text.

Canonical sources:
- Course hub: https://www.anthropic.com/learn/claude-for-you
- Course (login-gated): https://anthropic.skilljar.com/ai-fluency-framework-foundations
- Open framework site: https://aifluencyframework.org/
- Practical summary/rubric: https://ringling.libguides.com/ai/framework
- Coursera mirror: https://www.coursera.org/learn/ai-fluency-framework-foundations
- Explainer: https://www.theneuron.ai/explainer-articles/inside-anthropics-ai-fluency-masterclass-on-human-ai-collaboration/
- Anthropic Education Report — AI Fluency Index (Feb 2026): https://www.anthropic.com/research/AI-fluency-index
- Prior-art Claude Code skill (4D self-assessment): https://github.com/n-pillai/ai-fluency-assessment-skill
- Diligence one-pager (Anthropic CDN; a second, identical mirror also exists — same document, not independent corroboration): https://www-cdn.anthropic.com/97ccae9e659f590c192de721eff980ba7549535b.pdf

## The 4 D's (verbatim, official PDF)

AI Fluency is "interacting with AI systems in ways that are effective,
efficient, ethical and safe." The competencies are "interconnected
collections of skills, knowledge, insights, values."

| Competency | Official definition |
|---|---|
| **Delegation** | Setting goals and deciding whether, when and how to engage with AI. |
| **Description** | Effectively describing goals to prompt useful AI behaviors and outputs. |
| **Discernment** | Accurately assessing the usefulness of AI outputs and behaviors. |
| **Diligence** | Taking responsibility for what we do with AI and how we do it. |

## Three modes of AI interaction

Load-bearing vocabulary used across all four competencies, not just
Delegation:

- **Automation** — "AI executes specific tasks based on human instruction"
- **Augmentation** — "Humans and AI collaborate as thinking partner"
- **Agency** — "Humans configure AI to independently perform future tasks on their behalf"

## Delegation — detail

Three official sub-competencies (Anthropic course calls the first one
"Problem Awareness"; the academic paper calls it "Goal and Task Awareness" —
same content):

1. **Problem / Goal Awareness** — envision the goal; deconstruct the task
   into AI, human, and collaborative components.
2. **Platform Awareness** — understand the capabilities/limitations of the
   specific AI tool in play (knowledge cutoffs, hallucination modes, cost,
   operational/regulatory constraints) *before* deciding what to delegate.
3. **Task Delegation** — actually assign pieces of the work using the three
   modes above, balancing AI and human capabilities through the project.

**Design-critical findings:**
- Mode selection happens **per component of the workflow, not once per
  task**. Most real tasks mix automation, augmentation, and human-only
  pieces.
- **Over-delegation, not under-delegation, is the characteristic failure
  mode** across every source (official framework and the prior-art
  assessment skill both call this out explicitly). A delegation process that
  only asks "what can AI do here?" will systematically over-assign — "keep
  critical judgment exclusively human" needs its own explicit checkpoint.
- Prior-art rubric (n-pillai/ai-fluency-assessment-skill) frames Delegation
  as: "the ability to identify which tasks benefit from AI assistance and
  calibrate the scope of that assistance appropriately," tracked via two
  indicators — appropriate task delegation, and scope calibration (not
  over-delegating).

## Description — detail

Three official sub-competencies (name and split confirmed independently by
the Ringling libguide rubric and The Neuron's explainer; not found on
aifluencyframework.org itself, which only carries the one-line definition):

1. **Product Description** — define the desired output itself: format, style,
   tone, length, audience, explicit success criteria. The "what."
2. **Process Description** — direct how the AI should get there: dialogic,
   iterative prompting; breaking a task into smaller sequential steps;
   "think step-by-step" style reasoning direction. The "how."
3. **Performance Description** — set the terms of the interaction itself: the
   AI's behavioral role (supportive brainstorming partner vs. critical
   devil's-advocate vs. concise analyst), when it should ask before guessing,
   how it should push back. The "how we work together."

**Design-critical findings:**
- The framework explicitly frames Description as a loop, not a one-shot
  instruction: the "Description-Discernment loop" — you describe, the AI
  produces, you assess and re-describe. Quality of collaboration tracks the
  clarity *and revision* of communication, not the cleverness of a single
  upfront prompt. This differs from generic prompt-engineering advice two
  ways: (a) it frames Description as an iterative loop, not a one-shot
  artifact to get right the first time; (b) it treats Performance as an
  explicit step, which generic advice — covering Product and sometimes
  Process — almost never does.
- **Performance Description is the systematically neglected sub-part, not
  Product Description** — the Description analogue of Delegation's
  "over-delegation is the failure mode." Per the AI Fluency Index (Feb 2026,
  as reconstructed in the prior-art skill's own reference material): most
  users already iterate/refine and clarify goals, and many specify output
  format — but only a minority ever set explicit interaction terms or
  constraints (i.e., Performance Description).
- Prior-art rubric (n-pillai/ai-fluency-assessment-skill) frames Description
  as "communicating effectively with AI ... specify goals, constraints,
  format, tone, and examples clearly ... don't rely on the AI to guess
  intent; invest in precise setup and iterate deliberately." Its top tier
  describes Description becoming *systemic* — persistent instruction layers
  (CLAUDE.md, SKILL.md files), conventional prompt formats, cross-session
  context preservation — rather than re-specified per prompt. High
  Description fluency looks like building the kind of skill/instruction
  infrastructure this plugin itself is, not writing better one-off prompts.

## Discernment — detail

Three official sub-competencies (course terminology cheat sheet; the lesson
distinguishes them by *what's being judged* — the output, the AI's reasoning,
or the interaction itself):

1. **Product Discernment** — judge the output itself: accuracy,
   appropriateness, coherence, relevance, and whether it meets requirements
   and adds real value.
2. **Process Discernment** — judge how the AI arrived at the output: logical
   errors, attention lapses, fixation on one interpretation, circular
   reasoning, or losing track of earlier decisions (e.g. reintroducing an
   idea the user already rejected).
3. **Performance Discernment** — judge the interaction itself: whether the
   AI's communication style, verbosity, and responsiveness to feedback is
   actually working for this collaboration, independent of whether the
   output is correct.

**Design-critical findings:**
- **Uncritical acceptance of polished output is the characteristic failure
  mode** — the mirror of Delegation's over-delegation finding. Anthropic's
  Feb 2026 AI Fluency Index found that when output looks finished, users
  fact-check, question reasoning, and identify missing context measurably
  less often (the prior-art rubric, n-pillai/ai-fluency-assessment-skill,
  calls this "artifact passivity"). Finished-looking work needs its own
  explicit checkpoint, not less scrutiny.
- **Discernment isn't complete at evaluation.** The official lesson treats
  "found a problem but didn't act on it" as incomplete Discernment. A defect
  routes to specific corrective feedback, a revised Description, or — if the
  tool or approach itself is wrong — back to Delegation.
- **Discernment and Diligence share activities but split on purpose.**
  Fact-checking and bias-checking show up in both. Discernment is
  evaluative/diagnostic ("is this good, what's wrong with it");
  Diligence is normative/accountable ("am I responsible for using or
  sharing this"). The same fact-check is Discernment when judging quality
  and Diligence when it's the basis for shipping or vouching for the result
  — Diligence's own skill should own "verify before you ship," not
  duplicate Discernment's quality checks.
- Prior-art rubric (n-pillai/ai-fluency-assessment-skill) collapses the three
  official sub-competencies into one aggregate score, tracked via
  behavioral indicators: identifying missing context, fact-checking,
  questioning reasoning, catching errors, pushback/requesting revision, and
  direct-use-vs-edited. Lowest rating is "accepts outputs at face value";
  highest is "questions AI logic even on polished outputs."

## Diligence — detail

Three official sub-competencies (Anthropic's dedicated Diligence one-pager,
corroborated independently by the Ringling libguide rubric with consistent
though not identical wording; aifluencyframework.org itself, same pattern
already found for Description, carries only the one-line top-level
definition, not the breakdown):

1. **Creation Diligence** — thoughtful, responsible use of the AI tools
   themselves: ethical and legal practice, awareness of bias and flaws, and
   downstream stakeholder impact, applied during the work rather than after.
2. **Transparency Diligence** — honesty about AI's role in the work, to
   whoever needs to know it was used.
3. **Deployment Diligence** — verifying and vouching for outputs before
   they're used or shared: fact-checking, testing, validating claims.

**Design-critical findings:**
- **No source maps Diligence onto Automation/Augmentation/Agency** the way
  Delegation and Description both do — don't force that analogy into the
  skill; the framework's own material never makes the connection for this D.
- **No source names a Diligence-specific failure mode**, unlike Delegation's
  named "over-delegation" or Description's "under-specification." The
  closest the framework gets is its own caveat: "different contexts
  (personal, academic, professional) may have different expectations for
  disclosure and verification" (Diligence one-pager) — Diligence's bar
  moves with context, it isn't one fixed threshold.
- **Diligence and Discernment split on purpose, not on activity** — see the
  Discernment-detail finding above. The same fact-checking and bias-checking
  shows up under both; Deployment Diligence owns "verify before you ship" as
  accountability, not a duplicate of Discernment's quality pass.
- **The prior-art rubric (n-pillai/ai-fluency-assessment-skill) operationalizes
  Diligence much more narrowly than the official framework** — its five
  tiers (Developing → Practitioner → Advanced → Expert → Exceptional) are
  built almost entirely around data-sensitivity/privacy/secrets handling,
  not the official Creation/Transparency/Deployment split. Treat this as one
  narrow, security-flavored lens on Diligence, not a restatement of it.
- The rubric's top tier is systemic again, the same pattern already found
  for Delegation and Description: "Exceptional" is "infrastructure-level —
  pre-commit hooks, repo visibility controls, documented privacy rules,
  automated compliance enforcement," not more careful manual practice. High
  Diligence fluency looks like enforcement built into the environment, not
  vigilance applied per task.
- No usage-prevalence stats exist for Diligence in any source checked — the
  AI Fluency Index report (Feb 2026) doesn't name Diligence as a scored
  category at all, and explicitly flags behaviors like "being honest about
  AI's role" and "considering the consequences of sharing AI-generated
  output" as ones it structurally cannot observe from chat-interface data.
  That's an acknowledged measurement gap, not evidence about actual
  behavior — don't cite it as if it were.
- **Illustrative worked example, not framework material:** the Ringling
  libguide's own AI Fluency page models Transparency Diligence in its own
  footer, disclosing "we maintain full responsibility for the content, its
  accuracy, and its presentation" regarding its use of Claude to help
  produce the page.

## Sourcing caveats

Skilljar lesson bodies are login-gated, so exact lesson wording (e.g. the
Lesson 4 worksheet criteria) comes from third-party reconstructions, not
Anthropic's own text.
