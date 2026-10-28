# VELORA

AI witness-to-face composite and scene-sketch platform.

VELORA turns a witness's words — typed or spoken in Tamil, Hindi, English, and more — into an uncertainty-aware, fully auditable suspect composite and scene diagram using a recognition-first loop that improves as the witness interacts. Real-case data never leaves the local environment.

---

## Service Architecture & Port Assignments

The platform consists of federated services communicating locally over HTTP with service-key authentication:

* **Backend Hub**: `http://localhost:8000` (FastAPI, SQLite WAL, hash-chained audit log, LLM routing)
* **ML Service**: `http://localhost:8001` (FastAPI, PyTorch, image generation, masks, preference learning)
* **Speech Service**: `http://localhost:8002` (FastAPI, faster-whisper ASR, IndicTrans2 translation)
* **Frontend**: `http://localhost:5173` (Vite, React 18, TypeScript strict, Tailwind CSS)
* **Local LLM**: `http://localhost:11434` (Ollama)

---

## Service Bring-up & Execution (§15.2)

1. **Ollama (Backend Laptop)**:
   ```bash
   ollama serve
   ```
2. **ML Service (Person A GPU Laptop)**:
   ```bash
   cd ml_service && uvicorn app.main:app --host 0.0.0.0 --port 8001
   ```
3. **Speech Service (Person C Laptop / CPU)**:
   ```bash
   cd speech_service && uvicorn app.main:app --host 0.0.0.0 --port 8002
   ```
4. **Backend Hub (Person B GPU Laptop)**:
   ```bash
   python scripts/init_db.py && python scripts/seed_users.py
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
   ```
5. **Frontend (Person C Laptop)**:
   ```bash
   cd frontend && pnpm dev --host
   ```

---

## Per-Person Quick Start

* **Person A (ML / Image Pipeline)**:
  1. Clone repo and run `git config core.hooksPath .githooks`.
  2. Setup virtual environment: `cd ml_service && python -m venv .venv`.
  3. Branch from main: `git checkout -b personA/ml-service`.
  4. Follow Step A0 benchmarks in `docs/progress/PERSON_A.md`.

* **Person B (Backend Hub, Security, Audit, LLM)**:
  1. Clone repo and run `git config core.hooksPath .githooks`.
  2. Branch from main: `git checkout -b personB/backend-core`.
  3. Follow Step B1 DB & auth implementation in `docs/progress/PERSON_B.md`.

* **Person C (Frontend, Speech, Exports, Scene)**:
  1. Clone repo and run `git config core.hooksPath .githooks`.
  2. Install frontend dependencies: `cd frontend && pnpm install`.
  3. Branch from main: `git checkout -b personC/frontend`.
  4. Follow Step C0 fixtures and model download in `docs/progress/PERSON_C.md`.

---

## Team Ownership Split (§3)

* **Person A (ML / Image Pipeline)**
  * **Ownership**: `ml_service/`, `training/{synth_faces, verifier, sim}/`
  * **Branch**: `personA/ml-service`
* **Person B (Backend Hub, Security, Audit, LLM)**
  * **Ownership**: `contracts/`, `backend/app/{core, db, auth, audit, llm}`, `backend/app/routers/*` (except `exports.py` and `scenes.py`), `scripts/`, `.githooks/`, `.env.example`, `docs/HARDWARE.md`, `training/parser/`
  * **Branch**: `personB/foundation`, then feature branches
* **Person C (Frontend, Speech Service, Exports, Scenes, Demo)**
  * **Ownership**: `frontend/`, `speech_service/`, `backend/app/routers/{exports, scenes}.py`, `backend/app/services/{pdf, scene}/`, `tests/e2e/`, `docs/DEMO.md`, `docs/PITCH.md`
  * **Branch**: `personC/frontend`

---

## Required Post-Clone Setup

After cloning this repository, every team member must run:

```bash
git config core.hooksPath .githooks
```
