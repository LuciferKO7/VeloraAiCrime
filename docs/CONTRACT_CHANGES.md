# Contract Changes Log

Protocol R6: Contracts are frozen. Table names, columns, route paths, request/response fields, enum values, env var names and file names in §5–§8 may not be renamed or removed. If something is wrong or missing: STOP, tell the team, append an entry to this document, prefer additive changes, bump `contracts/VERSION`, and get all three humans to acknowledge before merging.

---

## v1.1 — Additive contract addendum (§8.0)

* **What changed**:
  1. Added environment variable `GEMINI_RPM` (integer, default 8; token-bucket limit for Gemini calls).
  2. Added environment variable `LLM_CACHE_TTL_S` (integer, default 3600; in-memory response cache TTL).
  3. Added ML route `GET /ml/v1/manifest` returning model metadata list `[{name, role, version, source, license, checksum}]`.
  4. Backend startup sync upserts `model_registry` rows for active LLMs, speech models, prompt lexicon, and approved glossary.
  5. Formalized `eval_runs.metrics_json` shapes per `eval_runs.kind` (§9.8).
  6. Added optional request field `audio_sha256` on `POST /sessions/{sid}/statements` (stored in `statements.audio_sha256`).
  7. Defined binding HTTP status map for error codes (§12).
  8. Defined egress ledger file `backend/data/egress.log` (host + path of outbound HTTP calls).
  9. Allowed `POST /sessions/{sid}/rounds/edit` with `instruction_text` to return a transform round (`kind: 'transform'`).
* **Why**: Accepted frozen additions per Section 8.0 of Master Prompt v1.1 to handle rate limiting, caching, model tracking, audio integrity, and structured error handling.
* **Additive?**: Yes
* **Affected persons**: Person A, Person B, Person C
* **Acks**: A [ ] B [ ] C [ ] (Unverified: team members must review and confirm)
* **Migration file**: None (incorporated into initial schema baseline)

---

## Template for Future Contract Changes

```markdown
## vX.Y — <title>

* **What changed**: <description of changes>
* **Why**: <reason>
* **Additive?**: yes / no
* **Affected persons**: Person A / B / C
* **Acks**: A [ ] B [ ] C [ ]
* **Migration file**: <path to contracts/migrations/NNN_name.sql if applicable, or None>
```
