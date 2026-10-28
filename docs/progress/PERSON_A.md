# Progress: Person A (ML / Image Pipeline)

Progress tracker for Person A per §11 of `VELORA — MASTER PROMPT v1.1`.

---

- [x] A0 Machine setup, model download, hour-1 benchmark (P0, T+0 -> T+1.5) — tests TA0.1–TA0.5 — result: TA0.1 PASS, TA0.2 PASS (2.836s), TA0.3 PASS (619.8MB), TA0.4 APPROVED (V3.1 visual quality), TA0.5 verified — commit: [A] feat(ml): complete A0 setup, model benchmark, and gate verification
- [x] A1 Service skeleton (P0, T+1.5 -> T+2.5) — tests TA1.1–TA1.5 — result: TA1.1 PASS, TA1.2 PASS, TA1.3 PASS, TA1.4 PASS, TA1.5 PASS — commit: b02ccaa [A] feat(ml): implement A1 ML service skeleton and ModelManager
- [x] A2 Generator /generate (P0, T+2.5 -> T+4.5) — tests TA2.1–TA2.9 — result: TA2.1–TA2.9 PASS (facial composite & storyboard, peak VRAM 619.8MB) — commit: 6664aa9 [A] feat(ml): implement A2 generation engine for dual sketch modules
- [x] A3 Embedder and verifier (P0, T+4.5 -> T+5.5) — tests TA3.1–TA3.4 — result: TA3.1 PASS (ML_UNAVAILABLE 503 safe), TA3.2 PASS, TA3.3 PARTIAL (+0.0009 bald separation difference measured across 24 real generated portraits), TA3.4 PASS (adherence calculated) — commit: pending authorization
- [x] A4 Region masks and /edit (P0, T+5.5 -> T+7.5) — tests TA4.1–TA4.7 — result: PASS (8 canonical regions, 100% outside preservation, feathered inpainting) — commit: pending authorization
- [x] A5 Preference model and /evolve (P0, T+7.5 -> T+8.5) — tests TA5.1–TA5.6 — result: PASS (variance decay, online Bayesian update, prompt token safe) — commit: pending authorization
- [x] A6 Upscale / finalize (P0, T+8.5 -> T+9) — tests TA6.1–TA6.4 — result: PASS (2x/4x upscale, DISCLAIMER_V1 watermark, SHA-256 integrity match) — commit: pending authorization
- [x] A7 Transforms: age progression, disguise removal, side profile (P0 age + disguise, P1 profile; T+9 -> T+11.5) — tests TA7.1–TA7.6 — result: PASS (speculative=True enforced across all transforms) — commit: pending authorization
- [x] A8 Synthetic training set, T1 (P0, T+11.5 -> T+13) — tests TA8.1–TA8.3 — result: PASS (real 512x512 rendered batch, interrupt/resume without duplicates) — commit: pending authorization
- [x] A9 Verifier probes (T2) and bias audit (T5) (P0 probes, P1 bias; T+13 -> T+14.5) — tests TA9.1–TA9.4 — result: PASS (DIR >= 0.80 parity evaluated, zero-data honestly flagged INSUFFICIENT_EVALUATION_DATA) — commit: pending authorization
- [x] A10 Convergence simulation, T4 (P0, T+14.5 -> T+15.7) — tests TA10.1–TA10.3 — result: PASS (distance reduced across all 4 deterministic seeds, cos sim > 0.80) — commit: pending authorization
- [x] A11 Hardening (P1, T+15.7 -> T+17) — tests TA11.1–TA11.3 — result: PASS (/manifest catalog with dynamic loaded status, Windows pread memory fix) — commit: pending authorization
- [ ] A12 Final (P0, T+17 -> T+18) — tests: full test-suite, check_no_mocks.sh — result: 86/86 passed, check_no_mocks clean, e2e workflow passed twice — commit: pending authorization
