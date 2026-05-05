# Bahi Smart Capture v1.1 — Specification

> Companion to **bahi-smart-capture-vision-001-v0.1.md**. This spec covers v1.1 only. v1.2 (Reconciliation Match) will get its own spec when v1.1 ships.

Milestones split inline:
* **v1.1.0** — Settings → AI tab + LLM primitive + Bill ingest from +New purchase
* **v1.1.1** — Text-to-entry slash command on all voucher forms
* **v1.1.2** — Voice-to-entry on top of the same pipeline (English only)

Same URL (`bahi.naklitechie.com`), same single HTML file, three deploys.

---

## 1. Settings → AI tab

A new tab in the existing Settings modal, to the right of the existing tabs. Visible only after the user toggles the master AI switch on.

### 1.1 Master toggle

* **Setting:** `bahi.ai.enabled` in `localStorage`. Boolean. Default `false`.
* **First-enable flow.** Turning the toggle on for the first time opens a confirmation modal: *"Smart Capture downloads a small AI model the first time you use a feature. The model stays on this device. Books never leave your computer unless you connect a remote provider in Settings → AI."* [Enable] [Cancel].
* **Disabling** hides every AI affordance from the UI immediately. Loaded models are unloaded. Settings preserved.

### 1.2 Provider picker

A dropdown listing:
* **LocalMind (on-device)** — default
* **Anthropic (BYOK)**
* **OpenAI (BYOK)**
* **Mistral (BYOK)**
* **OpenRouter (BYOK)**
* **Custom (OpenAI-compatible)** — exposes base URL + model name + key fields

The selected provider is the *default* for all AI features. Per-feature override is not in v1.1 scope.

### 1.3 Per-provider configuration

For BYOK providers:
* API key (password-masked input, eye-toggle for reveal)
* Model name (combobox with provider's published model list pre-filled, free text allowed)
* Base URL (only for *Custom*; other providers hard-code their canonical URL)
* **Test connection** button — single `chat()` call with `"ping"`, success toast or red error message inline

For LocalMind:
* Model picker — combobox listing the registered local models (see §3)
* Active backend readout (WebGPU / WASM, capabilities)
* **Unload model** button (frees GPU memory immediately)

### 1.4 Storage

* `bahi.ai.enabled` — `localStorage`
* `bahi.ai.provider` — `IndexedDB`, key `aiPreferences`
* `bahi.ai.providerConfig` — `IndexedDB`, per-provider sub-keys; **API keys live here only**, never in `localStorage`, never in `.khata`, never in any export.
* `bahi.ai.localModel` — `IndexedDB`, currently selected local model id

### 1.5 Capability badges

The provider picker shows a small badge next to each provider indicating its capabilities for the active model: `text` / `vision` / `tools`. Capability is queried via `llm.capabilities()` after model load.

When a provider lacks a capability needed for a feature, the feature's button is hidden (not disabled-and-greyed). For example: if the user picks an Anthropic model that supports vision but their local model doesn't, the *"Capture from bill"* button shows when Anthropic is the active provider and is hidden when LocalMind is active and the local text model is loaded. PaddleOCR is local-only and capability-flagged separately.

---

## 2. The LLM primitive

```js
class LLM {
  async loadModel(config)
  async chat(messages, options)   // { stream, maxTokens, json, schema }
  async embed(texts)
  capabilities()
  async unload()
}
```

### 2.1 Behaviour

* `chat()` supports a `schema` option for grammar-constrained JSON output. Local adapter uses the underlying runtime's grammar/JSON-mode support; remote adapter uses each provider's structured-output mechanism (Anthropic tool-use shape, OpenAI `response_format: json_schema`, etc.). Returns the parsed object, not a string.
* `chat()` `stream: true` yields tokens for UI streaming. `stream: false` returns the full response.
* `embed()` is local-only. Remote adapter throws `NotSupported`. Caller is responsible for falling back to the local embedding model (used only by v1.2).
* `capabilities()` returns synchronously after `loadModel` has resolved. Shape: `{ text: bool, vision: bool, tools: bool, embedding: bool, backend: 'webgpu'|'wasm'|'remote', maxTokens: int }`.
* `unload()` is idempotent.

### 2.2 Adapter selection

A thin factory: `getActiveLLM()` reads the provider preference from IndexedDB and returns the configured adapter. Single call site for every AI feature.

---

## 3. Local provider — Transformers.js + ONNX

### 3.1 Model registry

| ID | Display name | Repo | Quant | Size | Role | Default |
|---|---|---|---|---|---|---|
| `llama-3.2-1b-it` | Llama 3.2 1B Instruct | `onnx-community/Llama-3.2-1B-Instruct-ONNX` | q4 | ~700 MB | Text / structured | ✅ |
| `qwen-2.5-1.5b-it` | Qwen 2.5 1.5B Instruct | `onnx-community/Qwen2.5-1.5B-Instruct-ONNX` | q4 | ~900 MB | Text / structured | — |
| `paddle-ocr-wasm` | PaddleOCR | (pinned WASM build) | — | ~50 MB | OCR | bundled with ingest |
| `distil-whisper-small` | Distil-Whisper Small | `onnx-community/distil-whisper-small-en-ONNX` | int8 | ~150 MB | Voice (v1.1.2) | bundled with voice |
| `all-minilm-l6-v2` | all-MiniLM-L6-v2 | `Xenova/all-MiniLM-L6-v2` | fp16 | ~22 MB | Embeddings (v1.2) | not loaded at v1.1 |

* Models are **never** preloaded at app boot. They lazy-fetch on first use.
* Each model is downloaded chunked, streamed to OPFS at `/bahi-ai/models/{id}/`, SHA-256 verified per file. SHA-256 sums are hard-coded in the registry; mismatch hard-fails with *"Model file integrity check failed. Please retry the download."* and a Retry button.
* Switching the active local model in Settings unloads the prior model, then loads the new one. Other AI buttons are disabled-with-spinner during the swap.

### 3.2 Runtime

* **Web Worker.** All inference runs off the main thread. Worker file is generated inline as a Blob URL (no separate file — single-HTML-file constraint).
* **WebGPU primary, WASM fallback.** `navigator.gpu` feature-test on first load. If WebGPU unavailable, model loads with `device: 'wasm'` and a yellow banner appears in Settings → AI: *"Running on WASM. Inference will be slower. WebGPU requires a recent Chromium."*
* **GPU OOM handling.** `loadModel` catches OOM, attempts retry at lower batch size once, then surfaces *"This model is too large for your GPU. Try the smaller default, or switch to a remote provider."*
* **Tok/s + TTFT readout.** Inline below the chat-style streaming UI in any AI surface (Capture preview, slash-command pop-over, voice transcription panel).

### 3.3 Lazy fetch from CDN

* `transformers.js` is lazy-loaded from `cdn.jsdelivr.net` only when the master AI toggle is enabled, never at app boot. Matches Bahi's existing sql.js / JSZip / jsPDF pattern.

---

## 4. Remote BYOK provider

A single adapter file. Provider differences handled by config, not by separate adapter classes.

### 4.1 Provider config shape

```js
{
  baseUrl: "https://api.anthropic.com/v1/",
  authHeader: "x-api-key",
  authPrefix: "",
  model: "claude-haiku-4-5",
  jsonMode: "anthropic-tools",   // or "openai-jsonschema"
  visionMode: "anthropic-image"  // or "openai-image-url"
}
```

Pre-filled configs ship for Anthropic, OpenAI, Mistral, OpenRouter. *Custom* exposes all fields.

### 4.2 Network discipline

* Every BYOK call is a `fetch()` from the main page (no proxy). User's network sees the call; this is documented in Settings → AI as *"BYOK calls leave your browser and go directly to the provider you chose."*
* Timeout: 60s default, 120s for vision calls. Configurable per provider in *Custom*.
* Retries: one retry on 5xx with 2s backoff. No retry on 4xx.
* Errors surface inline in the AI panel, never in the audit log.

### 4.3 Privacy posture

A persistent banner shows in any AI surface when the active provider is remote: *"Smart Capture is using {Provider}. Bill content and entry text are sent to {Provider} for this session."*

---

## 5. v1.1.0 — Bill ingest

### 5.1 Trigger

A new button **"📎 Capture from bill"** in the **+New purchase** form, top-right, next to the existing form actions. Visible only when AI is enabled and the active provider has either local OCR + text or remote vision capability.

### 5.2 Capture flow

1. User clicks **Capture from bill**.
2. Modal opens with a drop zone: PDF, JPG, PNG, multi-page accepted. Up to 10 MB per file at v1.1.0.
3. On drop: progress ring around the dropped file thumbnail. Two stages of progress are shown:
   * Stage 1 — *Reading* (OCR or vision): PaddleOCR for local; single vision API call for remote.
   * Stage 2 — *Extracting* (LLM structuring): the OCR text + a fixed system prompt go to the active text LLM with a strict JSON schema (see §5.4). For remote-vision providers, stages 1 and 2 collapse into one call.
4. On extraction success: the modal shows the extracted fields side-by-side with the original document preview, with a confidence indicator per field (low / medium / high).
5. User clicks **Use this** → modal closes, the **+New purchase** form is pre-filled with the extracted values. The user reviews and posts via the existing posting bridge.
6. On any failure: extraction modal shows the partial extraction with a banner *"Couldn't extract everything. Fill the rest manually."*. User can still **Use this** with whatever was extracted.

### 5.3 Hard rule

The user always sees the **+New purchase** form before posting. Capture never auto-submits.

### 5.4 Extraction schema

```json
{
  "vendor": {
    "gstin": "string|null",
    "name": "string",
    "state_iso": "string|null"
  },
  "bill": {
    "number": "string",
    "date": "YYYY-MM-DD",
    "place_of_supply_iso": "string|null"
  },
  "lines": [
    {
      "description": "string",
      "hsn_or_sac": "string|null",
      "qty": "number|null",
      "rate": "number|null",
      "taxable_value_paise": "integer",
      "gst_rate_pct": "number",
      "cgst_paise": "integer",
      "sgst_paise": "integer",
      "igst_paise": "integer"
    }
  ],
  "totals": {
    "taxable_paise": "integer",
    "cgst_paise": "integer",
    "sgst_paise": "integer",
    "igst_paise": "integer",
    "total_paise": "integer"
  },
  "rcm_applicable": "boolean|null"
}
```

### 5.5 Snap-to-master logic

After extraction, before pre-fill:
1. **GSTIN snap.** If `vendor.gstin` matches an existing vendor master row, all vendor fields are replaced with the master values. Vendor name extracted by AI is discarded.
2. **State derivation.** `place_of_supply_iso` is derived from the vendor's GSTIN if not extracted; intra/inter-state routing then follows existing engine rules.
3. **HSN normalisation.** Each line's `hsn_or_sac` is checked against the bundled HSN dataset; if the AI extracted `8517 12 90` and the master entry is `85171290`, the master value wins.
4. **Rounding.** All `_paise` fields are integers per Bahi's existing rule. Float arithmetic from the LLM is rejected; values that don't round cleanly trigger a low-confidence flag on that field.

### 5.6 Failure paths

| Condition | Behaviour |
|---|---|
| Model not yet downloaded | First-use modal explains size + that model stays cached. User can cancel. |
| Model download interrupted | Existing chunked-resume from the OPFS partial. |
| OCR returns empty | Modal shows: *"Couldn't read this document. The image may be too low-resolution. Open the form blank?"* with [Open form] [Try another file] |
| LLM returns invalid JSON | One retry with stricter system prompt. On second failure: empty form with extracted raw OCR text shown in a side panel for the user to copy from. |
| GST totals don't reconcile | The line items render with a yellow banner: *"Tax totals don't add up. Review before posting."* — but the form is still populated. |
| GSTIN format invalid | Field rendered red; user fixes in the form. |
| Backend network failure (remote BYOK) | Inline error: *"Couldn't reach {Provider}. Check your key or switch to LocalMind in Settings → AI."* |

---

## 6. v1.1.1 — Text-to-entry

### 6.1 Trigger

A small **`/`** affordance in the top-right of every voucher form: Sales / Purchase / Receipt / Payment / Journal / Contra / Credit Note / Debit Note. Clicking opens a single-line text input. Keyboard shortcut: `/` while focused on the form.

### 6.2 Pipeline

1. User types or pastes natural-language description.
2. Hitting Enter sends to `chat()` with:
   * **System prompt** — voucher-type specific, includes the JSON schema for that voucher type.
   * **Context block** — pre-built per-form: chart of accounts (just the codes + names + types), the most recent 50 vendors and 50 customers, the open invoices for receipt allocation, the active period locks, the current FY, the current company name + GSTIN. Roughly 4-6K tokens depending on master sizes; if the chart of accounts is very large, only the leaf accounts are sent.
   * **User input** — the raw text.
3. LLM returns structured JSON matching the voucher's schema.
4. JSON is validated against the schema; on pass, the form is pre-filled.
5. User reviews and posts.

### 6.3 Voucher-specific schemas

Each voucher type has its own draft schema. Receipt schema includes invoice-allocation hints. Payment schema includes TDS section/rate hints (looked up from vendor master after vendor snap). Journal schema enforces Dr = Cr at the LLM level (system prompt explicit) and the existing engine's hard balance assertion catches any drift.

### 6.4 Hard rules

* **Period-lock check fires before pre-fill.** If the proposed entry date falls in a locked period for the relevant return type, the form opens with the existing amendment flag set. Same as a manual entry.
* **AI cannot create master rows.** If the entry references a vendor / customer / item not in the master, the slash-command pop-over surfaces a *"This vendor isn't in your master yet — add it first?"* prompt that opens the master form. AI never silently auto-creates.
* **Account routing is validated, not trusted.** AI proposes account codes; the existing posting engine validates them against the chart of accounts at post time. Invalid codes raise a form error.

---

## 7. v1.1.2 — Voice-to-entry

### 7.1 Trigger

A 🎤 mic button next to the slash-command input. Visible only when distil-whisper is downloaded (or available in browser cache).

### 7.2 Pipeline

1. User clicks mic → microphone permission prompt (browser-native).
2. Recording starts; visible waveform, max 60s.
3. User clicks again to stop.
4. Audio runs through distil-whisper-small in a Web Worker → English transcript.
5. Transcript is editable in the slash-command input before submission.
6. User hits Enter → text-to-entry pipeline (§6) takes over.

### 7.3 Scope

* English only. The voice button is hidden if the browser's UI language is set to a non-English locale and the user hasn't explicitly enabled English voice in Settings → AI. (This avoids confusing users who would otherwise expect Hindi voice to work.)
* Hindi voice is explicitly out of scope at v1.1.2. The tracking note lives in the vision doc.

---

## 8. Audit-log integration

### 8.1 Actor tagging

The existing `actor` field on `audit_log` rows takes a new value: `'ai'`. (The `origin` column is unchanged — it stays as `window.location.origin` for cross-origin tamper detection.) Combined with CA mode, the rule is:

| Mode active | Actor written |
|---|---|
| Owner mode, manual entry | `'owner'` |
| Owner mode, AI-assisted entry user accepted | `'ai'` |
| CA mode, manual entry | `'ca'` |
| CA mode, AI-assisted entry CA accepted | `'ca'` with `aiAssisted: true` in the payload |

The `auditActor()` helper from CA mode is extended to take a second argument indicating AI-assist. The hash chain doesn't care; the value is part of the canonical-JSON payload that gets hashed.

### 8.2 What is *not* logged

* The user's natural-language prompt text.
* The AI's draft proposals before user acceptance.
* OCR extracted text from bills (the bill itself is saved to `attachments/` per the existing flow if the user attached it; the OCR string is discarded after pre-fill).
* Any BYOK key, ever.

### 8.3 Round-trip test

The existing 45-test pytest suite gets new tests:
* AI-originated entries write `actor='ai'` correctly.
* Hash chain verifies across mixed-actor sessions.
* CA mode + AI yields `actor='ca'` + `aiAssisted=true`.
* `.khata` round-trip preserves all actor values.
* No BYOK key ever appears in any field of the saved file.

---

## 9. khata-format updates

`khata-format.md` gets a single addition under the `audit_log.actor` enum:

> `'ai'` — entry was drafted by an AI suggestion and accepted by the user. Combined with `'ca'` actor entries, the boolean `aiAssisted` may appear in the entry payload to mark AI-assisted CA actions.

`meta.schemaVersion` bumps from `9` to `10`. The migration runner adds an idempotent migration that does nothing structural (actor enum is open-string in the SQLite DDL, not CHECK-enforced); the bump exists so older app versions encountering a file with `'ai'` actors read it cleanly via the existing newer-files-open-read-only banner.

Because `khata-format.md` is the local copy of the spec maintained at `github.com/NakliTechie/khata-standard`, the upstream change is proposed via a gentle, advisory PR; whatever shape the maintainer accepts is what Bahi mirrors locally.

---

## 10. Failure model additions

Extending the table in Bahi's main README:

| Scenario | Protection | What the user sees |
|---|---|---|
| AI proposes invalid account routing | Existing posting bridge validates account codes at post time | Form error highlighting the invalid line; user fixes |
| AI proposes wrong GST split (intra vs inter-state) | Existing engine recomputes the routing from `place_of_supply_iso` at post time, ignoring AI-proposed CGST/SGST/IGST split when it disagrees | Form re-renders with corrected split before user clicks Post; small badge "GST split corrected" |
| BYOK key leaks via export | Layer 4 export-time identity check is extended to scan exports for any field matching stored API key prefixes (Anthropic, OpenAI, etc.) | Export hard-blocks if a key string appears anywhere in the export blob |
| User on remote BYOK loses internet mid-Capture | One retry, then surface error; bill content is held in memory only, not written to disk | "Couldn't reach {Provider}. Switch to LocalMind or retry?" |
| Local model file corrupted | SHA-256 verify on every load | Re-download prompt; existing OPFS chunked-resume |
| User deletes BYOK key from Settings | Active provider falls back to LocalMind | Banner: "Provider {X} key removed. LocalMind is now active." |

---

## 11. Out of scope at v1.1

* Auto-posting in any form.
* Agent loops or multi-step tool use.
* GST anomaly LLM checks (deterministic rules already cover this).
* Tally mapping LLM suggestions for non-standard groups.
* Hindi or Hinglish voice.
* Conversational ledger query / text-to-SQL.
* Narrative report commentary.
* HSN/SAC AI suggestion in item master.
* Fine-tuning or LoRA over Indian bill formats.
* CA observation drafting.
* AI-assisted reconciliation match (this is v1.2; embedding-only, no LLM).

---

## 12. Open items the agent should flag, not decide

These are the only places the agent must stop and ask:

1. If Llama 3.2 1B on q4 turns out to produce malformed JSON more than ~5% of the time during dev testing, the alternate Qwen 2.5 1.5B may need to become the default. **Flag for owner; do not switch silently.**
2. If PaddleOCR-WASM has a deployment issue (license, bundle size, browser support gap), surface to owner with the alternative being SmolDocling-256M. **Do not pick the alternative without owner confirmation.**
3. If the JSON schemas in §5.4 / §6.3 turn out to be insufficient for any voucher type during build, flag with the specific gap. **Do not extend the schemas unilaterally.**
4. If `aiAssisted: true` collides with an existing audit-log payload field name, flag.
