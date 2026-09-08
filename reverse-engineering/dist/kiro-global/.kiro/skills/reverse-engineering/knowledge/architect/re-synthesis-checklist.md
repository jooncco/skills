# Reverse Engineering Synthesis Checklist

(Excerpt of `architecture-guide.md` § "Reverse Engineering Synthesis Checklist"
from the AI-DLC architect knowledge.)

When receiving code scan results from the Developer:

1. Identify the dominant architectural style (or lack thereof)
2. Map discovered components to bounded contexts
3. Trace data flow paths (request entry to persistence)
4. Flag coupling hotspots (high fan-in/fan-out modules)
5. Identify missing boundaries (God classes, shared state)
6. Assess test coverage alignment with architectural risk
7. Document observed patterns vs. intended patterns
8. Produce a component inventory with health ratings (healthy/at-risk/degraded)

## Artifact-to-evidence mapping

| Artifact | Primary evidence in the developer handoff | Perspective |
|---|---|---|
| business-overview.md | Packages Found (purpose column), Handoff Summary | What the system is for; the domain and its key capabilities in business terms |
| architecture.md | Build Dependencies, APIs Discovered, checklist items 1-5 | Style, component relationships (Mermaid), data flow, and Interaction Diagrams for the main business transactions |
| code-structure.md | Packages Found, file classification (code-analysis-guide) | How the source is organized and which conventions/patterns recur |
| api-documentation.md | APIs Discovered, endpoint inventory (code-analysis-guide) | Every external and internal surface: method, path, contract, auth, middleware |
| component-inventory.md | Packages Found, Build Dependencies | One entry per component: responsibility, dependencies, health rating; headings are the names the scope block cites verbatim |
| technology-stack.md | Frameworks & Libraries, Build System | Languages, runtimes, frameworks, libraries with versions |
| dependencies.md | Build Dependencies, dependency graph extraction | External packages and internal cross-package edges; circular references flagged |
| code-quality-assessment.md | Test Coverage, Code Quality Indicators, Technical Debt Signals | Tests, linting, CI/CD, docs quality, tech debt with locations |
| reverse-engineering-timestamp.md | Scan Coverage, minted fingerprint | Freshness marker + machine-read Scope of Analysis block |
