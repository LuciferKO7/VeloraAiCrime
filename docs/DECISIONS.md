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

## 2026-10-28 21:15 — A — Visual Quality Approval for Candidate 2 Stack (Gate TA0.4)

* **Context**: Gate TA0.4 required human inspection and explicit approval of candidate portrait quality. Candidate 2 (`SG161222/Realistic_Vision_V5.1_noVAE` + `stabilityai/sd-vae-ft-mse` + `latent-consistency/lcm-lora-sdv1-5` at 512×512, 3 steps, guidance 1.5) underwent tuning iterations (V1, V2, V3, and V3.1) to resolve prompt truncation and latency regression while preserving clothing coverage and neutral framing.
* **Options tried (with measured numbers)**:
  - V2 Baseline: Median latency 2.876s, Peak VRAM 619.8 MiB. 100% clothing coverage, good quality, but slight contrast artifacts.
  - V3: Median latency 3.838s (FAIL $\le 3.0$s), 80-token CLIP overflow, clothing instruction truncated, causing bare-shoulder regression in Row 4 and text artifact in Row 2.
  - V3.1 Corrected: Median latency 2.836s (PASS $\le 3.0$s), Peak VRAM 619.8 MiB (PASS $< 3276.3$ MiB). Positive prompts 50–55 tokens, negative 68 tokens. 100% clothing coverage compliant, clean studio background, natural matte skin texture, zero text/lighting artifacts.
* **Decision**: Explicit human approval granted for the V3.1 contact sheet (`contact_sheet_realistic_vision_v3_1.png`) for Gate TA0.4, limited to synthetic-portrait visual quality. Candidate 2 is selected as the primary visual generation stack.
* **Consequence/affected people**: Unblocks visual quality prerequisite for Step A0. Gate TA0.4 satisfied. Step A0 milestone closure authorized. Step A1 remains NOT STARTED pending separate authorization. No shared contracts or other service boundaries affected.
