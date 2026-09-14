---
name: writing-prompts
description: Writes a new system prompt, skill, command or agent in the shape current models handle best — few outcome-shaped instructions, separate reference material, and hard rules left to code. Backs /prompt-fit:new.
---

# Writing prompts

Write a new prompt in the shape that wins in 2026, from
`${CLAUDE_PLUGIN_ROOT}/reference/principles.md`.

**Announce at start:** "I'm using the writing-prompts skill to draft this in
the 2026 shape."

## The shape

Three parts, and each part has a home:

| Part | Holds | Size |
| --- | --- | --- |
| instructions | outcomes and judgment | 11 or fewer, for a healthy band |
| reference | material the model consults and cites | as big as it needs to be |
| gates | hard content rules, personal-data handling, injection defence | code, not prose |

A 15k-token prompt that is mostly reference material is healthier than a
3k-token prompt that is 60 rules (P2).

## Before drafting

Get four answers, from the user or from the code:

1. The outcome, stated so that it can be measured. A length, a count, a format,
   or an explicit test.
2. The reader: which model, and whether it is pinned. An unpinned or small
   model keeps the scaffolding a frontier model does without (U2).
3. The reference material, and its size and rate of change.
4. The hard rules, which become gates and not prose.

Ask for a missing answer rather than assuming one. An assumed output contract
is the fault that survives longest, because nothing measures it.

## While drafting

Order the file: stable content first, long documents next, task instructions
last. A changed byte breaks the cache from that point on, so the parts that
change go at the end (P5).

Write each instruction as the result you want, with a number in it. Leave the
method to the model (P1).

Use markdown headings, or use tag-style markup. One scheme, not two (P6).

Give a reason next to every prohibition (P7).

Start with no examples. Add an example when a real failure shows one is needed,
and keep it to output format, tone, or an edge-case policy (U1).

## Where the corpus goes

| Corpus | Home |
| --- | --- |
| stable, and under about 100k tokens | in the prompt, cached (P4) |
| big, fast-changing, or different per user | retrieval |
| a skill's own material | a `reference/` file the skill names |

## Before handing it over

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prompt_lint.py" <the draft>
```

Exit code 0 means no finding. Report the instruction count and the band with
the draft, and name the model it is tuned against, because a model swap is a
breaking change (P9).
