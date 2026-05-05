# Bahi Smart Capture v1.1 — Agent Handoff

> Companion to **bahi-smart-capture-vision-001-v0.1.md** and **bahi-smart-capture-spec-001-v0.1.md**. This doc covers the non-spec gaps: build, deploy, design tokens, persistence rules, hard rules, escalation protocol, and per-milestone gates.

---

## 1. Repo, build, deploy

* **Repo:** `github.com/NakliTechie/bahi`
* **Domain:** `bahi.naklitechie.com` (no change)
* **Single HTML file constraint stays intact.** All AI code lives in the existing `index.html`. No build step. No bundler. No external JS files in the repo.
* **CDN dependencies — additions over the existing list (sql.js, JSZip, jsPDF):**
  * `@huggingface/transformers` — pinned version, lazy-loaded only when AI master toggle is enabled
  * `paddle-ocr-wasm` — pinned, lazy-loaded only on first bill capture
* All CDN URLs use `cdn.jsdelivr.net`. Match the existing pinning style.
* Web Worker source for the inference worker is generated as an inline `Blob` URL (no separate worker file). Existing pattern in Bahi codebase if relevant; otherwise standard.

---

## 2. Browser floor

* **Chromium-only**, as today. Safari and Firefox already refuse Bahi at the door.
* **WebGPU primary, WASM fallback.** Feature-detect `navigator.gpu` once, on first load of the AI runtime, not at app boot.
* **GPU memory floor:** soft target 4 GB free. If the model fails to load due to OOM, the surfacing flow is in spec §5.6.

---

## 3. Design tokens and icons

### 3.1 Themes

All five existing themes (Crisp paper, Sakura wash, Asagi haze, Kinari washi, Sumi) must work for AI surfaces. The Capture modal, Settings → AI tab, slash-command pop-over, and voice waveform all theme-switch with the existing token system. No new theme tokens needed; reuse existing accent / border / surface tokens.

### 3.2 New icons

Hand-coded outline SVGs to match Bahi's existing icon style (no Lucide / Feather dependency — single-file constraint):

* `capture` — paperclip + sparkle for the Capture from bill button
* `mic` and `mic-off` — voice button states
* `mic-recording` — pulsing fill variant
* `sparkle` — small badge on AI-originated entries in lists (audit log, voucher lists)
* `ai-on` / `ai-off` — Settings master toggle
* `provider-{anthropic|openai|mistral|openrouter|local|custom}` — small mark beside each in the provider picker

Icon weight target: ≤ 6 KB total uncompressed for the AI additions.

### 3.3 Streaming / progress affordances

Reuse Bahi's existing progress ring (used today on save / backup). Add:
* A two-stage progress indicator for Capture (Reading → Extracting), inline in the modal.
* Tok/s + TTFT readout component, reused across Capture preview, slash-command pop-over, and voice transcription panel.

---

## 4. Empty and error states

| State | Trigger | Behaviour |
|---|---|---|
| AI off | Master toggle never enabled | No AI affordance visible anywhere |
| AI on, no provider configured | Master on, no provider selected | Settings → AI tab opens automatically with a banner *"Pick a provider to start"* |
| AI on, BYOK chosen, key missing | Provider = remote, key blank | Provider picker shows a red dot; AI buttons hidden until key added |
| AI on, local provider, model not downloaded | LocalMind selected, no model in OPFS | First click on any AI button opens download modal with size + caching note |
| Model downloading | Active download | All AI buttons show progress ring; clicking opens the same download modal with progress |
| Model load failed (file integrity) | SHA-256 mismatch | *"Model file integrity check failed. Please retry."* with [Retry] / [Cancel] |
| Model load failed (GPU OOM) | WebGPU OOM after one retry | *"This model is too large for your GPU. Try the smaller default, or switch to a remote provider."* with [Open Settings] |
| OCR returned nothing | PaddleOCR empty result | Capture modal: *"Couldn't read this document. The image may be too low-resolution."* with [Try another file] / [Open form blank] |
| LLM returned invalid JSON twice | After one retry | Empty form, raw OCR text in side panel for manual copy |
| BYOK 401 | Auth failure | *"Key rejected by {Provider}. Check Settings → AI."* with [Open Settings] |
| BYOK 429 | Rate limit | *"{Provider} rate limit hit. Wait a minute or switch provider."* |
| BYOK 5xx | Provider outage | One auto-retry, then *"{Provider} is unreachable. Try again or switch to LocalMind."* |
| Voice mic permission denied | `getUserMedia` rejected | Mic button switches to alert state; tooltip: *"Mic blocked — type instead."* |
| Voice transcription empty | Whisper output empty | *"No speech detected. Speak closer to the mic."* |
| User offline, local provider | `navigator.onLine === false` | Local provider works fully (everything cached). No banner needed. |
| User offline, remote provider | `navigator.onLine === false` | Buttons disabled with tooltip: *"Offline. Switch to LocalMind in Settings → AI to keep working."* |

---

## 5. Persistence rules

Where each piece of AI-related state lives. Hard rules, not preferences.

| State | Storage | Survives reload | In `.khata`? | In exports? |
|---|---|---|---|---|
| AI master toggle | `localStorage` | Yes | No | No |
| Active provider | IndexedDB (`aiPreferences`) | Yes | No | No |
| BYOK API keys | IndexedDB (`aiPreferences.providers.{name}`) | Yes | **NEVER** | **NEVER** |
| Per-provider model name | IndexedDB | Yes | No | No |
| Local model files | OPFS (`/bahi-ai/models/{id}/`) | Yes | No | No |
| AI prompt history | Not persisted at all | No | No | No |
| AI draft proposals (rejected) | Not persisted | No | No | No |
| OCR extracted raw text | Held in memory only during Capture | No | No | No |
| Bill image / PDF | `attachments/` in the `.khata` (existing path), only if user explicitly attaches before posting | Yes | Yes | Per existing rules |
| Audit-log actor = `'ai'` | Inside `books.sqlite` audit_log table | Yes | Yes | Yes |
| `aiAssisted: true` flag | Inside the audit_log entry payload (canonical JSON) | Yes | Yes | Yes |

### 5.1 Why API keys never enter the `.khata`

`.khata` files travel. They go to CAs, sync providers, USB drives, email attachments. An API key embedded in a file that travels is a credential leak waiting to happen. Layer 4 of the existing export-time identity check is extended (per spec §10) to scan for known key prefixes and hard-block exports if any are present.

### 5.2 Why prompts and rejected drafts are never persisted

Prompts contain user intent and often sensitive financial context. Persisting them adds attack surface and storage bloat for zero product benefit. The audit log captures the entry the user *accepted*, which is the only artefact that matters for forensic chain-of-custody.

---

## 6. CSP and security posture

* Lazy-load whitelist: `cdn.jsdelivr.net` (existing). Add `huggingface.co` for model downloads to OPFS — the runtime fetches model files from there. No other domains.
* BYOK calls go directly from the browser to the provider's API. The user is informed via the persistent banner (spec §4.3).
* No telemetry. No usage analytics. No model-load pings home. Same as the rest of Bahi.
* The audit-log canonical-JSON serializer must scrub any field whose key matches `apiKey`, `key`, `Authorization`, `x-api-key` (case-insensitive). This is a defense-in-depth sweep; the spec already prevents these from getting into payloads, but the serializer enforces it.

---

## 7. Accessibility

* Settings → AI tab keyboard-navigable end-to-end. Tab order: master toggle → provider picker → per-provider config → test connection → unload.
* Capture modal keyboard-navigable. Drop zone has a *Browse* button as an Enter-activatable focus target. Confidence flags are not colour-only — each has a text label.
* Slash command input is a single-line text input; standard form a11y.
* Voice button has visible state for *idle*, *recording*, *no permission*. Recording state is announced to screen readers.

---

## 8. Keyboard shortcuts and conflicts

The existing Bahi shortcut set (Tally parity F1–F10, plus Ctrl+Z, Ctrl+Shift+B, Ctrl+Shift+D, Ctrl+Shift+M, `?`) **must not** be touched. New shortcuts:

| Shortcut | Action | Context |
|---|---|---|
| `Ctrl+Shift+A` | Toggle AI master switch | Global |
| `/` (forward slash) | Open slash-command input | Inside any voucher form |
| `Esc` | Close slash-command pop-over / Capture modal | Pop-over / modal active |
| `Ctrl+Shift+V` | Start voice recording | Inside any voucher form, only when distil-whisper is loaded |

`/` only triggers when the focus is inside a voucher form's outer container, not when typing in any input field. The handler explicitly checks `event.target.tagName !== 'INPUT' && !== 'TEXTAREA'`.

---

## 9. README updates

Add a *Smart Capture* section after the existing *Features* section, structured the same way (sub-sections per milestone). Update *Known limitations* to remove the "no bank-statement auto-match" entry once v1.2 ships (don't remove at v1.1).

---

## 10. Portfolio integration

* Update `bahi.naklitechie.com` landing page with a *Smart Capture* fold below the existing demo walkthrough.
* Update `naklitechie.github.io` Bahi tile with a small AI badge.
* No update to the demo walkthrough itself at v1.1.0; revisit at v1.1.2 when all three milestones are live.

---

## 11. What NOT to do — hard rules

These are non-negotiable. Crossing any of them is grounds for stopping and escalating to the owner.

1. **Never auto-post.** No code path may call the posting bridge directly from an AI-extraction result without the user clicking the existing form's Post button.
2. **Never bypass posting bridges.** AI-originated drafts go through the same `postInvoiceToLedger`, `postPurchaseToLedger`, `postEntry` etc. as manual entries. No new posting code paths.
3. **Never store BYOK keys outside IndexedDB.** Not in `localStorage`, not in `.khata`, not in exports, not in audit log payloads, not in error messages, not in console logs.
4. **Never load AI runtime at app boot.** Lazy-load only when the master toggle is enabled. Bahi's first-load time stays as-is for users who don't use AI.
5. **Never log AI prompts to the audit log.** Only the resulting accepted entry is logged, with `actor='ai'`.
6. **Never silently auto-create master rows from AI extraction.** Missing vendors / customers / items prompt the user to add them via the existing master form.
7. **Never let AI write SQL or JS directly.** All AI output is structured JSON validated against schemas. No code generation, no query construction.
8. **Never silent-fallback from BYOK to LocalMind.** If the BYOK provider fails, surface the error and let the user decide. Don't auto-route around it.
9. **Never let AI propose into a locked period without the existing amendment flag firing.** Period locks apply to AI same as manual.
10. **Never upload anything to any third party other than the user-configured BYOK provider.** No telemetry, no model-server health pings, no usage analytics.
11. **Never modify the existing snapshot-at-posting pattern.** Snapshots freeze company / customer / state / HSN / account names at post time, AI-originated or not. Same rule, no exceptions.
12. **Never embed model files in the `index.html`.** Single-file constraint applies to the *app shell*; model weights live in OPFS, fetched on demand. Embedding multi-megabyte ONNX in the HTML is not single-file discipline, it's hostage-taking.

---

## 12. Escalation protocol

The agent proceeds autonomously on naming, implementation choices, debugging, tuning, trying alternatives. **Stop and escalate to the owner only when:**

* A locked decision in the spec or vision conflicts with reality discovered during build.
* A new dependency is needed beyond what's listed in §1.
* A genuine product-scope ambiguity emerges that the existing docs don't resolve.
* The four open items in spec §12 trigger.
* Any of the hard rules in §11 cannot be honored as written for a technical reason.

For everything else — model parameter tweaks, prompt iteration, JSON schema refinements within voucher types, UI micro-affordances, error-message wording, performance tuning — proceed.

---

## 13. Per-milestone gates

Each milestone ships only after its gate artefact passes. The agent generates the gate artefact and presents it for owner sign-off before deploy.

### v1.1.0 gate — Bill ingest

A short video or screenshot sequence showing:
1. Settings → AI enabled, LocalMind selected, Llama 3.2 1B downloaded.
2. **+New purchase** form opened, Capture from bill clicked.
3. A sample vendor bill (PDF) dropped into the Capture modal.
4. Two-stage progress completes; extraction preview shown side-by-side with bill.
5. **Use this** clicked; form pre-filled with all extracted fields.
6. Form posted via existing Post button.
7. Audit log inspected via Debug Console; the new entry shows `actor='ai'`.

Plus: pytest suite passing with the new actor-tag tests.

### v1.1.1 gate — Text-to-entry

A sequence per voucher type (Sales / Purchase / Receipt / Payment / Journal / Contra):
1. Voucher form opened, `/` pressed, natural-language entry typed.
2. Slash-command produces a structured draft.
3. Form pre-fills correctly.
4. Posted via existing Post button.
5. `actor='ai'` confirmed in audit log.

Plus: a period-lock test showing the slash command hits the amendment flag for a locked period.

### v1.1.2 gate — Voice

1. Voice button clicked, English audio recorded.
2. Distil-whisper transcribes correctly to the slash-command input.
3. User edits transcript, hits Enter, text-to-entry pipeline produces a draft.
4. Posted via existing Post button.
5. Mic permission denied test: button shows alert state correctly.

---

## 14. Definition of done for v1.1

* All three milestones gated and signed off.
* README *Smart Capture* section live.
* `khata-format.md` updated with `actor='ai'` and `aiAssisted` field (mirrors whatever the upstream khata-standard PR lands as).
* Schema version bumped to 10.
* Migration runner has the v9→v10 noop migration.
* All existing 45 pytest tests still pass.
* New tests added for: AI actor tagging, `aiAssisted` flag in CA mode, hash chain integrity across AI-mixed sessions, `.khata` round-trip preserving actor values, BYOK key never-in-export check.
* Settings → AI tab works in all five themes.
* Master toggle off restores the v1 experience byte-for-byte for users who never enable AI.
* No CDN URL changes for users who keep AI off.
* `bahi.naklitechie.com` deployed; portfolio landing updated.
