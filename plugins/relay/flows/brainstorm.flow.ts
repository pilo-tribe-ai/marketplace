// Production acpx flow: drives the unmodified superpowers:brainstorming skill headless to a
// written spec, with a context-grounded decide node standing in for the user. Expressed with the
// acpx >=0.7.0 decision()/decisionEdge() sugar; routing semantics proven end-to-end (job c136182f
// on acpx 0.8.0/0.10.0). Reads context-doc PATHS via an in-flow read_context compute node. [inferred]
import {
  acp,
  compute,
  action,
  decision,
  decisionEdge,
  defineFlow,
} from "acpx/flows";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

type Input = {
  task: string;
  brainstorm_context_paths: string[];
  guidelines: string;
  specDir: string; // absolute dir where obra must write the spec
  today: string; // YYYY-MM-DD for the filename convention
};

const BRAINSTORMER = { handle: "brainstormer" }; // warm session reused across turns
const MAX_ROUNDS = 6;
const MAX_WRITE_ATTEMPTS = 3;

export default defineFlow({
  name: "autonomous-brainstorm",
  startAt: "read_context",
  nodes: {
    // ---- read + concatenate the context docs INSIDE the flow (paths, not inline text) ----
    read_context: compute({
      run: ({ input }) => {
        const inp = input as Input;
        const parts: string[] = [];
        for (const p of inp.brainstorm_context_paths) {
          try {
            parts.push(`===== ${p} =====\n${readFileSync(p, "utf8")}`);
          } catch {
            parts.push(`===== ${p} (UNREADABLE) =====\n`);
          }
        }
        return { body: parts.join("\n\n") };
      },
    }),

    // ---- obra (UNMODIFIED superpowers:brainstorming), warm across turns ----
    brainstorm: acp({
      session: BRAINSTORMER,
      timeoutMs: 300000,
      prompt: ({ input, outputs }) => {
        const decide = outputs.decide as { answer?: string } | undefined;
        // loop re-entry: relay the grounded decider's answer as the "user" reply (no re-inject)
        if (decide && typeof decide.answer === "string" && decide.answer.trim().length) {
          return decide.answer;
        }
        const inp = input as Input;
        const ctx = (outputs.read_context as { body?: string } | undefined)?.body ?? "";
        return [
          "Use the superpowers:brainstorming skill to design the following tool.",
          "Ask your clarifying questions ONE AT A TIME in plain prose (no interactive question tool).",
          "Propose 2-3 approaches with a recommendation, then present the design.",
          "When (and only when) the design is complete and approved, you will be asked to write the spec file.",
          "",
          `Task: ${inp.task}`,
          "",
          "Context (PRD / ADRs):",
          ctx,
        ].join("\n");
      },
      parse: (text) => text, // raw prose for the decider to read
    }),

    // ---- round counter ----
    tick: compute({
      run: ({ outputs }) => {
        const prev = outputs.tick as { count?: number } | undefined;
        return { count: (prev?.count ?? 0) + 1 };
      },
    }),

    // ---- grounded decision-maker, fresh each round (decision() sugar) ----
    decide: decision({
      session: { isolated: true },
      timeoutMs: 180000,
      choices: ["answer", "approve"] as const,
      field: "route",
      question: ({ input, outputs }) => {
        const inp = input as Input;
        const ctx = (outputs.read_context as { body?: string } | undefined)?.body ?? "";
        const last = String(outputs.brainstorm ?? "");
        const round = (outputs.tick as { count?: number } | undefined)?.count ?? 1;
        return [
          "You are the DECISION-MAKER standing in for the user in an autonomous brainstorming session.",
          "Ground every decision in the context body below; never invent beyond it.",
          "",
          "=== DECISION GUIDELINES (binding) ===",
          inp.guidelines,
          "",
          "=== CONTEXT (the body — ground every decision here) ===",
          ctx,
          "",
          "=== BRAINSTORMER'S LATEST MESSAGE ===",
          last,
          "",
          `This is round ${round} of at most ${MAX_ROUNDS}.`,
          "In ADDITION to the templated `route` field, include these in the SAME JSON object:",
          '- "answer": grounded reply text when route="answer"; "" when route="approve". When provisional=true you MUST embed the literal token "[provisional]" inline in this answer text (prefix it, e.g. "[provisional] use exact substring matching") so the marker carries into the written spec.',
          '- "provisional": true if the context is silent and you chose a minimal option (YAGNI).',
          '- "cite": the exact context phrase you grounded in, or "".',
          "route=answer: the brainstormer asked a question or proposed approaches — give a concise grounded reply.",
          '  If the context is SILENT, choose the minimal option consistent with its spirit (YAGNI), set provisional=true, and prefix the answer with the literal token "[provisional]".',
          "route=approve: the brainstormer presented a COMPLETE final design consistent with the context.",
          `  If round >= ${MAX_ROUNDS} and any reasonable design has been presented, route=approve to converge.`,
        ].join("\n");
      },
      // no parse — decision() validates route ∈ choices and returns the full object,
      // so answer/cite/provisional ride through into outputs.decide.
    }),

    // ---- approval: tell the SAME warm session to write the spec file ----
    write_spec: acp({
      session: BRAINSTORMER,
      timeoutMs: 300000,
      prompt: ({ input }) => {
        const inp = input as Input;
        return [
          "Approved. Write the complete design spec now.",
          'For every decision that was marked "[provisional]" during our conversation (a minimal YAGNI default chosen where the context was silent), carry that literal "[provisional]" marker into the spec next to the decision so downstream readers know it still needs confirmation.',
          `Save it to: ${inp.specDir}/${inp.today}-<slug>-design.md`,
          "(choose a short kebab-case <slug> from the tool name).",
          "Write the actual file to disk using your file tools, then reply with ONLY the absolute path of the file you wrote — nothing else.",
        ].join("\n");
      },
      parse: (text) => text.trim(), // logging only; check_spec is the source of truth
    }),

    // ---- write-attempt counter ----
    wtick: compute({
      run: ({ outputs }) => {
        const prev = outputs.wtick as { count?: number } | undefined;
        return { count: (prev?.count ?? 0) + 1 };
      },
    }),

    // ---- DETERMINISTIC done-gate: does a real spec file exist on disk? ----
    check_spec: action({
      run: ({ input, outputs }) => {
        const inp = input as Input;
        const attempts = (outputs.wtick as { count?: number } | undefined)?.count ?? 1;
        let path = "";
        let bytes = 0;
        try {
          const hits = readdirSync(inp.specDir)
            .filter((f) => f.endsWith("-design.md"))
            .map((f) => {
              const full = join(inp.specDir, f);
              return { full, mtime: statSync(full).mtimeMs, size: statSync(full).size };
            })
            .sort((a, b) => b.mtime - a.mtime);
          if (hits.length) {
            path = hits[0].full;
            bytes = hits[0].size;
          }
        } catch {
          /* dir missing -> not found */
        }
        const found = path !== "" && bytes > 0;
        const route = found || attempts >= MAX_WRITE_ATTEMPTS ? "done" : "retry";
        return { route, found, path, bytes, attempts };
      },
    }),

    // ---- terminal node (NO outgoing edge -> status:completed) ----
    finish: compute({
      run: ({ outputs }) => {
        const cs = outputs.check_spec as
          | { found?: boolean; path?: string; bytes?: number; attempts?: number }
          | undefined;
        return {
          specPath: cs?.path ?? "",
          found: cs?.found ?? false,
          bytes: cs?.bytes ?? 0,
          writeAttempts: cs?.attempts ?? 0,
          brainstormRounds: (outputs.tick as { count?: number } | undefined)?.count ?? 0,
        };
      },
    }),
  },
  edges: [
    { from: "read_context", to: "brainstorm" },
    { from: "brainstorm", to: "tick" },
    { from: "tick", to: "decide" },
    decisionEdge({
      from: "decide",
      choices: ["answer", "approve"] as const,
      field: "route",
      cases: { answer: "brainstorm", approve: "write_spec" },
    }),
    { from: "write_spec", to: "wtick" },
    { from: "wtick", to: "check_spec" },
    decisionEdge({
      from: "check_spec",
      choices: ["retry", "done"] as const,
      field: "route",
      cases: { retry: "write_spec", done: "finish" },
    }),
    // finish has no outgoing edge -> terminal -> status: completed
  ],
});
