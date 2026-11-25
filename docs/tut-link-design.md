# Osiris ↔ Tut link — design (Phase 1)

Status: **DESIGN ONLY. Nothing in this document is built.** Build starts only on Tut's go-ahead.
Written against the installed tree at `~/Mark-LVII` (Python 3.12.16 venv, Gemini Live engine, Charon voice) and its `AGENTS.md`.

## 0. Roles and the one-line shape

| Who | Role |
|---|---|
| Tut | Boss. Decides, approves, spends. |
| Osiris (Mark 57) | The voice she talks to. Reads Tut state, takes notes. Nothing else. |
| Claude | Builder. Builds on this Mac. |
| Codex | Reviewer of the same shared source. |

**Shape:** Tut's repo and control centre stay the *only* source of truth. A small exporter on the Tut side writes read-only mirror files into one shared folder on the Mac. Osiris reads those mirrors. The only thing Osiris writes is an append-only inbox. Claude/Tut read the inbox. No second memory, no second dashboard.

Osiris never: replaces Claude, edits video, touches Flow, posts, contacts leads, invents prices, spends money.

---

## 1. What I checked in the installed code (these drive the design)

| Finding | Where | Consequence |
|---|---|---|
| A plugin is one file `plugins/<name>.py` with `PLUGIN` dict + `run(parameters, player=None, session_memory=None) -> str`. Never raise, return in seconds, treat `player` as maybe `None`. Auto-enabled when the file exists. | `AGENTS.md`, `plugins/_template.py`, `core/plugin_loader.py` | Phase 1 plugins are four files plus one `_tut_common.py` helper (leading `_` = loader skips it). |
| Plugins run on worker threads; UI only via `player.write_log` / `player.show_content`. | `AGENTS.md`, `ui.py:258,265` | All HUD output goes through those two calls. |
| Long background work belongs to the task engine (`core/tasks/`, `agents/*.md`), not a plugin. | `AGENTS.md` | Phase 1 plugins are file reads only. Anything slow later = a task agent. |
| Built-in memory `memory/long_term.json` is injected into the prompt at every connect (`main.py:1389`, ~900-char core) and searched by `recall_memory`. It is gitignored. | `memory/memory_manager.py`, `main.py:1389` | Osiris's own memory is a **second memory** and must not hold Tut facts (see §2.4). |
| `core/confirm.py` gives a confirmation **only the HUD can issue** (CONFIRM/CANCEL button, 90 s timeout). The model cannot forge it. | `core/confirm.py` | This is the gate for anything outward-facing. Spoken "yes" alone is *not* a gate (the model hears and relays it; it is forgeable). |
| The phone dashboard (`dashboard/server.py`) is a chat/log mirror: WebSocket message types `log`, `status`, `sys`, `wake`, `file_received`. There is no data panel. | `dashboard/server.py:1157+`, `dashboard/static/app.html:255-259` | Phase 1 shows Tut's day on the phone by sending text through `write_log`. A real panel is an optional later edit (§3.3). |
| `core.gemini` one-shot calls lead with a **Live** throwaway session (separate quota pool), then pinned REST text models (a 429 rests a rung 5 min), then the configured **sidecar provider** (`providers.sidecar`, `sidecar_first`). SEARCH is REST-only. | `core/gemini.py:83-200,618-760` | Tut's premise ("text quota dies before voice") is already half-handled for one-shots. |
| The **task engine** (`core/tasks/brain.py`) walks the Gemini REST ladder for tool-calling rounds and does **not** use the Live rung. | `core/tasks/brain.py:1-8` | This is where text quota actually bites. See §5. |
| `providers/` has: `llm_openai` (any OpenAI-compatible endpoint incl. local Ollama/LM Studio), `stt_whisper` (local or API), `tts_piper` (local, free), `tts_system` (macOS voice, free), `tts_elevenlabs` (needs key, paid tiers), `engine_pipeline` (STT → LLM → TTS). | `providers/*.py` | $0 rungs exist for hearing and speaking. A $0 text rung needs a local model, which is not installed. |
| There is **no Tut checkout on this Mac** — only `~/Downloads/tut-ai-company-phase1-*.zip` files. I did not unpack them. | `~/Downloads` | I do not know Tut's real file names or schemas. Every Tut-side field name below is marked **(confirm)**. |

---

## 2. MEMORY — one shared memory

### 2.1 Principle

Canonical Tut knowledge lives in **Tut's repo / control centre**. Osiris holds *no copy it can edit*. What Osiris sees are generated, read-only mirrors. What Osiris says by voice goes to an inbox only.

### 2.2 Shared folder

One folder, outside both repos so neither repo gets churn or accidentally commits her voice notes:

```
~/Tut-Shared/                      # override with env TUT_SHARED
├── mirror/                        # Tut side WRITES, Osiris READS. Osiris never writes here.
│   ├── rules.md                   # standing rules (exported from Tut's single rules source)
│   ├── facts.md                   # business facts: Quantum, Maxa, CreatesbyCairo, YouTube
│   ├── today.json                 # today's state: leads, replies, posts, approvals
│   └── jobs.json                  # named jobs: Jensen film, Ep6, Messenger Phase 2, …
└── inbox/                         # Osiris WRITES (notes.jsonl only). Tut side READS.
    ├── notes.jsonl                # append-only, one JSON object per line
    └── acks.jsonl                 # Tut side WRITES: which note ids were picked up
```

### 2.3 Files — exact direction

| File | Written by | Read by | Rule |
|---|---|---|---|
| `mirror/rules.md` | Tut-side exporter (Claude builds it) from Tut's one rules source **(confirm path)** | Osiris at every connect (injected) and `tut_brief` | Osiris never edits. Never hand-edited either — regenerate. |
| `mirror/facts.md` | Tut-side exporter | Osiris at connect (capped) | Prices appear **only** if Tut stated them. Absent = "not on file". |
| `mirror/today.json` | Tut-side exporter, from the control-centre sync (every 4 h) | `tut_brief`, `tut_leads`, connect-time digest | Carries `generated_at`. Osiris states the age. |
| `mirror/jobs.json` | Tut-side exporter | `tut_status` | Named jobs with state, last update, blocker. |
| `inbox/notes.jsonl` | **Osiris only** (`tut_note`) | Claude and Tut's pickup script | Append-only. Osiris never rewrites or deletes a line. |
| `inbox/acks.jsonl` | **Tut side only** | `tut_note` (to report "N notes not yet picked up") | Separate file so there is never two writers on one file. |
| `config/api_keys.json` | not touched | not touched | `AGENTS.md`: settings only via `memory/config_manager.py`. The link needs no setting. |
| `memory/long_term.json` (Osiris's own) | Osiris built-ins (unchanged) | Osiris | **Must not hold Tut facts** — see 2.4. |

Mirror writes are atomic (write temp file, `os.replace`) so Osiris never reads half a file. Missing or unreadable mirror → plugins say so plainly and return; they never guess.

### 2.4 Keeping two memories from drifting

Osiris already has a memory tool. If Tut says "Maxa's price is £X" the model could save that into `long_term.json` and it would sit there beside the Tut files and diverge. Mitigation, in order of strength:

1. The injected rules block says: *business facts, prices, decisions and notes go ONLY through `tut_note`; never save them with the memory tool.*
2. `tut_note` is the only documented path, so the model has a better tool for that intent.
3. Detection (cheap): the Tut-side exporter's weekly check lists anything in `long_term.json` that mentions Quantum / Maxa / CreatesbyCairo / Chrono Nexus / Tech Saga / Metta Loop, so drift is surfaced, not silent.

I cannot *technically* block the model from calling its memory tool without editing `main.py`; (1)–(3) reduce the risk, they do not eliminate it. **Stated limit.**

### 2.5 `notes.jsonl` line format

```json
{"id":"20261123T091502Z-7f3a","ts":"2026-11-23T09:15:02+00:00","kind":"decision",
 "business":"maxa","text":"<her words, verbatim as heard>","said_via":"voice",
 "status":"tut-stated-unverified","source":"osiris"}
```

- `kind`: `note | decision | price | task | question | approval_claim`.
- `business`: `quantum | maxa | cairo | youtube | general`; if unclear, `general` — Osiris asks one short question rather than guessing.
- `text` is stored verbatim; speech-to-text can mishear, so Osiris reads it back in one sentence before the write for `price`, `decision`, `approval_claim`.
- Timestamped in UTC with offset. One `os.write` on an `O_APPEND` fd under an advisory lock, line < 4 KB, so a crash can't leave a torn line.
- A `price` line is a record that **Tut said it**, not a verified price. Nothing downstream may publish it without the control-centre approval flow.

### 2.6 What Osiris reads before answering

At every Live connect, one injected block, **hard-capped at ~3,000 characters** (existing memory core is ~900, so session start stays fast):

1. `rules.md` in full (target ≤ 1,200 chars).
2. `facts.md`, capped (≤ 1,200 chars), newest-verified first.
3. A 4-line digest from `today.json` with its age ("as of 3 h ago").

Anything larger is fetched on demand by the plugins, not pasted in. If a mirror is missing the block says "Tut state unavailable" — and Osiris must then say so rather than improvise.

**This injection is the one Phase 1 change outside `plugins/`:** a small reader module (`core/tut_context.py`) plus ~3 lines in `main.py` where the system prompt `parts` are assembled (near `main.py:1389`). It needs Tut's explicit OK. If she declines, fallback: every Tut plugin reply opens with a one-line rules reminder — weaker (it only fires when a plugin is called).

---

## 3. DASHBOARD — Tut's day on the HUD and the phone

### 3.1 No second dashboard

The control centre (private URL, 4-hourly non-destructive sync, approvals queue) stays the dashboard. Osiris does **not** call that URL: that would put a credential and network access into Mark 57. The Tut-side exporter, which already has access, writes `mirror/today.json`; Osiris reads the file.

### 3.2 Morning brief — each item and its source

| Brief item | Source of truth | Exported as (confirm field names) | Osiris says |
|---|---|---|---|
| Leads (total, new since yesterday, hot) | Scout's shared leads table (`business_id`, `travel_enquiry` track) via control-centre sync | `leads.total`, `leads.new_24h`, `leads.hot[]`, `leads.by_business` | counts + names of hot ones; "Scout only finds, it contacts no one" if asked |
| Replies waiting | Maxa Messenger AI inbox (Phase 1 built) via control centre | `replies.waiting`, `replies.oldest_age_h` | count + age; never drafts or sends |
| Posts scheduled | control-centre content calendar (YouTube + socials) | `posts.scheduled[]` (`business`, `title`, `when`) | next few; never posts |
| Approvals needing her yes | control-centre approvals queue | `approvals.pending[]` (`id`, `title`, `business`, `kind`, `age_h`) | each by title; she approves in the control centre, not by asking Osiris |
| Staleness | sync metadata | `generated_at`, `sync_interval_h` | "as of 3 hours ago"; "stale" if older than 2 intervals (8 h) |

`hot` is defined **by the Tut side** (one definition, in the exporter). Osiris does not compute it.

### 3.3 Where it shows

- **HUD:** `tut_brief` calls `player.show_content("Tut — today", text)` (full detail) and returns a 3–5 line spoken summary.
- **Phone dashboard:** `dashboard/server.py` mirrors `write_log` lines to the phone as `log` messages, so the brief reaches the phone with **no change to the server or `app.html`**. It appears as chat text, not a panel.
- **Optional, later, needs approval:** a read-only `GET /api/tut/today` plus a small panel (edits `server.py` and `app.html`). Not recommended in Phase 1.
- **Existing startup briefing** (`morning_brief_enabled`, `core/routines`) is **untouched**. Phase 1 brief is on request ("brief me"). Auto-run at start-up is a later option, her call.

---

## 4. PLUGINS — Phase 1 (design only)

Common rules (from `AGENTS.md`): one file each, `PLUGIN` dict, `run(...) -> str`, never raise, return in seconds, `player` may be `None`, no Qt, no keys written. **None of the four calls a model.** They read files and format text, so they spend **zero** Gemini quota. All four share `plugins/_tut_common.py` (path resolution, atomic read, age formatting, the "say only this" return wrapper).

Return strings start with a marker the model is told to obey, same pattern as `core/confirm.py`'s `[CONFIRMATION_PENDING]`: e.g. `[TUT READ-ONLY — speak only these facts, add nothing]`. This is the guard against the voice model embellishing numbers.

### 4.1 `tut_brief`
- **Trigger:** "brief me", "what's my day", "morning brief".
- **Params:** none (optional `business`: quantum/maxa/cairo/youtube to narrow).
- **Reads:** `mirror/today.json`, `inbox/acks.jsonl` (count of unpicked notes).
- **Does:** builds the brief of §3.2 by template; `player.show_content(...)` for the full list, returns a ≤5-line spoken version with age.
- **Failure:** missing/old file → "I can't see Tut's state right now" + age of the last copy if any.
- **Writes:** nothing.

### 4.2 `tut_leads`
- **Trigger:** "how many leads", "any hot leads".
- **Params:** optional `business`, optional `track` (`travel_enquiry`).
- **Reads:** `mirror/today.json` → `leads`.
- **Returns:** counts and hot names. Read-only. Never contacts anyone; never offers to. Asked "email them?" → "Scout only finds leads; contacting anyone goes through you in the control centre."
- **Writes:** nothing.

### 4.3 `tut_note`
- **Trigger:** "note this", "remember for Tut", "the price is…", "I've decided…".
- **Params:** `text` (required), `kind`, `business`.
- **Does:** reads back price/decision/approval claims in one sentence, then appends one line to `inbox/notes.jsonl` (§2.5). Returns "Noted for Tut — [first words]" and the note id.
- **Writes:** `inbox/notes.jsonl` **only**. Plain internal file append: reversible, no outward effect, so no `core.confirm` needed (undo = Tut-side mark the id void; Osiris never deletes).
- **Failure:** folder missing or unwritable → says it was **not** saved and does not claim success (AGENTS.md: never report success without checking). It re-reads the last line after writing to verify.

### 4.4 `tut_status`
- **Trigger:** "status of the Jensen film", "where's Ep6", "Messenger Phase 2?".
- **Params:** `job` (required, free text).
- **Reads:** `mirror/jobs.json`; fuzzy-matches the name (`difflib`), asks if two jobs tie.
- **Returns:** state, last update time, blocker, who holds it. No match → "No record of that job" — never a guess.
- **Writes:** nothing.

### 4.5 Anything that sends, posts, publishes or spends (not in Phase 1)

No Phase 1 plugin does this. When one is ever added, it must follow this exact path:

1. Osiris **never executes** the action. It raises a **request**.
2. `core.confirm.request(key, title, detail, run)` puts CONFIRM/CANCEL on the HUD. Her **click** is the spoken-confirmation gate in practice: the model cannot press it. Her saying "yes" aloud is the conversation; the click is the proof. *(Deviation from "spoken confirmation": speech alone is forgeable by the model, so the HUD press is required alongside her voice.)*
3. On CONFIRM, `run()` does one thing only: append an **approval request** to `inbox/approval-requests.jsonl` (new file, Osiris-write / Tut-read) — it lands in the **same control-centre approvals queue** as everything else.
4. The action happens only when she approves it **there**. Osiris cannot close the loop.

### 4.6 Build order and checks (when approved)

1. `_tut_common.py` + `tut_note` first (smallest, the only writer), then `tut_status`, `tut_leads`, `tut_brief`.
2. Tut-side exporter + `mirror/` files (Claude, in the Tut repo, not here).
3. The one `main.py` injection (§2.6) — separately reviewable by Codex.
4. Verify with the repo's own `core/_smoke_harness.py` and `core/code_checks.py` (they scan `plugins/`), then a live voice test with a fixture `today.json`.
5. Codex reviews the same source before it is used for real.

---

## 5. PROVIDERS — degrade, don't die, $0-first

### 5.1 Facts that change the plan
- **Gemini Live stays the voice engine.** No change.
- Phase 1 plugins use **no model**. They cannot run out of quota.
- One-shot `core.gemini` calls already lead with Live, then REST models, then the sidecar provider.
- The **task engine** (`core/tasks/brain.py`) uses the REST ladder only → that is what runs dry first. Any Phase 2 background agent (research, drafting) inherits that risk.

### 5.2 Fallback ladder for background work

| Rung | What | Cost | Status |
|---|---|---|---|
| 1 | Live throwaway session (one-shots only) | $0 free pool | exists |
| 2 | Gemini REST models, rung rests 5 min after a 429 | $0 free tier | exists |
| 3 | **Sidecar provider** via `providers/llm_openai` pointing at a **local** model (Ollama / LM Studio) | $0 | **not installed**; needs her OK to install and a model that fits this Mac's RAM **(confirm RAM)** |
| 4 | **No-model mode:** answer from the mirror files by template only ("I can read your numbers but can't summarise or draft right now") | $0 | design only; Phase 1 plugins already behave this way |

Rungs that need a key or a bill — OpenAI, ElevenLabs, any hosted API — are **off** and stay off without her approval. Groq's free tier would be $0 but needs an account; also her call.

### 5.3 Voice ladder
Gemini Live → (if Live is down or exhausted) the existing `engine_pipeline` local mode: Whisper local (hearing) + sidecar LLM + Piper or macOS system voice (speaking). Piper and system TTS are free; Whisper local is free once its model downloads (install = her OK). ElevenLabs is excluded.

### 5.4 Osiris says so
Osiris says it plainly when it switches, e.g. *"I've switched to my backup brain — I can read your numbers but I can't draft right now."* Today `core.gemini` reports rung changes to the **console only** (`print`), not to speech or the HUD. So announcing needs one of:
- Phase 1: nothing to announce (no model calls).
- Phase 2: background agent results carry a first line naming the rung used; and a tiny hook that writes a `player.write_log` line when `core.gemini` skips a rung. That hook is a core edit → needs approval.

I have **not verified** whether `main.py` already voices a Live-model switch (the code near `main.py:2943` handles a quota error on the voice model); that gets checked before Phase 2.

### 5.5 No new paid provider, no new subscription, without her approval — written into the rules block (§6).

---

## 6. GUARDRAILS — the rules Osiris knows by heart

These go in `mirror/rules.md` (exported from Tut's single rules source) and are injected at every connect (§2.6). Wording for the block:

1. **Nothing public without Tut's exact go-ahead.** Osiris never posts, publishes, sends, schedules or replies publicly.
2. **Burmese copy:** only on her literal word **"Approved"**. Osiris cannot approve Burmese copy. A spoken "Approved" is logged as `approval_claim` (status unverified); the real approval is flipped only in the control centre.
3. **No invented prices, availability or confirmations.** If it isn't in `facts.md` or `today.json`: "That isn't on file."
4. **Scout never contacts anyone.** Find-only. Osiris never contacts a lead either.
5. **Business scope only:** Quantum Solutions, Maxa Holidays, CreatesbyCairo, YouTube (Chrono Nexus, Tech Saga, Metta Loop). Anything else: Osiris says it is outside scope.
6. **She uploads long videos from YouTube Studio herself.** There is no upload plugin. Osiris will not build or run one.
7. **Osiris never edits video, never touches Flow, never replaces Claude, never spends money.** No new paid provider or subscription without her approval.
8. **Business facts go only through `tut_note`.** Never into Osiris's own memory tool.
9. **Say the age** of any Tut state; say plainly when it is stale or missing.

---

## 7. PHASE LATER (parked, not built) — 3D printer for CreatesbyCairo

A `printer_control` plugin could let Osiris report on and start CreatesbyCairo print jobs over MQTT (printer status, job progress, queue). It is parked: MQTT adds a dependency not in `requirements.txt` (`AGENTS.md`: keep to those), it needs the printer's address and credentials stored through `memory/config_manager.py`, and *starting a print* is a physical, hard-to-reverse action that must go through the §4.5 request path (HUD confirm, then her approval) — read-only status could come first. Nothing is designed in detail until Phase 1 is proven.

---

## 8. Open items — I could not verify these, so I did not assume them

1. **Tut's real structure.** No checkout on this Mac; only zips I did not open. All `(confirm)` field/path names in §2–3 must be matched to the real repo before the exporter is written.
2. **Where Tut's single rules source lives** — `rules.md` must be generated from it, not typed twice.
3. **Burmese "Approved"** — confirm the intended mechanism (control-centre click/typed word vs. voice). Design assumes voice cannot approve.
4. **Hot lead definition** — Tut side, one place.
5. **Is a local LLM acceptable?** Needs her OK to install Ollama/LM Studio and a model sized to this Mac. Without it, rung 3 does not exist and degradation stops at rung 4.
6. **`~/Tut-Shared/` as the location** — her/Claude's choice; only the env var changes.
7. **The `main.py` injection (§2.6)** — the single non-plugin change in Phase 1. Needs her yes; fallback described.

## 9. Her go-ahead needed for

- [ ] Phase 1 as written (4 plugins + helper + `~/Tut-Shared/`)
- [ ] The one `main.py` injection (§2.6)
- [ ] Anything in §5 that installs software (rung 3, local Whisper model)
- [ ] Optional dashboard panel (§3.3)
