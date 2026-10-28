# VELORA — MASTER PROMPT v1.1

AI witness-to-face composite and scene-sketch platform · hackathon build · 3 people · 18-hour hard limit
Repo: https://github.com/LuciferKO7/VeloraAiCrime.git

## HOW TO USE THIS DOCUMENT

**Human**: paste this entire file into your coding agent (or tell it to read `docs/MASTER_PROMPT.md` in the repo). Then say exactly:
"I'm working as Person A." (or B, or C)

**Agent**: you now act as that person's pair-programmer. Follow §0 strictly, execute only your person's section (§11 = A, §12 = B, §13 = C) step by step, and obey the shared contracts (§5–§8) exactly. Start with Step X0 of your section.

| Person | Role | Machine |
| :--- | :--- | :--- |
| **A** | ML / image pipeline: generation, edit, evolve, age/disguise/profile, upscaling, synthetic data, verifier, simulations | GPU laptop #1 (RTX 3050) → runs `ml_service` :8001 |
| **B** | Backend core, security, audit chain, LLM layer, parsing, ML proxy, glossary/parser learning, match, consensus | GPU laptop #2 (RTX 3050) = HUB → runs `backend` :8000, `Ollama` :11434 |
| **C** | Entire frontend, speech service (ASR + translation), exports, scene module, e2e tests, demo | Intel i7 laptop (no GPU) → runs `frontend` :5173 (+ `speech_service` :8002 on CPU for dev) |

---

## 0. AGENT OPERATING RULES (NON-NEGOTIABLE)

* **R1 — Identity**. Take Person X from the human's first message. If missing, ask once.
* **R2 — Scope**. Do only your person's steps. Other persons' sections are read-only context. Never edit files owned by another person (see §3 ownership) except through the contract-change protocol (R6).
* **R3 — Gate protocol**. For every step: (1) state the step; (2) implement; (3) run every test listed; (4) paste the real output to the human; (5) only if all pass, tick the box in `docs/progress/PERSON_X.md`, commit, push; (6) next step. Never skip a test, never weaken a test to make it pass — fix the code. If a test cannot pass, stop and tell the human what is blocking.
* **R4 — No mocks, no fake data**. Forbidden in committed non-test code: hard-coded sample LLM outputs, fake image bytes, stub endpoints that return canned data, `if MOCK/USE_MOCK` switches, placeholder faces, Lorem ipsum, fabricated metrics. Services must call the real LLM, real models, real DB. Test fixtures (real-format inputs such as an English description string) are allowed only under `tests/` or `**/fixtures/`. Local-only scratch data may live in gitignored `__dev__/` folders and must never be pushed. `scripts/check_no_mocks.sh` runs on pre-push and fails the push (§16).
* **R5 — Real LLM**. API keys live only in `.env` (gitignored). Every LLM-touching step ends with a live call to the real provider(s) (Gemini and Ollama) with measured latency printed. No step involving LLMs is "done" on unit tests alone.
* **R6 — Contracts are frozen**. Table names, columns, route paths, request/response fields, enum values, env var names and file names in §5–§8 may not be renamed or removed. If something is wrong or missing: STOP, tell the human, and use the change protocol: append an entry to `docs/CONTRACT_CHANGES.md` (what, why, who is affected), prefer additive changes (new nullable column, new optional field, new route), bump `contracts/VERSION`, and get all three humans to ack before merging. Additive DB changes go in `contracts/migrations/NNN_name.sql`.
* **R7 — Git**. Clone the repo; create your branch from `main` named `personX/<feature>` (e.g. `personA/ml-service`; no spaces). Push often (`git push -u origin personX/<feature>`). Commit format: `[A] feat(ml): short message`. Open a PR to `main` at each Integration Gate (§10) after your gate tests pass; run `git pull --rebase origin main` first; merge after the dependent teammate confirms the smoke test. Never force-push `main`.
* **R8 — Secrets**. Never commit `.env`, keys, tokens, models, datasets, DB files, or generated images. Only `.env.example` with empty/placeholder values.
* **R9 — Human-in-the-loop**. Ask the human only for what an agent cannot do: API keys, installing drivers, recording audio, reading `nvidia-smi`, LAN IPs, approvals of contract changes. Otherwise act autonomously.
* **R10 — Honesty**. Report measured numbers. Thresholds marked (calibrate) are starting guesses; measure and record the final value in `docs/DECISIONS.md`. Never claim real-world accuracy; claim only what your tests measure.
* **R11 — Responsible-AI invariants (never violate)**:
  1. The LLM/ML must never infer appearance group, skin tone, religion, caste, nationality or region from the witness text. Only stated by witness or `user_edit` by officer. Case-level `default_appearance_group` is set by a human.
  2. Unspecified attributes are not defaulted — they are sampled across variants so no stereotype is baked in. The UI shows them in the "AI assumed" panel.
  3. Every generated image and export carries: "AI-generated investigative aid — not a photograph, not evidence of identity."
  4. `cases.data_mode='real'` ⇒ LLM calls go to Ollama only; no cloud API is ever called. If Ollama is down, fail with `LLM_UNAVAILABLE_LOCAL`; never fall back to cloud.
  5. Every case-scoped request, success or denied, writes a hash-chained audit entry.
  6. No automatic learning from real-case data. Learning uses synthetic data, consented volunteers, and supervisor-approved glossary entries only. Model/glossary versions are stamped on outputs.
  7. Match results are called "possible leads" with similarity scores — never "identified".
* **R12 — Priorities**. Steps are tagged P0 (must), P1 (should), P2 (stretch). At every gate (§10), if you are >45 min behind, drop P2, then P1, in that order. Tell the human when you cut.
* **R13 — Verify before use**. Model repo IDs, package APIs and versions in this doc are best knowledge, not guaranteed. Verify each by running code (`huggingface_hub.model_info`, `pip index versions`, a 3-line import test). Record deviations in `docs/DECISIONS.md`. Pin working versions in `requirements.lock`.
* **R14 — Quality**. Python 3.11, type hints, ruff clean, pytest; TypeScript strict; structured logging (no print); every route has a pytest test; all I/O has timeouts.
* **R15 — Progress file**. Keep `docs/progress/PERSON_X.md` as a checklist of your steps with measured results; it lets a fresh agent session resume.

---

## 1. PRODUCT, DIFFERENTIATORS, JUDGING STRATEGY

**One-liner**: Velora turns a witness's words — typed or spoken in Tamil, Hindi, English and more — into an uncertainty-aware, fully auditable suspect composite and scene diagram, using a recognition-first loop that gets better as the witness chooses; real-case data never leaves the building.

**Baseline (everyone will build)**: text → one pretty face → chat edits → export → login log.

### Our differentiators (each is a demo moment)

| # | Differentiator | Why judges care |
| :--- | :--- | :--- |
| **D1** | Recognition-first variant grid (6 variants/round, pick / more-like-this / less-like-this) with an online preference model | Matches how witness memory works (recognition beats recall); explainable; measurable |
| **D2** | Regional-language voice + text (ta, hi, te, kn, ml, bn, mr, en) via ASR → IndicTrans2 → LLM parse | Real accessibility for Indian police stations |
| **D3** | Privacy router: real cases = local Ollama only; demo cases may use Gemini | Free Gemini tier may use prompts to improve products and human reviewers may read them |
| **D4** | Responsible-AI panel: "AI assumed" list, per-feature witness confidence, uncertainty-aware export, bias audit | Answers the biggest critique of AI composites |
| **D5** | Tamper-evident hash-chained audit log + live "Verify integrity" + tamper demo | Goes far beyond "a log table" |
| **D6** | Governed learning: synthetic-ground-truth training, learning curves, supervisor-approved glossary | "Learns over time" without unsafe drift |
| **D7** | Transforms: age progression/regression, disguise removal, side profile (labelled speculative) | Extra investigative value |
| **D8** | Scene diagram from narratives (editable canvas, uncertainty styling) | Covers both readings of the problem |
| **D9** | Multi-witness consensus + active question selection | Realistic casework |
| **D10** | Offline kill-switch demo: disable Wi-Fi, system still works (Ollama + local models) | Credibility for police deployment |

### Judge rubric → our answer

| Criterion | Evidence we show |
| :--- | :--- |
| **Innovation** | D1, D3, D6, D7, D8 |
| **Technical depth** | Own pipeline: parsing → masks/inpainting → preference model → verifier; learning-curve charts |
| **Working demo** | Live, real LLM, real GPU, no mocks; 5-minute scripted flow (§17) |
| **UX / accessibility** | Voice-first, large-touch witness mode, 6 UI languages |
| **Impact / feasibility** | Runs on 6 GB laptops; BNSS-aligned audit; local-first |
| **Responsible AI / security** | R11 invariants, bias audit, RBAC, hash chain |
| **Presentation** | Problem numbers, honest limits slide, backup video |

Evidence for the pitch (verify each before quoting): Innocence Project (2018) data as reported in Tredoux et al. 2021, J. Exp. Criminology: eyewitness misidentification in 69% of 367 DNA-exoneration cases, 27% of those involving a composite (correlation, not proven cause). Frowd et al.: feature-based composites (E-FIT/PRO-fit) typically named ~20% in lab tests; EvoFIT police audits (2011) reported arrests from 25.4% of composites (38.5% with a newer interview). Goodyear (AZ) PD uses ChatGPT-enhanced sketches; critics note photorealism overstates certainty and AI is hard to explain in court. BNSS §176(3) mandates forensic scene visits for offences ≥7 years (state-notified). Indian courts treat identification parades as corroborative only.

---

## 2. ARCHITECTURE & TECH STACK

```text
Browser (React PWA :5173)
│ JSON + multipart (JWT)
▼
BACKEND HUB (FastAPI :8000, Person B machine)
├─ SQLite velora.db (WAL) + backend/storage/{images,exports}
├─ Audit middleware (hash chain) ├─ RBAC / case access
├─ LLM Router ──► Ollama :11434 (always) └─► Gemini API (demo cases only)
├─ ML proxy ──► ML SERVICE :8001 (Person A GPU) — NDJSON streaming, X-Service-Key
└─ Speech proxy ─► SPEECH SERVICE :8002 (ASR + IndicTrans2) — X-Service-Key
```

| Layer | Stack |
| :--- | :--- |
| **Frontend** | React 18, Vite, TypeScript (strict), Tailwind CSS, TanStack Query, Zustand, react-i18next, react-konva, Recharts, vitest, Playwright |
| **Backend** | Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2, SQLite (WAL), Pydantic v2, PyJWT, argon2-cffi, httpx, slowapi, reportlab, qrcode, Pillow, google-genai, ollama, pytest, ruff |
| **ML service** | PyTorch (CUDA), diffusers, transformers, accelerate, open_clip_torch, insightface + onnxruntime, mediapipe, opencv-python, scikit-learn, numpy, FastAPI |
| **Speech** | faster-whisper, IndicTransToolkit + transformers, ffmpeg, FastAPI |
| **LLMs** | Ollama (3–8B instruct, 4-bit) = primary/offline; Gemini free tier (Flash / Flash-Lite class, chosen from AI Studio) = demo-mode only |
| **Image gen** | Local only (Gemini free tier does not currently include image models; check AI Studio). Optional hosted fallback (Cloudflare Workers AI FLUX-schnell/SDXL-Lightning free quota) only for synthetic-data augmentation, never real cases |

**GPU budgeting (6 GB-class 3050; confirm with nvidia-smi)**:
- GPU #1 (A): one SD-1.5-class pipeline in VRAM at a time via ModelManager (LRU swap); fp16; 512 px; LCM 4 steps.
- GPU #2 (B/hub): Ollama model ≤ 2.5 GB + Whisper ≤ 1.5 GB (use small/medium int8 unless VRAM ≥ 8 GB) + IndicTrans2 distilled on CPU.
- If a card is 4 GB: run speech on CPU (C's laptop via `SPEECH_SERVICE_URL`), set `LOW_VRAM_MODE=true` (sequential CPU offload, 448 px, no IP-Adapter on edits).

---

## 3. REPO LAYOUT, OWNERSHIP, GIT

```text
VeloraAiCrime/
├─ docs/ MASTER_PROMPT.md CONTRACT_CHANGES.md DECISIONS.md HARDWARE.md DEMO.md progress/PERSON_{A,B,C}.md
├─ contracts/ schema.sql face_attributes.schema.json scene.schema.json VERSION migrations/
├─ backend/ app/{main.py,core/,db/,auth/,audit/,llm/,routers/,services/} tests/ requirements.txt
├─ ml_service/ app/{main.py,pipelines/,masks/,preference/,verifier/,transforms/,store/} scripts/ tests/ reports/(gitignored)
├─ speech_service/ app/ tests/
├─ frontend/ src/{api,components,pages,i18n,store,...} public/locales/ e2e/
├─ training/ synth_faces/ synth_text/ parser/ verifier/ sim/ (data gitignored)
├─ scripts/ check_no_mocks.sh init_db.py seed_users.py llm_smoke.py tamper_demo.py integration/
├─ .githooks/pre-push .env.example .gitignore README.md
```

### Ownership (only the owner edits)

| Path | Owner |
| :--- | :--- |
| `contracts/`, `backend/app/{core,db,auth,audit,llm}`, `backend/app/routers/*` except `exports.py`, `scenes.py`, `scripts/`, `.githooks`, `.env.example`, `training/parser/` | **B** |
| `ml_service/`, `training/{synth_faces,verifier,sim}/` | **A** |
| `frontend/`, `speech_service/`, `backend/app/routers/{exports,scenes}.py`, `backend/app/services/{pdf,scene}/`, `tests/e2e/`, `docs/DEMO.md`, `docs/PITCH.md` | **C** |
| `docs/MASTER_PROMPT.md`, `docs/CONTRACT_CHANGES.md` | **shared (protocol R6)** |

**Router auto-discovery**: `backend/app/main.py` (B) imports every module in `app/routers/` exposing a variable `router`; so C adds `exports.py`/`scenes.py` without touching `main.py`.

**Branches**: `personA/ml-service`, `personB/foundation`, `personC/frontend` (sub-branches allowed).
**Step 0 order**: B pushes the foundation commit (this doc, contracts, `.env.example`, `.gitignore`, hooks) to `main` first (within ~45 min); A and C use the wait to install drivers/tools and download models, then branch from `main`.

---

## 4. ENVIRONMENT — .env.example

See `.env.example` in repo root.

---

## 5. DATABASE SCHEMA (single source of truth → contracts/schema.sql)

See `contracts/schema.sql` in repo. SQLite, `PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL;`. IDs are UUID4 text (except `audit_log.seq`). Timestamps are UTC ISO-8601 text `YYYY-MM-DDTHH:MM:SS.sssZ`.

Hash chain (exact): `entry_hash = SHA256_hex( prev_hash + "|" + canonical )`
where `canonical = json.dumps({ts,user_id,username,role,action,resource_type,resource_id,case_id,purpose,ip,status_code,details}, sort_keys=True, separators=(",",":"), ensure_ascii=False)` (`details` = parsed `details_json`).
Genesis `prev_hash = "0"*64`. Writes happen inside one transaction that reads the last hash (serialize with `BEGIN IMMEDIATE`).

---

## 6. SHARED DATA CONTRACTS

### 6.1 FaceAttributes v1.0 (`contracts/face_attributes.schema.json`)
Generated by B via `scripts/gen_face_schema.py`.

### 6.2 Scene v1.0 (`contracts/scene.schema.json`)
Top-down view; (0,0) = top-left.

### 6.3 Errors, auth, conventions
- Base paths: backend `/api/v1`, ML `/ml/v1`, speech `/sp/v1`. All JSON UTF-8. IDs UUID4.
- Auth: `Authorization: Bearer <JWT>` (claims `sub`, `role`, `exp`). Service-to-service: header `X-Service-Key: $SERVICE_KEY`.
- Purpose of access: every case-scoped request must carry header `X-Access-Purpose: <min 5 chars>`; otherwise `400 PURPOSE_REQUIRED`.
- Error body: `{"error":{"code":"STRING","message":"human readable","details":{}}}`. Codes: `AUTH_INVALID`, `AUTH_EXPIRED`, `ACCOUNT_LOCKED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `PURPOSE_REQUIRED`, `CONFLICT_VERSION`, `LLM_UNAVAILABLE`, `LLM_UNAVAILABLE_LOCAL`, `LLM_SCHEMA_INVALID`, `ML_UNAVAILABLE`, `ML_BUSY`, `SPEECH_UNAVAILABLE`, `RATE_LIMITED`, `INTERNAL`.
- Role matrix: `investigator/artist` → only cases with a non-revoked `case_access` row (edit for mutations, view for reads); `supervisor` → all cases, plus glossary review; `auditor` → audit routes + case metadata but no content; `admin` → users, models, gallery, health, eval-runs.
- Disclaimer constant (`DISCLAIMER_V1`): "AI-generated investigative aid — not a photograph, not evidence of identity."

---

## 7. API CONTRACTS
Details of backend `/api/v1`, ML `/ml/v1`, and Speech `/sp/v1` routes.

---

## 8. LLM LAYER, PROMPTS, AND DETERMINISTIC LOGIC
Includes §8.0 frozen addendum (`GEMINI_RPM=8`, `LLM_CACHE_TTL_S=3600`, etc.), router rules, prompt specifications, and merge algorithm.

---

## 9. ML ARCHITECTURE, DATASETS, TRAINING SCHEDULE
Pipeline overview, model choices, variation rules, preference learning, and eval runs.

---

## 10. TIMELINE, INTEGRATION GATES, MERGE PROTOCOL
Gates G0–G5 schedule and merge rules.

---

## 11. PERSON A — ML / IMAGE PIPELINE
Steps A0–A12.

---

## 12. PERSON B — BACKEND HUB, SECURITY, AUDIT, LLM
Steps B0–B13.

---

## 13. PERSON C — FRONTEND, SPEECH SERVICE, EXPORTS, SCENE MODULE, E2E, DEMO
Steps C0–C13.

---

## 14. FINAL END-TO-END TEST AFTER INTEGRATION
Scenarios E1–E18.

---

## 15. STEP-BY-STEP INTEGRATION GUIDE
Network, ports, and bring-up order.

---

## 16. PRE-PUSH MOCK/SECRET GATE
Implemented via `scripts/check_no_mocks.py`, `scripts/check_no_mocks.sh`, and `.githooks/pre-push`.

---

## 17. DEMO SCRIPT, PITCH, AND JUDGE Q&A
5-minute talk track and Q&A cheat sheet.

---

## 18. EXTENSIBILITY
Feature expansion recipes without contract breaking.

---

## 19. APPENDIX
Kickoff checklists, templates, risk register, and version history.
