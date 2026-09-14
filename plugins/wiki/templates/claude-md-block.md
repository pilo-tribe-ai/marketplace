## Knowledge wiki

See [AGENTS.md](./{{CONTAINER}}AGENTS.md) for the LLM Wiki schema governing `{{CONTAINER}}`.

Ingest new sources, query the wiki, and lint it by following the four
operations `AGENTS.md` defines -- do not hand-edit generated files
(`index.md` under a subdirectory, or a Source page's fed-pages list).

Run `/wiki:ingest <path-or-URL>` to add a source to the wiki.

Run `/wiki:ask <question>` to ask the wiki a question.
