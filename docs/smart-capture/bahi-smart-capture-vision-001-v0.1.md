# Bahi Smart Capture — Vision

> *AI inside Bahi, with the same forensic posture as the rest of the file.*

This doc covers Bahi v1.1 (Smart Capture) and v1.2 (Reconciliation Match). It is a supplement to the existing Bahi v1 — the engine, posting bridges, snapshot pattern, audit chain, and `.khata` format are unchanged. AI is bolted onto the existing surface, never around it.

---

## Why AI in Bahi at all

Bahi already proves that a serious accounting product can run from a single browser file with no server. AI is the obvious next layer if — and only if — it inherits the same posture.

The three places AI earns its keep:

1. **Vendor bill ingest.** Indian SMBs receive bills as PDFs, scanned images, and WhatsApp photos. Today, every purchase line is keyed in by hand. AI gets the form 80% pre-filled before the user reviews.
2. **Text-to-entry.** Power users want to say *"paid 50,000 to Sharma Auto by RTGS on 12 Apr"* and have a vendor payment voucher draft appear with TDS computed, account routing decided, and the entry waiting for one final click.
3. **Bank reconciliation match.** The single largest known limitation in v1's manual matcher. Embedding-based fuzzy match between statement narration and ledger entries closes it without any LLM at all.

Everything else AI could do in Bahi (GSTR-1 anomaly checks, Tally mapping suggestions, fraud detection) is better served by the deterministic rules already in the engine. AI does not get to dress up as policy.

---

## What ships at v1.1

**Smart Capture** — three features, one settings surface, one runtime contract.

* **v1.1.0** — Bill ingest. *"Capture from bill"* button inside the existing **+New purchase** form. PDF / image upload, OCR + extraction, form pre-filled, user reviews, user posts.
* **v1.1.1** — Text-to-entry. Slash command on every voucher screen (Sales / Purchase / Receipt / Payment / Journal / Contra). Natural-language input → structured draft → pre-filled form → user posts.
* **v1.1.2** — Voice-to-entry. Mic button feeds the same text-to-entry pipeline through distil-whisper-small. English only at this milestone.

All three milestones share the same Settings → AI tab, the same model registry, and the same draft-then-review contract.

## What ships at v1.2

**Reconciliation Match.** The bank reconciliation screen gains an *Auto-match* button. Embedding similarity (all-MiniLM-L6-v2, 22 MB) on statement narration vs. payment-side ledger entries, plus amount + date heuristics, produces ranked match suggestions with confidence scores. User clicks to accept. No LLM. Closes the v1 known limitation cleanly.

---

## What this is not

* **Not auto-posting.** AI never writes to the ledger directly. Every AI-originated entry is a draft populated into the existing voucher form. The user reviews, the user clicks Post, the existing posting bridge fires. The balance assertion, snapshot capture, and audit-log entry happen exactly as they do for a manually-keyed entry.
* **Not an agent.** No tool-use loops, no autonomous multi-step reasoning, no AI-driven workflow orchestration.
* **Not GST anomaly detection.** Routing rules stay deterministic.
* **Not Tally mapping suggestions.** The existing 25+ standard-group auto-mapper is enough; user-created groups stay as a hard-block.
* **Not Hindi voice.** Parked — see *Roadmap* below.
* **Not on by default.** Settings → AI is off until the user enables it. The first time they do, the existing model-download modal explains size, that the model stays cached, and that the local model runs offline after first download.

---

## Architecture

Smart Capture inherits LocalMind's runtime abstraction wholesale. Bahi is the third consumer (after LocalMind itself and Mahalla v1.1), which gives the abstraction a useful third stress test.

### The LLM primitive

Five methods, identical to LocalMind / Mahalla / Foliant:

```js
class LLM {
  async loadModel(config)        // local: download + WebGPU/WASM init; remote: noop
  async chat(messages, options)  // streaming or batched; returns text or grammar-constrained JSON
  async embed(texts)             // local only; remote adapter throws → caller falls back to local
  capabilities()                 // { multimodal, tools, embedding, backend, vision }
  async unload()                 // local: free GPU memory; remote: noop
}
```

### Two adapters from day one

* **LocalMind adapter.** Transformers.js + ONNX Runtime Web + WebGPU, WASM fallback. Web Worker offload. OPFS streaming cache with SHA-256 verify per file. Model disposal on switch. The full VaultMind/LocalMind loading-UX inheritance — progress ring, tok/s + TTFT readout, capability gates that hide UI when the model can't do a task.
* **Remote BYOK adapter.** One adapter for Anthropic, OpenAI, Mistral, OpenRouter, and any OpenAI-compatible endpoint. Per-provider base URL + model name + API key. Stateless.

Forcing both adapters through the same interface from day one prevents local-specific assumptions leaking into the contract — the same lesson Mahalla v1.1 enforced.

### Model registry at v1.1

| Slot | Default | Alternate | Size (q4) | Why |
|---|---|---|---|---|
| Text / structured | Llama 3.2 1B-Instruct | Qwen 2.5 1.5B-Instruct | 700 MB / 900 MB | Llama is faster, Qwen has tighter JSON adherence; user can switch in Settings to test which suits their bills |
| OCR (bill ingest stage 1) | PaddleOCR-WASM | — | ~50 MB | Two-stage beats single VLM here; reuses the text model already loaded |
| Voice (v1.1.2) | distil-whisper-small | — | 150 MB | English only |
| Embeddings (v1.2) | all-MiniLM-L6-v2 | — | 22 MB | Reconciliation match only |

---

## Bahi-specific gates

These are non-negotiable. They are what separates Smart Capture from "we added a chatbot."

1. **Never auto-post.** Hard rule. AI proposes drafts; user posts.
2. **`actor: 'ai'`** stamped on every AI-originated entry's audit-log row. The existing `actor` enum (`'owner' | 'ca' | 'system'`) gains `'ai'` as a fourth value. The audit chain verifier covers it without modification. The forensic chain stays unbroken — anyone walking the audit log sees exactly which entries originated from AI suggestion vs. owner vs. CA. When CA mode is active, AI-originated entries get `actor: 'ca'` with a separate `aiAssisted: true` field on the audit-log payload, so CA actions and AI-assisted CA actions stay distinguishable without inflating the actor enum. (`origin` continues to mean `window.location.origin` for cross-origin tamper detection — unchanged.)
3. **Period locks honored.** AI cannot draft into a locked period without the existing amendment flag firing — same gate as manual entry.
4. **AI prompts are not stored.** The audit log captures the resulting accepted entry, never the prompt or the rejected drafts. Prompts contain user data; persisting them is a leak surface for no benefit.
5. **BYOK keys never enter the `.khata` file.** Keys live in IndexedDB only. They are stripped from any export or backup. A `.khata` file is portable across machines; the user's API key is not.
6. **Off by default.** Same shape as CA mode toggle. Bahi v1's existing user is unaffected unless they explicitly turn AI on.

---

## Trade-offs we are making

* **Local default trades raw accuracy for privacy.** A 1B model will miss line items on messy bills more often than Claude or GPT-4o would. This is the right trade for an accounting product where the books are the user's most sensitive data. Users who want frontier accuracy can flip to BYOK; the UI flags clearly that BYOK sends bill content to the chosen provider.
* **Two-stage OCR over single VLM.** Less impressive on demos; more reliable, lighter to ship, easier to debug per-stage, and lets the text model be reused for text-to-entry without a second model load.
* **English-only voice at v1.1.2.** Hindi/Hinglish is the actual SMB workflow but the multilingual-voice rabbit hole is well-documented and has eaten previous explorations. Better to ship English voice than to delay v1.1 chasing Hindi.
* **No fine-tuning at v1.1.** A LoRA over Indian bill formats would lift extraction accuracy noticeably. It also blows the build path open. Revisit at v2.

---

## Roadmap beyond v1.2

These are not promises. They are signals about which directions stay open.

* **Hindi voice (and Hinglish code-mixed).** Whisper handles Hindi reasonably; Hinglish degrades fast. Wait for either a better small multilingual model or a clean fine-tune path before reopening.
* **Conversational ledger query.** *"Top 5 customers with > 30 day outstanding"* → text-to-SQL → run inside a SELECT-only sql.js transaction. Fits Bahi's well-defined schema; risk is read-only enforcement.
* **Narrative report commentary.** *"Sales dropped 12% MoM, mostly from customer X."* Pure LLM task on top of the existing P&L / dashboard data.
* **HSN/SAC suggestion.** Embedding lookup over the HSN dataset, item description in. Tiny feature, big QoL win during item master entry.
* **CA review observation drafting.** When a CA marks an entry for review, AI can draft an observation note for the review report PDF. CA edits and signs.

---

## Status

This is the vision doc. The companion **bahi-smart-capture-spec-001-v0.1.md** locks v1.1 in detail, with v1.1.0 / v1.1.1 / v1.1.2 milestones split inline. v1.2 will get its own spec when v1.1 ships. Agent handoff lives in **bahi-smart-capture-agent-001-v0.1.md**.
