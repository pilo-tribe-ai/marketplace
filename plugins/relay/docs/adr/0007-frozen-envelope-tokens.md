---
status: accepted
date: 2026-06-06
---

# Four envelope tokens are frozen and byte-pinned

`ROLE_DONE`, `BLOCKED: <reason>`, `NEEDS_DECISION: <question>`, and the capture
regex `^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$` are a public contract. Their exact byte
sequences are pinned in `test_envelope_tokens.py` and cannot change without a major
version bump.

## Context

These four are the entire boundary between free-text model output and deterministic
downstream parsing. The dispatcher scans the last 200 lines of stdout for the
envelope grammar; the watcher classifies a turn by matching the two sentinels against
its first non-empty line. Everything after that point — routing, retry, landing
verification — is ordinary code operating on parsed values, and all of it breaks
silently if a token drifts.

## Consequences

Per-role `output-tokens` remain free to vary, and `ROLE_RESULT` stays internal
driver-to-watcher plumbing. Only the four are frozen, so roles can evolve their own
vocabulary without touching the contract.

The two sentinels contain a colon and therefore deliberately do *not* match the
envelope regex; they are classified by a dedicated first-line branch. That asymmetry
is load-bearing and easy to "tidy" into a single unified matcher, which is why it is
written down here as well as in the contract doc.

`FILES_TOUCHED` is validated downstream with
`jq -e 'type == "array" and all(type == "string")'`, so a role emitting prose where
an array belongs fails loudly at the boundary rather than corrupting the coordinator's
view of what changed.
