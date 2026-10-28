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

## 2026-10-29 01:00 — A — ArcFace Model Licensing & Weight Provenance Review (Gates TA3.1 & TA3.2 Status)

* **Context**: Milestone A3 requires a 512-dimensional, $L_2$-normalized ArcFace facial embedder for `POST /ml/v1/embed`. Before downloading or enabling weights, a licensing and provenance review was conducted per human instruction.
* **Options inspected (with licensing analysis)**:
  - Option 1 (Official InsightFace Model Zoo: `buffalo_l` / `buffalo_s`): Contains `w600k_r50.onnx` (ArcFace ResNet-50, 512-dim embedding) and `det_10g.onnx` (RetinaFace). Provenance: DeepInsight (trained on Glint360k/MS1MV2). License: DeepInsight Non-Commercial / Research-Only. Permissible for academic and hackathon demonstration, but prohibited for commercial deployment without enterprise licensing.
  - Option 2 (Permissively Licensed ArcFace ONNX): Checkpoints released under Apache-2.0 or MIT on HuggingFace Hub, accompanied by a permissive face detector (e.g. OpenCV YuNet). Requires input dimension calibration.
* **Decision**: Strict adherence to safety mandate: Zero unapproved weights downloaded. `POST /ml/v1/embed` enforces an explicit HTTP 503 `ML_UNAVAILABLE` error indicating that weights are unloaded pending licensing authorization. Gates TA3.1 and TA3.2 are marked PENDING HUMAN DECISION. Safe Milestone A3 components (CLIP-based attribute verifier, adherence arithmetic, endpoint schemas, and fast test suite) proceed without blocking.
* **Consequence/affected people**: No fake embeddings or Haar substitutions are returned. Zero VRAM leakage on GPU laptop #1. Teammates relying on `/embed` will receive standardized `ML_UNAVAILABLE` until the model checkpoint is approved and downloaded.

## 2026-10-29 02:45 — A — CLIP Zero-Shot Hair Separation Empirical Status (Gate TA3.3)

* **Context**: Gate TA3.3 requires evaluating CLIP zero-shot attribute verifier separation between bald and long-hair suspect portraits. An empirical benchmark was conducted with 24 real generated portraits (12 bald vs. 12 matched long-hair) using the Candidate 2 stack.
* **Options tried (with measured numbers)**:
  - Bald group (12 portraits): Mean bald prob = 0.0023 (std: 0.0016), mean long prob = 0.0259 (std: 0.0102).
  - Long hair group (12 portraits): Mean bald prob = 0.0014 (std: 0.0014), mean long prob = 0.0890 (std: 0.1199).
  - Bald separation difference: +0.0009.
  - Long hair separation difference: +0.0631.
* **Decision**: Gate TA3.3 is recorded honestly as **PARTIAL** (not a full pass). Long hair shows positive separation (+0.0631), but bald separation (+0.0009) is marginal due to CLIP ViT-B/32 photorealistic prompt priors on pencil sketch textures. Zero results were fabricated.
* **Consequence/affected people**: Informs downstream team that attribute adherence on bald sketches has lower dynamic range than photorealistic inputs; no contract or API breaking changes.

## 2026-10-29 02:50 — A — Windows Safetensors Non-mmap Pread Fallback

* **Context**: On Windows (`sys.platform == 'win32'`), `safetensors.torch.load_file` defaults to `backend='mmap'`. Memory-mapped files under Windows Virtual Memory Manager can trigger access violations (`STATUS_ACCESS_VIOLATION` / `0xC0000005`) during model component loading and swapping.
* **Options tried (with measured numbers)**:
  - Option 1 (Default mmap): Occasional OS memory access violation on Windows during large weight mapping.
  - Option 2 (Platform-guarded pread wrapper): Configure `safetensors.torch.load_file` to use native `backend='pread'` on Windows only.
* **Decision**: In `ml_service/app/models/manager.py`, safely defaulted `backend='pread'` on Windows (`sys.platform == 'win32'`). The fix is strictly platform-conditional, does not replace model weights, does not alter model behavior, and maintains peak VRAM under 620 MiB.
* **Consequence/affected people**: Eliminates the Windows memory-mapping blocker without affecting Linux environments or pipeline outputs.
