# The distillation standard

An ADR is a distillation, not a design journal. Write the decision as it stands today. When new
learning arrives, rewrite the ADR in place. Never append. Git holds the history — you do not need
to keep it in the document too.

## Four tells that an edit appended instead of rewrote

Check every edit against these four tells before you save it.

1. **A clause dating the document against an earlier state of itself.** Phrases like "since landed",
   "the original draft", or "after the first cut" are the tell. Delete the clause and state the
   current fact plainly.
2. **A struck-through open question, annotated as resolved.** An item is open, or it is deleted.
   There is no middle state. Remove the question; if it changed the decision, fold that into the
   Decision section.
3. **A sentence justifying why something was kept in the document, rather than what it decides.**
   If a sentence explains "we kept this section because...", cut the sentence. Say what the
   decision is, not why the document still says it.
4. **An `## Update (date):` block stacked above or below the decision.** There is no such heading
   in an ADR. Fold what the block says into Context, Decision, Why, Alternatives considered, or
   Consequences, and delete the block.

## The rule in one line

Write the decision as it stands. When learning arrives, rewrite in place — never append.
