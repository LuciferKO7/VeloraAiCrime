# VELORA — FRONTEND EXPERIENCE SPEC v1.0 (Person C)

**Companion to `docs/MASTER_PROMPT.md` (v1.1). Save as `docs/FRONTEND_DESIGN.md`.** Goal: a Huly-inspired, Apple-smooth, live-animated UI with the **fewest possible screens** and one obvious next action at every moment — built to win a 5-minute live demo.

---

## 0\. HOW TO USE (read first, agent)

1. The MASTER PROMPT wins every conflict. This file changes **presentation and flow only**: no route paths, API fields, DB columns or env names change, so no R6 contract entry is needed. Record the screen consolidation in `docs/DECISIONS.md`.
2. Rules still binding: **R4** (no mocks, no placeholder faces, no fake data — skeletons and honest empty states only), **R11** (no inference, "AI assumed" visible, disclaimer on every image, "possible leads" wording), §13 rules for Person C, TC tests.
3. Build order is in §12. Polish never blocks P0 function: if \>45 min late at a gate, cut P2 then P1 of this file first (R12).
4. This spec is **inspired by** Huly's dark, calm, glowing look; it does not copy its assets, copy or logo. Token values below are our own choices.

---

## 1\. DESIGN THESIS

**"Calm intelligence."** Near-black canvas, soft living light behind glass surfaces, one companion character who reacts to what the system is *really* doing, and motion that follows physics (springs), never decoration for its own sake.

**Five wow-moments the judges must see (everything else supports these):**

| \# | Moment | Why it lands |
| :---- | :---- | :---- |
| W1 | **Voice in Tamil → chips fly out of the speech bubble into the attribute panel**, with the character "listening → thinking → sketching" | Shows D2 (regional voice) \+ real pipeline latency honestly |
| W2 | **Six faces draw themselves in one by one** (pencil strokes reveal), while the character sketches along | Makes streaming generation feel alive and hides no latency |
| W3 | **The whole world turns teal when a case is Local-only** (ambient light, shield on the character, "No cloud" chip) | D3 privacy router understood in 1 second, no explanation needed |
| W4 | **Audit chain as visible linked blocks**; tamper one byte → the chain visibly breaks at the bad block | D5, the most memorable security demo |
| W5 | **Before/after slider and Time dial** (age ± years, remove beard/glasses, profile) with Speculative amber styling | D7, tactile and impressive |

---

## 2\. INFORMATION ARCHITECTURE — 4 SHELLS, ALL FROZEN ROUTES KEPT

Fewer pages ⇒ simpler flow. The 13 frozen routes of §13 stay as **deep-link paths**; they render inside four shells as tabs, drawers or sheets.

| Shell | What it is | Frozen routes rendered inside it |
| :---- | :---- | :---- |
| **1\. Landing** (exists) | Story \+ live status \+ "Open Velora" | `/` (+ `/login` opens as a **sheet over the landing**) |
| **2\. Command Center** | Case grid, create-case sheet, case **drawer** with tabs (Witnesses · Sessions · Consensus · Access) | `/cases`, `/cases/:id` (drawer open), `/cases/:id/consensus` (drawer, Consensus tab) |
| **3\. Studio** | The one place real work happens: describe → recognize → refine → finalize; scene mode uses the same shell | `/sessions/:sid`, `/sessions/:sid/scene` |
| **4\. Trust Center** | Segmented tabs: **Audit · Learning · Glossary · Responsible AI · System** (System \= health \+ models \+ users, admin only) | `/audit`, `/learning`, `/glossary`, `/responsible-ai`, `/health`, `/admin/users`, `/admin/models` |

Role-aware: tabs a role cannot use are not rendered (auditor sees only Audit; investigator never sees Glossary/System). A global **command palette** (`Ctrl/Cmd+K`, library `cmdk`) jumps anywhere: "Open case…", "New case", "Start composite", "Toggle witness mode", "Switch language", "Verify integrity", "Presenter HUD".

---

## 3\. DESIGN SYSTEM

### 3.1 Tokens (CSS variables in `src/styles/tokens.css`; Tailwind reads them)

:root {

  /\* surfaces — dark ladder (bg-0 matches Huly's theme-color \#090a0c) \*/

  \--bg-0:\#090a0c; \--bg-1:\#0e0f12; \--bg-2:\#14161a; \--bg-3:\#1b1d22;

  \--glass: rgba(20,22,26,.55); \--glass-strong: rgba(27,29,34,.72);

  \--line: rgba(255,255,255,.08); \--line-strong: rgba(255,255,255,.14);

  \--hi: inset 0 1px 0 rgba(255,255,255,.06);            /\* top highlight on glass \*/

  /\* text \*/

  \--text-1:\#f4f5f7; \--text-2:rgba(244,245,247,.68); \--text-3:rgba(244,245,247,.56); /\* min for small text: AA on bg-0 \*/

  /\* semantic \*/

  \--warn:\#ffb454;   /\* speculative, unsure \*/

  \--danger:\#ff6b6b; \--ok:\#41d6a1;

  /\* ambient accent, switched by data-mode on \<html\> \*/

  \--a1:\#7c8cff; \--a2:\#5ad1ff; \--a3:\#b48cff;             /\* demo (cloud allowed): indigo / cyan / violet \*/

  \--radius-s:12px; \--radius-m:20px; \--radius-l:28px;

  \--ease-out: cubic-bezier(.2,.8,.2,1);

}

html\[data-mode="local"\] { \--a1:\#2fd4a4; \--a2:\#5ad1ff; \--a3:\#7be0c3; }   /\* real case: teal/emerald \*/

html\[data-mode="alert"\] { \--a1:\#ff6b6b; \--a2:\#ffb454; \--a3:\#ff8f8f; }   /\* integrity failure / tamper \*/

`data-mode` is set from the open case's `data_mode` (`demo` → default, `real` → `local`) and flips to `alert` while the Audit Verify result is invalid. Transition the variables with `@property` registered colors (`transition: --a1 .8s`) so the whole ambient shifts smoothly (W3).

### 3.2 Typography

- **Inter Variable** self-hosted via `@fontsource-variable/inter`; stack `ui-sans-serif, system-ui, -apple-system, "SF Pro Text", Inter, …` so Apple devices render SF. Mono for hashes: `JetBrains Mono` (self-hosted).
- Indic scripts: self-hosted Noto Sans Tamil/Devanagari/Telugu/Kannada/Malayalam/Bengali (same files the PDF export uses).
- **No CDN fonts, images or scripts anywhere** — the offline kill-switch demo (D10) must work with Wi-Fi off, and TCD6 enforces it.
- Scale: display 56/60 −0.03em · h1 32 · h2 22 · body 15 · small 13 · mono 12\. Hierarchy by weight (400/500/600) and opacity (`text-1/2/3`) rather than many sizes. `font-optical-sizing:auto`.

### 3.3 Glass, elevation, shape

- Glass \= `background: var(--glass); backdrop-filter: blur(24px) saturate(160%); border:1px solid var(--line); box-shadow: var(--hi), 0 8px 32px rgba(0,0,0,.35)`.
- **Max 3 glass layers visible at once** (performance on the demo laptop's integrated GPU). Everything else is solid `bg-1/2/3`.
- Under `prefers-reduced-transparency` or low-power tier: solid `bg-2` \+ border, no blur.
- Radii: cards 20, sheets 28, chips/buttons pill. Optional progressive enhancement: `corner-shape: squircle`.
- Buttons: primary \= gradient `--a1→--a2`, dark text, soft glow `0 0 24px color-mix(in srgb,var(--a1) 40%,transparent)`; secondary \= glass; destructive \= outline `--danger`. Press: `scale(.97)` on **pointer-down**, 100 ms ease-out.

### 3.4 Motion tokens (Apple-style physics; library `motion` (framer-motion))

| Token | Value | Use |
| :---- | :---- | :---- |
| `spring.standard` | `{type:"spring",duration:.4,bounce:0}` | all UI state changes, drawers, sheets, chips |
| `spring.momentum` | `{type:"spring",duration:.4,bounce:.2}` | flick/drag releases, card dismiss, dial |
| `press` | `scale .97`, 100 ms ease-out on pointer-down | every button/card |
| `stagger` | 60 ms per item, max 8 items | grids, lists, chip groups |
| `enter/exit` | mirror each other (same axis/direction) | sheets, drawers, route changes |
| shared elements | `layoutId` \+ `transform-origin` at the trigger | card → expanded face, chip FLIP from bubble to panel |
| rubber-band | resistance constant `0.55` past drag limits | dial, sheets, swipe cards |
| Animations must be **interruptible and re-targetable** (springs, not keyframe timelines). `prefers-reduced-motion`: replace every transform animation with a 200 ms opacity fade; background goes static; the character holds a still pose. Functionality never depends on motion. |  |  |

---

## 4\. LIVE BACKGROUND SYSTEM (`<AmbientBackground/>`, mounted once in the root layout)

Four layers, bottom to top, pointer-events none:

1. **Base**: `--bg-0` plus a very faint vertical vignette.
2. **Aurora blobs**: 3 large radial-gradient divs using `--a1/--a2/--a3`, `filter: blur(80px)`, animated only with `transform` (slow drift, 28–40 s loops, different periods so it never repeats visibly). Cheap on iGPU.
3. **Line field** (Huly-like "lines" texture): one `<canvas>` 2D at 0.5× resolution — thin perspective grid / flowing contour lines that gently ripple, with the pointer creating a soft local distortion; 30 fps cap; opacity 0.25.
4. **Dust particles**: \~40 tiny points drifting upward; additive blend; during "thinking" states they accelerate toward the character (ties the world to system activity).

**Performance tiers (auto, `useAmbientTier`)**: measure frame time for the first 2 s and again every 30 s. `high` \= all layers; `mid` \= blobs \+ lines, no particles; `low` \= static gradient \+ one slow blob. Pause everything when `document.hidden`. A discreet toggle in the command palette ("Low-power visuals") forces `low`. The Playwright suite runs in `low`. **Ambient reacts to real events:** `round running` → blobs brighten and lines flow faster; `error` → a single warm pulse; `integrity invalid` → `data-mode="alert"`; `local case` → teal.

---

## 5\. THE LIVE CHARACTER — "VELA" (original character, code-drawn SVG)

A small luminous sketching spirit: a rounded orb body with two expressive eyes, a tiny pencil-tip tail that leaves a faint line trail, and a soft glow in `--a1`. **Original design — do not model it on any existing mascot.** Drawn as one SVG component `<Vela state size/>` animated with `motion` variants (no external animation asset required; a Rive upgrade is P2).

**She reacts only to real system events** (no scripted fakery). Her speech bubbles are the **real `next_question`** and real status text, from locale files (every string i18n'd, so she speaks the witness's language).

| State | Trigger (real signal) | Animation |
| :---- | :---- | :---- |
| `idle` | nothing pending | slow breathing (scale 1→1.03), blink every 3–5 s, eyes lazily follow the pointer |
| `listening` | mic recording | leans toward the mic orb; ring of live audio-level bars (from `AnalyserNode`) around her; eyes widen |
| `thinking` | statement request in flight (ASR / translate / parse) | eyes look up-right, 3 small orbs circle her, dust particles stream toward her |
| `sketching` | round `running` | tail-pencil draws strokes in the air; every new image event ⇒ a small "tick" flourish |
| `curious` | `next_question` available | tilts head, bubble pops with the question and answer chips |
| `shield` | case `data_mode='real'` | wears a translucent shield; `Local-only` chip; glow teal |
| `proud` | finalize done / audit verify valid | small hop \+ sparkle burst (canvas, 600 ms) |
| `wince` | `ML_UNAVAILABLE`, `LLM_UNAVAILABLE(_LOCAL)`, `SPEECH_UNAVAILABLE` | quick shake, eyes squint, bubble with the plain-language reason \+ retry |
| `alarm` | audit verify invalid | red glow, eyes wide, points at the broken block |
| `sleepy` | idle \> 90 s | eyes half-closed, slow "z" particles; wakes on pointer |

Sizes: **hero 220 px** (landing, Studio empty state, witness mode), **companion 64 px** (docked bottom-left of the conversation rail), **mini 24 px** (inside the Dynamic Island). Respect reduced motion (still poses). Dev-only gallery route `/vela-lab` (`import.meta.env.DEV` only) lets you cycle states for test **TCD8**.

---

## 6\. SCREEN SPECS

### 6.1 Landing (already built) — additions only

- Replace any decorative faces with **abstract** visuals (aurora \+ animated contour lines \+ the hero Vela). Never use stock or invented face images (R4).
- **Live status strip** under the hero from the real `GET /health`: pills "Backend · ML · Speech · Local LLM · Cloud LLM" with pulsing dots; if the backend is unreachable the pill says so (honest).
- Hero line suggestion: **"Say it. See it. Prove it."** Sub: *Witness words in any Indian language → an uncertainty-aware composite → a tamper-evident audit trail. Real cases never leave the building.*
- Primary CTA **Open Velora** → login sheet. Secondary **Watch how it works** scrolls a 3-beat story: *Speak* (waveform → chips) · *Recognize* (six sketch cards drawing in) · *Prove it* (hash-chain blocks) — built from the real components in a non-interactive demo-less state (empty UI chrome, no fake data).
- Parallax on scroll is subtle (≤ 24 px). Footer: disclaimer constant, licenses link.

### 6.2 Login sheet (route `/login`)

Glass sheet slides up (spring.standard) over the dimmed landing. Fields: username, password. Lock message with countdown for `ACCOUNT_LOCKED`; localized error shake for `AUTH_INVALID`. On success the sheet morphs (shared layout) into the Command Center greeting "Good afternoon, \<full\_name\>". **No credentials are ever hard-coded or pre-filled.** Language switcher (globe) top-right of the sheet.

### 6.3 Command Center (`/cases`)

- **Greeting row** with Vela companion, role chip, today's date, and a live integrity dot (green \= last Verify valid, fetched from `/audit/verify` only for auditor/admin; for others show service health).
- **Case grid**: glass cards (title, case number, station, status, mode badge: indigo "Demo" / teal "Local-only", last updated). Hover: lift \+ gradient border sweep. Click ⇒ drawer.
- **"New case" button** ⇒ bottom sheet, 3 steps in one sheet with animated progress: (1) number \+ title, (2) **mode** as a large segmented control — *Demo (may use Gemini)* vs *Real (Local-only, never cloud)* — the ambient preview shifts teal when "Real" is hovered, (3) `default_appearance_group` with helper "Set by the officer only; the AI never guesses this" and "unspecified" preselected.
- Empty state: hero-size Vela \+ "No cases yet — start your first" (real empty state).
- **Purpose-of-access sheet** (Face-ID-style): appears the first time a case is opened in the browser session; quick chips ("Witness interview", "Case review", "Supervision") **fill** the text field, the 5-character minimum still applies; remembered in memory per case (§13 C2).

### 6.4 Case drawer (right-side, 520 px, spring.standard)

Tabs with a sliding underline: **Witnesses** (add: alias auto-suggested `W-00N`, language as flag-less chips with native script names: தமிழ், हिन्दी, తెలుగు, ಕನ್ನಡ, മലയാളം, বাংলা, मराठी, English) · **Sessions** (cards; buttons **Start composite** / **Start scene**) · **Consensus** (multi-select witnesses' face sessions → agreement matrix heat-map; row click highlights disputed features; "Generate alternates for disputed features") · **Access** (supervisor only). Starting a session closes the drawer and **zooms into Studio** (shared-element transition from the session card).

### 6.5 STUDIO (`/sessions/:sid`) — the main event

**Layout (≥1280 px):**

┌───────────────────── Dynamic Island (top centre, morphs) ─────────────────────┐

│  CASE-001 · W-001 · ● Ollama 1.2 s · Local-only   \[Describe\]—\[Recognize\]—\[Refine\]—\[Finalize\]  │

├──────────────┬──────────────────────────────────────────────┬───────────────┤

│ Conversation │                 STAGE                        │  Inspector    │

│ rail 340px   │  (voice orb / 6-card grid / expanded face /  │  attributes   │

│ \+ Vela       │   compare slider / scene canvas)             │  AI assumed   │

│ \+ next Q     │                                              │  locks, conf. │

├──────────────┴──────────────────────────────────────────────┴───────────────┤

│        Round filmstrip (thumbs)          ·          DOCK (floating, magnifying)          │

└──────────────────────────────────────────────────────────────────────────────┘

- **Dynamic Island** (Apple-style pill, `layout` animation): collapsed \= case no · witness · route badge · phase; expands on activity to show *what is happening now*: "Transcribing (Tamil) …", "Translating …", "Parsing · ollama:qwen… · 1.2 s", "Round 2 · 4/6 images". Content comes from real request state and the `llm` object of the response (provider, model, latency, `route_reason`). Mini-Vela on its left.
- **Phase stepper** (4 dots linked by a fluid line): Describe → Recognize → Refine → Finalize; the active segment fills with the accent gradient; completed steps are clickable (to go back and look, not to rewrite history).
- **Dock** (macOS-style, icons magnify on pointer proximity): Mic · Type · Generate/Next round · Edit · Time dial · Compare · Undo · Finalize. **Exactly one primary button glows** (the next logical action) and the rest are secondary — this is what keeps the flow simple.
- **Inspector**: attributes grouped by region from `contracts/face_attributes.schema.json`; chips with a confidence ring (sure ●, somewhat ◐, unsure ○, editable → `PUT /attributes`); lock toggles per region; **AI assumed** panel with dashed ghost chips ("not stated — varied across variants"); unmapped notes; collapses to a bottom sheet \<1100 px.

**Phase 1 — Describe** (stage shows hero Vela \+ giant mic orb; copy: *"Describe the person. Speak or type — any language."*)

1. Mic orb: **tap to start / tap to stop** (also hold-space). While recording: Vela `listening`, bars around the orb, language chip shows the witness's preferred language and "auto".
2. Stop ⇒ Vela `thinking`, island shows *Transcribing → Translating*. The transcript appears **editable** in a glass bubble with original script on top and English beneath; button **Send** (or Enter). Never auto-send low-confidence text (confirmation is the human-in-the-loop).
3. Send ⇒ island *Parsing*; on response, **chips fly (FLIP) from the bubble to the Inspector** with stagger; `changes[]` flash once; the route badge updates (W1, W3). `unmapped` items appear as soft notes under the bubble.
4. Vela turns `curious` and shows the real **next question** in her bubble with 2–3 neutral answer chips \+ "not sure" (in the witness's language via `text_local`; English small underneath). Answering \= another statement. The primary dock button becomes **"Show me faces"** as soon as ≥ 1 attribute exists (also available earlier).

**Phase 2 — Recognize** 5\. **Show me faces** ⇒ `rounds/generate`; stage morphs into a 3×2 grid; Vela `sketching`; island *Round 1 · 0/6*. 6\. Each image arrives (700 ms polling) ⇒ its card goes **skeleton shimmer → pencil-stroke wipe reveal (≈600 ms, clip-path from top) → settles**; the "AI-generated" ribbon is part of the card from the first frame and is **never hidden by hover/selection** (TCD4). Pencil style by default; a segmented control flips to photo. A small `variant_axes` caption ("varied: face shape · hair") appears on hover. 7\. Interactions per card (hover shows 4 pills; touch shows on tap): **Pick** (ring glow, card lifts), **More like this**, **Less like this**, **Reject** (card dims and slides to the filmstrip). Keyboard 1–6 / P / M / L / R / N; live-region announces each action. 8\. Dock primary \= **Next round** with a count ("1 picked · 1 rejected"). Round 2+ cards appear with the same wipe; previous rounds sit in the filmstrip as thumbnails (real). No fabricated "convergence" meter in-session — only round number and the filmstrip.

**Phase 3 — Refine** 9\. Double-click or press Enter on a picked card ⇒ it **expands to the stage** (shared-element from the card's own origin); the others collapse to the filmstrip. 10\. **Edit by words**: the conversation rail input becomes *"Tell Vela what to change…"* (mic works too). Result \= 2 images beside the base with a **before/after drag slider** (rubber-band at the ends). Locked regions that were dropped show a small "kept (locked)" note from B's response. 11\. **Time dial** (dock): circular dial −30…+30 years with detent ticks and spring snap; presets "10 years later / earlier". **Disguise**: chips Beard · Moustache · Glasses · Headwear (toggle \= remove). **Profile**: 45° / 90° rotate handle. Every transform result gets an **amber "Speculative" stripe**, the identity-similarity bar, and `notes`; profile also shows "features not visible in the frontal view are invented". 12\. **Undo** (Cmd/Ctrl+Z) animates the attributes backwards (chips reverse FLIP).

**Phase 4 — Finalize** 13\. **Finalize** ⇒ progress ring around the face (indeterminate, elapsed seconds shown — finalize is a single call ≤ 25 s), Vela `thinking`; on success Vela `proud`, sparkle, the face unfolds to full-res (zoom/pan viewer; disclaimer footer permanent). 14\. **Export sheet** (glass, bottom): format tiles PNG · PDF · JSON, language select (6 UI languages for the PDF), "include alternates" toggle; on completion a **QR flash** and the file card with its short sha256. PDF text shows what will be inside (attributes \+ confidence \+ AI assumed \+ model versions). 15\. Optional **Possible leads** button (P1) ⇒ top-k cards with similarity bars and the standing disclaimer. Never the word "identified".

**Failure behaviour (all real, all friendly):** map `error.code` → Vela `wince` \+ bubble \+ one clear action (Retry / Switch model / Open System status). `LLM_UNAVAILABLE_LOCAL` shows "Local model is offline — start Ollama. This case never uses the cloud." with a teal shield.

### 6.6 Scene mode (`/sessions/:sid/scene`, P1)

Same shell: the stage becomes a `react-konva` canvas on a soft grid; entities are glass chips with icon \+ label; `unsure` ⇒ dashed outline \+ 60 % opacity; conflicting positions ⇒ ghost marker joined by a dashed line; timeline slider at the bottom animates `movement` with spring easing; badge "scale unknown — not to scale". Extract button \= the dock primary; Vela `sketching` while the LLM works. Export SVG/PNG/PDF with the disclaimer.

### 6.7 Trust Center (segmented control with sliding thumb)

- **Audit** (auditor/admin): the **hash chain**: horizontally scrolling virtualized strip of blocks (seq, action, short hash), links between blocks. **Verify integrity** ⇒ a light pulse travels block to block while the real `GET /audit/verify` request runs (the pulse is cosmetic, capped at 1.2 s; the real latency number is printed beside it). Valid ⇒ all links glow green, Vela `proud`, card shows `checked` and `head_hash`. Invalid ⇒ ambient flips to `alert`, the block at `first_bad_seq` shakes and turns red, all later links dim, Vela `alarm` (W4). Below: filterable table \+ CSV/JSON export.
- **Learning**: 4 chart cards (parser curve, verifier curve, convergence with-vs-baseline with CI bands, bias audit bars) that **draw on** when scrolled into view; each footnote shows run timestamp, `n`, and the §9.9 caveat; a null kind renders a Vela `sleepy` pose with "No run yet" — never a placeholder curve. A **glossary growth** sparkline (approved terms over time).
- **Glossary** (supervisor): **swipe stack** — each pending term is a card (term, language, proposed mapping, source sentence); drag right \= approve, left \= reject, with spring.momentum and rubber-band; buttons for keyboard users; approve shows "version g12-ab34cd" from the registry after the call returns.
- **Responsible AI**: five calm cards (What it is · What the AI assumed · How the audit works · Known limits · Bias findings linking to the bias-audit run).
- **System** (admin): service **orbs** that pulse (backend, ML, speech, Ollama, Gemini) from `/health`; **Test LLMs** runs `/health/llm-live` and animates two latency bars with the real numbers; below, models registry (activate) and users.

---

## 7\. THE GOLDEN PATH (maps 1:1 to the §17 demo script; ≤ 6 clicks from login to faces)

| Beat | Presenter action | UI response (real data only) | API |
| :---- | :---- | :---- | :---- |
| 0:00 | Landing → **Open Velora** → sign in | sheet morphs to Command Center | `POST /auth/login` |
| 0:20 | Click existing **DEMO-001** (pre-seeded for the demo) → purpose chip "Witness interview" | drawer, then Studio zoom-in | `GET /cases/{id}` |
| 0:30 | Tap mic, speak Tamil description, stop, **Send** | listening → thinking → chips fly; route badge | `/speech/transcribe`, `/statements` |
| 1:00 | **Show me faces** | six cards draw in, Vela sketching | `/rounds/generate` |
| 1:30 | Pick one, reject one, lock hair, **Next round** | round 2 draws in; filmstrip grows | `/feedback`, `/locks`, `/rounds/evolve` |
| 2:30 | Type "make the jaw a bit narrower" → compare slider; Time dial \+10; "without the beard"; profile 90° | speculative stripes | `/rounds/edit`, `/rounds/transform` |
| 3:15 | **Finalize** → **Export PDF** | proud Vela, QR flash | `/finalize`, `/exports` |
| 3:45 | Trust → Audit → **Verify** (green) → run tamper script → Verify (red) → restore | chain breaks visibly (W4) | `/audit`, `/audit/verify` |
| 4:15 | Switch to LOCAL-SIM-001, Wi-Fi off, send a statement | world turns teal, shield (W3) | `/statements` |
| 4:45 | Trust → Learning | charts draw on with real numbers | `/learning/dashboard` |

**Presenter HUD** (`Shift+P` or palette): a small glass panel with the *measured* latencies from real responses (ASR, translate, parse with provider/model, first image, round total, finalize). Real numbers impress judges and double as the honest-latency evidence. Off by default.

---

## 8\. MICRO-INTERACTION CATALOGUE (all with `spring.standard` unless noted)

- Buttons/cards: press scale .97 on pointer-down; hover lift 2 px \+ gradient border sweep.
- Chips: enter with scale .9→1 \+ opacity, stagger 60 ms; confidence ring animates between states.
- Sheets/drawers: slide \+ fade from their trigger; swipe-down/side to dismiss with rubber-band.
- Segmented controls & tabs: sliding thumb (`layoutId`).
- Toasts: bottom-center glass, auto-dismiss 4 s, Vela mini on the left; errors persist until dismissed.
- Skeletons: shimmer sweep 1.4 s; used only while real requests are in flight.
- Numbers (latencies, counts) count up with tabular figures.
- Cursor glow: a soft radial highlight following the pointer on glass surfaces (high tier only).
- Optional UI sounds: **off by default**, P2.

---

## 9\. STATES (never fake data)

| Situation | UI |
| :---- | :---- |
| Loading | skeletons / indeterminate ring with elapsed time |
| Empty | hero-size Vela \+ one-line explanation \+ one action |
| `AUTH_EXPIRED` | sheet "Session expired" over current page, keeps unsent text |
| `PURPOSE_REQUIRED` | purpose sheet |
| `ML_BUSY` | island shows "GPU busy — queued", automatic retry indicator |
| `ML_UNAVAILABLE` / `SPEECH_UNAVAILABLE` | wince \+ retry; text path stays available |
| `LLM_UNAVAILABLE_LOCAL` | teal banner, no cloud option offered |
| `LLM_SCHEMA_INVALID` | "Couldn't understand that — rephrase or edit manually" \+ manual attribute editing |
| Offline browser | shell still loads (service worker); status strip says so |

---

## 10\. ACCESSIBILITY, PERFORMANCE, OFFLINE

- Contrast: body text ≥ 4.5:1 (`text-3` is the floor for small text); focus ring 2 px `--a2` \+ offset; all controls keyboard-operable; dock and cards have roving tabindex.
- Live regions announce round progress, pick/reject, route badge changes, errors. axe-core: 0 critical/serious (TC5.6).
- Witness mode (§13 C11): one task per screen, hero Vela, giant mic, ≥ 48 px targets, officer panels and audit hidden, high-contrast option.
- Performance: initial JS ≤ 350 KB gzip; lazy-load Konva, Recharts, cmdk, PDF-related UI; images lazy; animate only `transform`/`opacity`; ≤ 3 glass layers; p95 frame time ≤ 20 ms in Studio with a 6-card grid on the C laptop (measure with the HUD's FPS readout).
- Offline: all fonts/icons/images bundled; no third-party requests; service worker caches the shell only (never API).

---

## 11\. DO / DON'T (tied to the master prompt)

**Do:** show provider/model/latency from real `llm` objects · keep the disclaimer ribbon on every image, always visible · label transforms Speculative · use "possible leads" · let the human confirm transcripts · keep pencil default · persist locks visibly. **Don't:** use stock or placeholder faces, fake charts, canned chat replies, scripted Vela lines not tied to a real event · call the browser `SpeechRecognition` API · use the words "identified" or "suspect found" · load anything from a CDN · hide the AI-assumed panel · let animation delay a real action (animation may play *after* data arrives, never gate it).

---

## 12\. BUILD ORDER INSIDE C's SCHEDULE (master prompt §10.1)

| Order | Work | Fits master step | Priority | Time box |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Tokens, fonts, glass utilities, motion tokens, `data-mode` switch | C2 | P0 | 45 min |
| 2 | `<AmbientBackground/>` (blobs \+ lines \+ tiers) | C2 | P0 (blobs) / P1 (lines, particles) | 60 min |
| 3 | Shells \+ routes \+ drawer/sheets \+ command palette | C2–C3 | P0 / palette P1 | 90 min |
| 4 | `<Vela/>` with 6 core states (idle, listening, thinking, sketching, wince, shield) | C4 | P0 | 75 min |
| 5 | Studio core: island, stepper, dock, inspector, chips FLIP | C4 | P0 | 120 min |
| 6 | Card grid with stroke-wipe reveal, filmstrip, actions | C5 | P0 | 90 min |
| 7 | Refine: expand transition, compare slider, Time dial, disguise/profile controls | C6 | P0 slider / P1 dial polish | 90 min |
| 8 | Finalize ring, export sheet, QR flash | C6–C7 | P0 | 45 min |
| 9 | Trust Center: audit chain \+ verify choreography | C8 | P0 | 90 min |
| 10 | Learning charts draw-on, glossary swipe stack, system orbs | C8 | P1 | 90 min |
| 11 | Remaining Vela states (curious, proud, alarm, sleepy), sparkles | C11 | P1 | 45 min |
| 12 | Presenter HUD, witness-mode polish, reduced-motion pass | C11–C13 | P1 | 60 min |
| 13 | Rive version of Vela, UI sounds, face-region hover overlay | — | P2 | only if idle |

Cut order when late: P2 → particles/cursor glow → Glossary swipe (use buttons) → Time dial polish (use slider) → palette. **Never cut:** disclaimer ribbons, route badge, AI-assumed panel, audit chain verify, reduced-motion support.

---

## 13\. ACCEPTANCE TESTS (extend §13 `TC` list; Playwright on the real stack)

- **TCD1** From `/cases` to six faces visible in ≤ 6 clicks (count in test).
- **TCD2** With `prefers-reduced-motion: reduce` emulated: no element has a non-`none` transform animation, all flows still pass.
- **TCD3** Opening a `real` case sets `html[data-mode="local"]` and the computed `--a1` equals the teal token; opening a `demo` case resets it.
- **TCD4** The disclaimer ribbon is visible (bounding box inside card, contrast ≥ 4.5) in states idle, hover, selected, loading-complete.
- **TCD5** Island text equals the latest response's `llm.provider`, `llm.model`, `route_reason` after a statement.
- **TCD6** During a full pass of the golden path, **every network request** is same-origin or the configured API base (no fonts/CDN/analytics).
- **TCD7** Initial JS bundle ≤ 350 KB gzip (build script prints and asserts).
- **TCD8** `/vela-lab` (dev) reaches all 10 states; a unit test asserts each real trigger maps to the right state (e.g. `ML_UNAVAILABLE` → `wince`).
- **TCD9** Audit tamper demo: after `tamper_demo.py --apply`, Verify shows the red block at `first_bad_seq` and `html[data-mode="alert"]`; after `--restore`, back to green.
- **TCD10** Visual regression screenshots (low tier, fixed viewport 1440×900) for Landing, Cases, Studio phases 1–4, Trust tabs; reviewed by the human.

**Human visual QA checklist (each person who can, before G4):** background never stutters while images stream · text readable over every glow · no layout jump when chips fly · dock magnification smooth · Tamil text renders · witness mode usable one-handed on a phone.

---

## 14\. PASTE-READY PROMPT FOR YOUR AGENT

> I'm working as Person C. Read `docs/MASTER_PROMPT.md` and `docs/FRONTEND_DESIGN.md`. The master prompt wins on conflicts; the design file defines the visual system, the four shells, the Vela character, the Studio flow and the build order (§12). Continue from my current step in `docs/progress/PERSON_C.md`, keep the existing landing page, and implement the design layer inside steps C2–C11 under the same gate protocol (tests listed, real output pasted, no mocks, no CDN assets). Start by auditing the current landing page against §3 tokens and §6.1 additions, tell me the gaps, then implement build-order items 1–3.

---

## 15\. SOURCES AND CAVEATS

- Huly's own marketing page exposes only a near-black theme color (`#090a0c`) and a line-texture background; richer values here (surface ladder, slate-blue accent family) are adapted from a reconstructed design-system summary of the Huly app and from our own choices — treat them as **inspiration, tuned by eye** against your landing page.
- Motion values (springs with `bounce 0` / `0.2` and `duration 0.4 s`, press scale `0.97` at 100 ms, rubber-band constant `0.55`, reduced-motion fallback) come from a published write-up adapting Apple's HIG for the web; Apple does not publish these as official web numbers.
- Performance tiers assume the demo browser runs on the i7 laptop's integrated GPU; measure on that machine, not a dev workstation.
