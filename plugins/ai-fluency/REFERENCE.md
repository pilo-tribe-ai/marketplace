# AI Fluency Framework — Reference

**Build material, not a runtime artifact.** This is the research base we author
the skills *from* — Delegation, and the Description / Discernment / Diligence
skills to follow. Keep it updated as we research each competency, and don't
link it from a skill body: a skill that tells Claude to read framework theory
mid-task is paying context for something that doesn't change what it does.
Skills should encode the framework's conclusions as procedure instead.

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

## Delegation — detail (skill already built)

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

## Open questions for Description / Discernment / Diligence skills

Not yet researched in depth — capture findings here when we build each:

- **Description**: likely maps to prompt/context engineering practice —
  check whether the course's rubric differs meaningfully from generic
  prompting advice.
- **Discernment**: check whether the framework provides concrete
  verification/evaluation criteria beyond "assess usefulness," and whether
  it connects to Diligence's responsibility framing.
- **Diligence**: check for overlap with Anthropic's usage policies /
  responsible-scaling framing vs. a narrower "own your outputs" framing.

## Sourcing caveats

Skilljar lesson bodies are login-gated, so exact lesson wording (e.g. the
Lesson 4 worksheet criteria) comes from third-party reconstructions, not
Anthropic's own text. The 4 D's table above and the sub-competency
definitions are from the official CC-licensed PDF and are safe to quote
directly with attribution.
