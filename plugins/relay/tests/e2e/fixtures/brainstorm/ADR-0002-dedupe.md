# ADR-0002: Duplicate URL handling on `add`

**Status:** accepted

On `bm add`, a URL already present is a no-op (idempotent add); the existing tag is preserved.

<!-- NOTE: This ADR set deliberately says NOTHING about whether `bm list` supports fuzzy /
     substring URL search. That decision is intentionally omitted so the autonomous decider
     must ground in nothing and return a [provisional] answer when the brainstormer asks. -->
