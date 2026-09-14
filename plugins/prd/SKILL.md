# PRD Analysis

Product-level PRD creation and roadmap planning through lens-driven Socratic exploration, with full traceability between the PRD and the roadmap.

## Features

- **Lens-Driven Exploration** - Guided discovery through an ordered lens spine: Problem → Personas → Journeys → Capabilities → Scope → Success Metrics, plus satellites (Business Model, Go-to-Market, Risks)
- **The Product Hat** - Guardrails keep every skill at the product level; implementation asks are deflected into product constraints
- **One Living PRD** - `docs/product/prd.md` with per-lens coverage frontmatter and permanent requirement IDs
- **Roadmap Generation** - `/prd:plan` slices scope (MVP, phases, full product) and drives milestone/feature/story identification
- **Traceability** - Every roadmap item carries `Trace` links (requirement ID + content hash) back to the PRD
- **Drift Detection** - When a requirement changes, the affected roadmap items get flagged `Needs Review`
- **Implementation Simulation** - Developer-perspective gap analysis with product-level decision capture
- **Roadmap Status Table** - Auto-generated progress tracking with visual progress bars
- **Roadmap Sync** - Status updates from GitHub issues/PRs, code verification, and requirement drift

## Skills

### PRD Creation

### `/prd:explore [lens]`
Lens-driven Socratic exploration. Pass a lens (`problem`, `personas`, `journeys`, `capabilities`, `scope`, `success-metrics`, `business-model`, `go-to-market`, `risks`) or get a guided menu that recommends the next lens in logical order. Bootstraps `docs/product/prd.md` on first run.

**Use when**: Discovering or deepening product requirements.

### `/prd:save [lens]`
Write the session's findings into the living PRD: updates the lens section, assigns requirement IDs, maintains coverage frontmatter, and flags drifted roadmap items.

**Use when**: An exploration or simulation session produced findings worth keeping.

### `/prd:simulate [prd-file]`
Simulate implementing the PRD from a developer's perspective. Surfaces gaps one requirement at a time; captures decisions at the product level.

**Use when**: The spine is explored and you want to stress-test the PRD.

### Roadmap Planning

### `/prd:plan [scope]`
Generate `docs/product/roadmap.md` from the PRD. Asks what to plan (MVP, next phase, full product, a specific phase), proposes slicing strategies, then drives milestone → feature → story identification for the chosen slice. Other phases stay visible as `Not Planned` placeholders.

**Use when**: The PRD is ready and you want a roadmap.

### `/prd:themes-identify [prd-file]`
Extract milestones from the PRD (granular building block of `/prd:plan`).

### `/prd:features-identify [roadmap] [milestone]`
Break a milestone into features, each traced to PRD requirements.

### `/prd:stories-identify [roadmap] [feature]`
Decompose a feature into user stories with acceptance criteria and trace links.

### `/prd:stories-estimate [roadmap] [feature]`
T-shirt sizing (S/M/L), one story at a time, with the team.

### `/prd:roadmap-sync [roadmap-file]`
Sync the status table from GitHub issues/PRs and code existence, and run the requirement drift check — flags items whose traced requirements changed.

## Conventions and Specifications

File paths (`docs/product/prd.md`, `docs/product/roadmap.md`), the lens catalog, requirement IDs, hash rules, and migration live in `skills/shared/prd-schema.md`. The product-level guardrail lives in `skills/shared/product-hat.md`; the status table format and drift rules in `skills/shared/roadmap-table-schema.md`. The full workflow narrative is in `README.md`.
