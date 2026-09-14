---
name: authoring-adrs
description: Writes one architecture decision record (ADR) the moment a decision that would be expensive to undo has just been made -- a datastore, a service or trust boundary, a wire or event contract, a deployment topology, a public interface others consume. Writes the ADR with status proposed and keeps working; it never stops to ask. Use for "/adr:new", "write an ADR", "record this decision", "document this architecture decision", and fires on its own during a session the moment a decision that is expensive to undo is made.
argument-hint: "[decision]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

# authoring-adrs

Write one ADR. Capture the decision now, then keep working on whatever the session was already
doing. Do not stop to ask.

## The bar

Record a decision when undoing it later would be expensive. Cheap to change your mind, no ADR.

| Earns an ADR | Does not |
|---|---|
| Chose Postgres over DynamoDB | Picked a retry count of 3 |
| Put auth at the gateway, not per service | Named a helper function |
| An event shape other services now consume | Chose a lodash utility |

Two rejected bars, recorded so they are not re-litigated:

- **"Escapes its module."** This bar misses expensive local choices, such as a storage engine
  inside one service. A decision does not have to cross a module boundary to be expensive to undo.
- **"Alternatives were weighed."** This bar fires constantly, because sessions weigh options all
  the time. Weighing options is not the test. The cost of reversing the choice is the test.

## When this fires on its own

The moment you make a decision that is expensive to undo -- a datastore, a service or trust
boundary, a wire or event contract, a deployment topology, a public interface others consume --
write the ADR and keep working. Do not stop to ask.

`status: proposed` is the safety valve. It is not a request for permission. The human accepts or
deletes the draft later, when reading the diff. Asking mid-session was rejected on purpose: it
breaks flow, and in a long or unattended session nobody is there to answer, so the decision gets
lost anyway.

## Write it

From the repository root:

```bash
python3 scripts/adr/adr_new.py --title "<title>" [--area <area>] [--supersedes <filename>]
```

This allocates the next identity, writes frontmatter with `status: proposed`, and prints the new
file's path. Open that file and fill in the five sections: Context, Decision, Why, Alternatives
considered, Consequences.

**The filename is the identity.** Never write an `id` field into the frontmatter -- there is no
such field. A number in frontmatter can drift from the filename that carries it, and nothing
detects that drift. Cross-references (`supersedes`, `superseded_by`, `related`) hold filenames,
never numbers.

## Then

Run both gates and report their output:

```bash
python3 scripts/adr/adr_index.py --write
python3 scripts/adr/adr_lint.py
```

Report the lint output plainly. Never claim the ADR is recorded while the lint is red.

## Style

Read `${CLAUDE_PLUGIN_ROOT}/skills/authoring-adrs/distillation.md` and apply it. An ADR is a
distillation, not a design journal: write the decision as it stands, and when you learn more
later, rewrite in place instead of appending.
