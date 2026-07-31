# ai-fluency

Claude Code skills that operationalize the (Anthropic co-authored) [AI
Fluency framework](https://aifluencyframework.org/) — Delegation, Description,
Discernment, Diligence — as lightweight checkpoints in the natural lifecycle
of any task: start → produce → check → ship.

See [REFERENCE.md](./REFERENCE.md) for the framework's definitions, sourcing,
and design notes shared across all four skills.

## Skills

| Checkpoint | Skill | Fires when | What it adds to the reply |
|---|---|---|---|
| Start | [`delegation`](./skills/delegation/SKILL.md) | a multi-part or consequential ask | a 4-line split: I'll do / together / yours / assuming |
| Produce | [`description`](./skills/description/SKILL.md) | about to write a deliverable | 2 lines: producing / operating as |
| Check | [`discernment`](./skills/discernment/SKILL.md) | about to say done, fixed, or ready | findings only — silence means it passed |
| Ship | [`diligence`](./skills/diligence/SKILL.md) | work leaves the session | 1–2 lines: what was verified, what was disclosed |
