# Prompt engineering principles

State of play, August 2026. This page is the reference material behind the
prompt-fit plugin. It comes from vendor guidance (Anthropic, OpenAI, Google,
Microsoft), from published measurements, and from a 30-day sweep of
practitioner discussion in July and August 2026.

## The shift this page records

The field inverted over the year to August 2026. All three major vendors now
say the same thing: the big, prescriptive prompts that kept older models
reliable hurt current models. The instructions that used to add reliability are
now a source of unreliability.

Anthropic deleted over 80% of the Claude Code system prompt for its
Claude-5-generation models, and lost nothing on its coding evaluations
(July 2026).

The default flipped with it. When a prompt misbehaves, the first move is to
delete instructions, not to add them.

The shape that wins now has three parts:

- a small set of instructions that describe outcomes and judgment, not
  step-by-step procedure;
- reference material the model consults, held in the prompt when it is small
  and stable, and loaded on demand when it is big;
- hard guardrails enforced in code and classifiers, not in prose.

The community calls this context engineering: the design of everything the
model sees, and not the instruction text alone.

If one line survives from this page: write a small prompt that trusts the
model, give it good reference material, enforce the hard rules in code, and run
the evaluations again every time the model changes.

## How to read this page

Each entry has an identifier. P1 to P9 are patterns to follow. L1 to L8 are
habits to leave behind. U1 and U2 are unsettled. A review cites the identifier,
so that a reader can find the entry behind a finding.

Each entry ends with two lines:

- `Check.` names the automatic check that raises the finding, or says that the
  rule is judgement only. A judgement-only rule needs a reader.
- `Confidence.` is one of three words. `measured` means a published
  measurement. `vendor` means vendor guidance, with named production cases.
  `directional` means the figure circulates without a published method.

## Reference: the rule catalogue

### P1 — Describe the outcome, not the procedure

**Rule.** State the result in measurable detail. Let the model pick the path.

**Broken.**

```text
To review the code:
1. Read every changed file.
2. Build a list of issues.
3. Sort the list by severity.
4. Write a paragraph for each issue.
5. Add a summary at the end.
```

**Fixed.**

```text
Return one paragraph per issue, 3 to 6 sentences each, ordered by severity,
followed by a summary of 2 sentences.
```

**Why.** A procedure is a chain of rules, and each link can break. An outcome
is one rule with a measurable test. The model already knows how to read files.

**Check.** none, judgement only.

**Confidence.** vendor.

### P2 — Keep rules few, and keep reference material separate

**Rule.** Hold the rulebook small. Let the corpus be big.

**Why.** Rule following collapses geometrically as rules pile up. At a per-rule
compliance of 0.98, the chance that all 40 rules hold at once is about 45%.
Reference text that the model consults and cites degrades gently with size.

A 15k-token prompt that is mostly reference material is healthier than a
3k-token prompt that is 60 rules. To judge the size of a prompt, count the
instructions, and not the tokens.

The plugin reports three bands over the instruction count, from the same
0.98 figure:

| Instructions | All-rules estimate | Band |
| --- | --- | --- |
| 0 to 11 | 80% or above | healthy |
| 12 to 25 | 60% to 79% | watch |
| 26 and above | below 60% | at-risk |

**Check.** the instruction count and the band, printed for every file.

**Confidence.** measured for the collapse math. directional for the 0.98
figure itself, which is why `--per-rule` can change it.

### P3 — Use concrete thresholds, not judgment words

**Rule.** Give a number, or an explicit test. A word that needs interpretation
gets interpreted.

**Broken.**

```text
Report only high-severity issues. Keep the summary concise.
```

**Fixed.**

```text
Report an issue when it can lose data, expose a credential, or break a
documented promise. Keep the summary to 3 sentences or fewer.
```

**Why.** Current models execute hedge words literally. A review harness told to
report only high-severity issues dropped real findings in silence. If a
teammate would have to ask what a word counts as, the model does not ask. It
guesses.

**Check.** `hedge`, raised on an instruction that holds a judgment word and no
number.

**Confidence.** vendor, with a named production case.

### P4 — Put a small, stable corpus in the prompt and cache it

**Rule.** Below roughly 100k to 200k tokens, and stable, put the corpus in the
prompt and cache it. Above that, or when it changes often, or when each user
sees a different part of it, use retrieval.

**Why.** A cached read costs about 10% of the normal input price at all three
vendors, so an in-prompt corpus beats the cost and the complexity of a
retrieval layer at this size.

**Check.** none, judgement only.

**Confidence.** directional for the 100k to 200k cutoff. The price ratio is
vendor.

### P5 — Order the prompt for caching and attention

**Rule.** Put stable content first, long documents next, and the task
instructions last.

**Why.** A changed byte breaks the cache from that point to the end, so the
parts that change go at the end. The instructions hold their force best when
they sit after the material they apply to.

**Check.** `instructions-before-reference`, raised when 5 or more instructions
sit above a reference block of 40 lines or more.

**Confidence.** vendor.

### P6 — Use one formatting scheme

**Rule.** Use markdown headings, or use tag-style markup. Use one of the two.

**Why.** Both work on every major model now. Mixing them hurts, and feeding
JSON in as an input format hurts. Formatting matters far less than the number
of instructions and where they sit, so this is a small win, not a large one.

**Check.** `mixed-format`, raised on a file with 3 or more headings and 3 or
more distinct structural tag names.

**Confidence.** vendor.

### P7 — Frame instructions positively, and give a reason for each prohibition

**Rule.** Say what to do. When a prohibition is needed, write the reason next
to it.

**Broken.**

```text
Never use ellipses.
```

**Fixed.**

```text
Never use ellipses, because a text-to-speech engine reads this text aloud.
```

**Why.** A prohibition with its reason holds up far better than a bare one.
Every never needs a because.

**Check.** `bare-prohibition`, raised on a prohibition with no reason in the
same sentence or the two blocks that follow.

**Confidence.** vendor.

### P8 — Enforce outside the prompt

**Rule.** Put hard content rules, personal-data handling, and injection defence
in classifiers and code hooks. Leave tone and topic steering to the prompt.

**Why.** Prompts steer. Systems enforce. Prompt-only defences still lose to
multi-turn attacks 70% to 100% of the time.

**Check.** `hard-rule-in-prose`, raised on prose that tries to enforce.

**Confidence.** measured.

### P9 — Version prompts, and test again on every model change

**Rule.** Treat every model swap as a breaking change. Share the durable
sections across models and surfaces: goals, definitions, output contracts, and
reference content. Hold the model-specific tuning in a separate overlay.

**Why.** Prompts do not port. One prompt measured at 99% accuracy on its home
model dropped to 69% on another.

**Check.** none, judgement only.

**Confidence.** measured.

### L1 — Leave behind: capitals and emphasis words

**Rule.** Write the instruction in plain words.

**Broken.**

```text
CRITICAL: You MUST always use this tool.
```

**Fixed.**

```text
Use this tool when the file is over 100 lines.
```

**Why.** Current models over-trigger on aggressive language. When every rule is
marked important, none of them is.

**Check.** `emphasis`.

**Confidence.** vendor.

### L2 — Leave behind: repairing behaviour by adding an instruction

**Rule.** When a prompt misbehaves, delete first. Add only after deleting has
failed.

**Why.** Additions now degrade quality. Deleting is the cheap optimisation of
2026.

**Check.** none, judgement only. The instruction count under P2 is the number
that shows this over time.

**Confidence.** vendor.

### L3 — Leave behind: expert personas

**Rule.** Delete the persona line.

**Why.** A persona changes style, and not accuracy. This is replicated on
current models. Keep a role line only when the style itself is the product.

**Check.** `persona`.

**Confidence.** measured.

### L4 — Leave behind: politeness, tips, and threats

**Rule.** Delete them, and spend the tokens on reference material.

**Why.** No reliable effect.

**Check.** `pressure`.

**Confidence.** measured.

### L5 — Leave behind: anti-laziness scaffolding

**Rule.** Delete the scaffolding that was written against an older model.

**Why.** This is the prompt content that breaks worst on a model upgrade. See
U2 before deleting it from a prompt that runs on a small or unpinned model.

**Check.** `anti-laziness`.

**Confidence.** vendor.

### L6 — Leave behind: a bigger window as room for more rules

**Rule.** Size the rulebook by the instruction count, and not by the window.

**Why.** Instruction following does not grow with window size. Reliability can
start to drop around 50k tokens into a 200k window, and it drops hardest when
the context holds material that looks like the material the task needs.

**Check.** none, judgement only.

**Confidence.** measured.

### L7 — Leave behind: prescribing the reasoning steps

**Rule.** Constrain the output. Leave the thinking alone.

**Why.** Reasoning models often do worse when a prompt dictates how to think.

**Check.** `prescribed-reasoning`.

**Confidence.** vendor.

### L8 — Leave behind: XML tags treated as a Claude-only thing

**Rule.** Pick the scheme that fits the prompt, on any vendor.

**Why.** Tag-style markup is house style in the OpenAI guides now. It is
cross-model. See P6 for the rule that matters, which is to use one scheme.

**Check.** none, judgement only.

**Confidence.** vendor.

### U1 — Unsettled: few-shot examples

**Position.** Start without examples. Add them against observed failures.

Examples that show output format, tone, or edge-case policy are safe
everywhere. Examples that teach a reasoning procedure are risky on reasoning
models. This is the one live disagreement between vendors.

**Check.** none, judgement only.

**Confidence.** vendor, and disputed between vendors.

### U2 — Unsettled: minimalism is a frontier-model luxury

**Position.** Small and older models still need the scaffolding. When a product
runs on a weak or unpinned model, delete less, and test again whenever the
platform swaps the model underneath.

**Check.** none, judgement only.

**Confidence.** directional.

## Staleness

This page is a snapshot of a fast-moving field, dated August 2026. It is meant
to be refreshed by running the research again, roughly each season, or after
any major model generation. When the date is more than about six months old,
treat the specifics as stale, and treat the shape as the part that lasts.
