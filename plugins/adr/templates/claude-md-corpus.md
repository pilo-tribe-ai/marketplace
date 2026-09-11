# ADRs

One ADR records one decision that is expensive to undo.
If it is cheap to change your mind, do not write an ADR.

## Before you change an architectural boundary

Read `README.md`. It lists every ADR, one line each. Open only the ADRs that apply.

## When you decide something expensive to undo

Write the ADR now, with `status: proposed`. Do not stop to ask.
Run `/adr:new`, or write the file and then run `/adr:index`.

## When a decision changes

Rewrite the ADR in place. Do not append an update block — git holds the history.
If the decision is replaced, write a new ADR. Set `superseded_by` on the old ADR
and `supersedes` on the new one.

## Rules

- One decision per ADR.
- Record what was decided and why. Do not record how the design was explored.
- Do not edit `README.md` between the generated markers. Run `/adr:index`.
