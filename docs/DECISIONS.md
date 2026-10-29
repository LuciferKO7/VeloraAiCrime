# Architectural and Implementation Decisions

This log records deviations, calibrated thresholds, benchmark findings, and technical decisions made during the build.

---

## Decision Entry Template

```markdown
## YYYY-MM-DD HH:MM — [A|B|C] — <title>

* **Context**: <background situation and problem statement>
* **Options tried (with measured numbers)**: <options explored and test outcomes>
* **Decision**: <concrete choice made>
* **Consequence/affected people**: <impact on teammates, interfaces, or deadlines>
```

---

## Initial Entries

## 2026-10-28 21:30 — [C] — Four-Shell Architecture Consolidation

* **Context**: Master Prompt §13 specifies 14 distinct steps for Person C (Landing, Auth, Cases, Witnesses, Session Intake, Interview, Recognition Loop, Edits/Transforms, Finalize/Export, Audit, Glossary/Learning, Scene, Consensus, and Witness Mode). Building isolated, disjoint full-page screens within the accelerated time constraint introduces navigation disconnect, state fragmentation, and high risk of user drop-off during time-boxed demonstrations.
* **Options tried (with measured numbers)**:
  - *Option 1*: 14 separate isolated page routes with full page transitions. Result: High navigation friction, duplicated shell boilerplate, broken session state across pages, estimated +6 hours of redundant layout plumbing.
  - *Option 2*: Four Consolidated Shells (Landing, Command Center, Studio, Trust Center) rendering secondary views via persistent tabs, drawers, and context sheets while preserving all frozen route paths (`/`, `/cases`, `/studio`, `/trust`, `/audit`, `/scenes`, etc.). Result: Instant view switching, unified state preservation, streamlined investigative narrative covering all five core demo moments.
* **Decision**: Adopt the Four-Shell Architecture:
  1. `Landing Shell` (`/`): Public narrative, ethical commitments, system health, entry point.
  2. `Command Center Shell` (`/cases`, `/dashboard`): Case registry, witness roster, session intake, purpose authorization.
  3. `Studio Shell` (`/studio`, `/interview`, `/session/:id`): Core recognition loop (Describe → Recognize → Refine → Finalize), with Vela companion and live API integration.
  4. `Trust Center Shell` (`/trust`, `/audit`, `/governance`): Tamper-evident hash chain verification, AI-assumed inspection, and privacy router monitoring.
* **Consequence/affected people**: Fully preserves all frozen API contracts and route paths. Person A and Person B backend contracts remain untouched. Delivers an end-to-end demonstrable workflow under the time budget.
