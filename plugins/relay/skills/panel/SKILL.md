---
name: panel
description: Use to resolve a single decision through a fixed three-mandate quorum — skeptic, pragmatist, and advocate panelists answer in parallel, a neutral synthesizer reads their verdicts and reports the majority, and a single moderator is escalated to only on a genuine split.
user-invocable: false
---

# panel

panel runs a fixed three-mandate quorum decision and synthesizes a majority verdict.

## Steps

This skill realizes the `quorum-decide` L1 shape. Drive it as follows:

1. **Frame the question.** State the single decision to resolve and the context the
   panelists need. The same framing goes to all three panelists unchanged.
2. **Dispatch the three fixed mandates in parallel.** Run the `skeptic`, `pragmatist`, and
   `advocate` panelist roles concurrently. Each is a `role` producing a `typed-output`
   verdict; they do not see one another's answers.
3. **Synthesize.** Hand the three verdicts to the neutral synthesizer `role`. The
   synthesizer reads all three, detects agreement, and reports the majority verdict with
   its supporting rationale.
4. **Escalate only on a split.** When the synthesizer reports a genuine three-way split
   with no majority, `branch` to a single moderator `role` to break the tie (§4.3). A clear
   majority never reaches the moderator.
5. **Return the verdict.** Surface the synthesized (or moderated) decision as the result.

Calm imperatives only. Describe the target form; the roles do the work.

## Vocabulary

```relay-vocab
l1-shape: quorum-decide
l0-deps: parallel, delegate, role, typed-output, branch
acpx-leg-required: false
```
