# Bahi — Browser-Native Accounting for Indian SMBs

> *Your books. Your file. Your browser. Nothing leaves your device.*

A browser-native, local-first accounting application for Indian SMBs. Bahi reads and writes a `.khata` file (a zip containing a SQLite double-entry ledger + manifest + attachments + in-file snapshots) on the user's own disk via the File System Access API. **No server. No account. No subscription. No telemetry.**

The app is **Bahi** (बही — the traditional bound ledger of Indian merchants). The file format it reads and writes is **`.khata`** (खाता — account/ledger), published as an open standard so any tool can implement it.

- **Live build**: <https://bahi.naklitechie.com/>
- **Feature walkthrough with screenshots**: <https://bahi.naklitechie.com/demo/>
- **Sample `.khata` files** (synthetic, 2 FYs each): [`sample-data/`](sample-data/) — pharma, manufacturing, consulting

---

## Status

**Alpha — feature-complete for a CA-assisted pilot.** Bahi ships as a single ~1 MB HTML file. Schema is at v12 and round-trips cleanly across owner and CA workflows. The app has a deterministic generator and a 53-test suite that exercises the format end-to-end against three realistic sample files (pharma + manufacturing + consulting); all 53 pass.

The "alpha" tag means: the engine, posting bridges, snapshot pattern, audit chain, and report set are stable enough to drive real books. Defaults, copy, ordering, and minor UI affordances will keep moving until v1.

---

## Features

### Engine

- sql.js (SQLite WASM) double-entry ledger, lazy-loaded from CDN
- `.khata` zip I/O — `manifest.json`, `books.sqlite`, `attachments/`, `exports/`, in-file snapshots
- Standard Indian Chart of Accounts seeded on file create
- Posting engine with hard balance assertion (Dr = Cr or the transaction rolls back)
- Append-only audit log: SHA-256 hash chain + ECDSA P-256 signatures + per-entry `origin`
- File System Access API with **forced** read+write permission on every open
- Persistent file handles in IndexedDB
- BroadcastChannel concurrent-tab lock — one file, one tab
- Identity banner on every file open; clock drift sanity check
- Format version compatibility check (newer files open read-only, older migrate forward)
- Optimistic concurrency check on save with conflict modal
- Cross-origin detection on file open
- Idempotent schema migration runner with `meta.schemaVersion`

### Snapshots, backup, recovery

- Rolling in-file snapshot system: last 10 saves + last 7 daily + last 12 monthly + permanent (manual / FY-close)
- Snapshots panel with manual save + restore-as-new-file
- **Backup Now** button — dated `.khata-backup.zip` with `audit-log.csv` + `meta.json`. `Ctrl+Shift+B` shortcut, 30-day nudge banner on the dashboard
- Restore from backup auto-detects `.khata` or backup zip
- **OPFS atomic-write staging** — every blob mirrored to `OPFS:bahi-staging/{workspaceId}.khata` before disk write; orphan staging copies surface a Settings → Crash recovery panel
- 5-layer wrong-file detection (workspace identity, fingerprinted exports, audit-log ancestry, export-time identity, change-history walk)
- Corruption recovery modal — `PRAGMA integrity_check` failure surfaces three paths: restore from in-file snapshot, restore from backup zip, **rebuild from audit log** (replays every replayable entry on a fresh database)

### Masters

- State stored as **ISO 3166-2:IN code** (canonical FK) with typeable input combobox
- Reference data subsystem with bundled seeds + lazy-fetch from the [khata-standard CDN](https://github.com/NakliTechie/khata-standard) (SHA-256 verified per dataset, persisted per file)
- Customer master with GSTIN ↔ state sync, outstanding column, payment terms
- Vendor master with RCM-applicable flag, default TDS section, payable opening balance
- Item / service master with HSN/SAC datalist, auto-suggested rate, inventory toggle
- Multiple invoice series (Domestic / Export / SEZ-WP / SEZ-WOP / Bill of Supply, plus user-defined)
- Full new-company wizard with PAN-aware multi-GSTIN copy from existing files
- Edit company details with per-field audit log + `manifest.company.changeHistory`

### Sales

- Invoice form with live tax computation (intra-state CGST+SGST vs inter-state IGST routing)
- **Date-parameterized GST rates** (no hardcoded enums); per-rate sub-account auto-create on first use
- **Compensation cess** — per-line cess on cess-bearing goods, auto-suggested from the HSN and date-effective (honours the 2025-09-22 GST 2.0 cutover for non-tobacco goods); posts a Cess Output leg and flows through to the PDF, GSTR-1 (`csamt`) and GSTR-3B. Reads both the bundled rate table and the [khata-standard](https://github.com/NakliTechie/khata-standard) cess dataset
- Auto invoice number per FY, per series (`INV/26-27/0001`)
- **Snapshot pattern** on every invoice — company, customer, place-of-supply, HSN description, account names frozen at posting time so reprints survive any future master edit
- GST-compliant **invoice PDF** (TAX INVOICE / BILL OF SUPPLY) with multi-line description wrapping, totals, amount in words, signature block
- **Devanagari support** in PDFs — Noto Sans Devanagari lazy-loaded, ₹ rupee glyph included
- Credit notes against invoices (full-reversal or partial)
- Composition scheme: invoice form hides GST routing, PDF prints "BILL OF SUPPLY" with the Rule 49 disclosure

### Purchases

- Purchases with internal ref (`PUR/{FY}/{NNNN}`), vendor's bill number, place-of-supply state routing
- RCM toggle that auto-routes posting to GST RCM Input/Output sub-accounts
- **Compensation cess** on cess-bearing purchases — posts a Cess Input leg (or Cess RCM Input/Output that nets to zero under reverse charge) and flows into GSTR-3B ITC
- ITC eligibility flag for blocked credits (motor vehicles, club fees, etc.)
- Per-rate GST Input sub-account auto-create
- Debit notes against purchases (full-reversal or partial)
- Item picker with free-text fallback for one-off services

### Money

- Customer receipts with multi-invoice allocation, FIFO checkboxes, bank/cash picker, mode + reference fields
- **Vendor payments with auto-TDS** — section + rate auto-fill from vendor master, live `gross − TDS = net to vendor`, posts the journal split (Bank net + per-section TDS Payable)
- Advance receipts with back-calculated taxable from gross, GST routing, separate `advances` + `advance_adjustments` tables
- Apply-advance section in the invoice form with reversing journal automation
- Status badges: PAID / PARTIAL / DUE on invoices, OPEN / PARTIAL / FULLY ADJUSTED on advances
- TCS collection recording (Section 206C)
- **Manual bank reconciliation** — pick a bank account + date range, per-line cleared checkbox, statement-vs-book closing balance, snapshot persisted to `bank_reconciliations`
- Journal voucher form for free-form double-entry adjustments
- **Session-scoped undo stack** (Ctrl+Z) — posts a counter-entry via the same engine; original and reversal both stay in the audit log

### Inventory

- Items get inventory columns: `enable_inventory`, `valuation_method`, `track_batches`, `reorder_level`, `preferred_vendor_id`, `opening_stock_qty`, `opening_stock_value`
- **Stock movement engine** with both **Weighted Average Cost** AND **First-In-First-Out**, selectable per item
- Optional named-batch tracking with `mfg_date` + `expiry_date` for pharma / electronics / perishables
- Multi-godown support (single auto-seeded "Main" godown by default)
- Auto stock posting hooks on every invoice / purchase / credit note / debit note / delivery challan
- **Cost of Goods Sold journal** — every invoice posts a separate Dr COGS / Cr Stock-in-Hand entry at the WAC or FIFO rate
- **Inventory dashboard** with KPIs + reorder alerts
- **Reports**: Stock on hand (per item × godown), Stock movements (full log), Stock register (per-item walkthrough), Batches (with expiry warnings), Valuation summary, Reorder alerts, Stock aging
- **Delivery challans** (outward-job / outward-sample / outward-return / inward-return) — vehicle, transporter, returnable flag, no GL posting
- **E-way bills** — generated from invoice or DC, NIC bulk-upload JSON, printable PDF with QR placeholder, "Mark as generated" workflow to re-export with the real EWB number
- **Inter-GSTIN stock transfers** — outbound wizard creates the transfer + matching tax invoice + cross-file JSON; inbound import validates GSTINs and creates the receiving record

### Reports

- **Trial Balance** with debit/credit tie check
- **Balance Sheet** with assets/liabilities/equity sections, tie check, current-period unclosed profit rollup
- **P&L summary** computed live from the ledger
- **Day Book** (chronological)
- **Account Ledger** (per-account with running balance)
- **Sales Register** and **Purchase Register**, date-filterable
- **Dashboard**: cashflow vs last month, outstanding receivables, GST liability, receivables aging (4 buckets), top customers, recent activity feed

### Compliance

- **GSTR-1** monthly portal-upload JSON — B2B / B2CL / B2CS / HSN / doc_issue / AT (advances) / TXP (adjustments), compensation cess (`csamt`) carried per line, validation errors hard-block JSON download. **B2CL threshold is date-effective** (₹2.5 L pre-2024-08-01, ₹1 L from 2024-08-01) so historical invoices are never re-bucketed
- **GSTR-3B** monthly summary — Section 3.1(a) outward + 3.1(d) RCM + Section 4 ITC (including cess) + net liability, JSON + CSV export
- **CMP-08** quarterly view for composition dealers
- **Form 26Q** quarterly TDS return — section breakdown, validation errors, NSDL-compatible CSV
- **Form 27EQ** quarterly TCS return — same shape
- **Form 27D** TDS certificate — per-vendor PDF with deductor letterhead, deductee block, deductions table, totals, signature block
- **Tax payment challans** — templated JSON exports for PMT-06, DRC-03, ITNS 280/281/282/283, ECR, ESI, PTRC, LWF, plus a custom challan builder
- **Period locks** — mark a return type as filed for a date range so postings dated within get flagged as amendments
- **FY rollover wizard** — preview income / expense / net P/L, then post the year-end closing entries (zero out income/expense to P&L Summary, transfer P&L Summary to Capital Account)
- **Layer 4 export-time identity check** — every export verifies the active workspace entry's GSTIN + name against the open file's manifest before producing the file

### Tally migration

- **Permissive parser** for both Tally Prime and Tally ERP 9 (browser-native `DOMParser`, no CDN deps)
- Walks Masters (Groups, Ledgers, Stock Items, Units, Godowns) and Vouchers (Sales / Purchase / Receipt / Payment / Journal / Contra / Credit Note / Debit Note + variants)
- **6-step wizard**: file summary → date range → mapping review → commit target (new file or merge) → dry-run preview → result
- Auto-suggested mappings for 25+ standard Tally groups; user-created groups hard-block until resolved
- Atomic transaction — entire import wraps in `BEGIN` / `COMMIT`; any failure rolls back cleanly
- Posting bridges reused — every imported invoice goes through `postInvoiceToLedger`, every purchase through `postPurchaseToLedger`, every journal through `postEntry`, so snapshot capture and stock effects fire automatically
- Forensic audit trail — `tally.import.start` / `tally.import.commit` / `tally.import.failed` entries

### CA mode

- **First-run mode picker** — Business owner / Chartered accountant. Persisted to `localStorage.bahi.mode`
- **CA profile** stored in IndexedDB outside any client `.khata` file: name, firm name, ICAI membership number, optional logo
- **Mode-aware sidebar** with a CA-only group (Client review / Adjustment voucher / Annotations / Review report)
- **Topbar mode badge** showing OWNER or CA · {initials}; click to switch
- **`auditActor()` helper** auto-tags every audit entry as `'ca'` in CA mode — every CA action is forensically distinguishable from owner actions
- **Annotations** with target type, body, status, and CA identity captured at creation time
- **Review markers** track which entries the CA has signed off on
- **Client review interface** with per-voucher-type unreviewed counts + bulk mark
- **CA adjustment voucher form** — wraps the journal voucher engine with adjustment-type picker (year-end / depreciation / prepaid / outstanding / accrual)
- **Printable review report PDF** — multi-page A4 with CA firm letterhead, page numbering, sections for Trial Balance / P&L / Balance Sheet / CA Adjustments / Observations
- **Layer 3 ancestry check** on file open — compares audit chain head against `workspace.lastKnownHead`; divergent branches route to the Reconciliation View
- **Reconciliation View** for divergent branches — side-by-side checkbox lists, replay engine that re-executes picked entries via the existing posting bridges, merged manifest carries `integrity.parentHashes = [localHead, importedHead]`

### Smart Capture & CA Lookup (AI) — optional, on-device, off by default

AI is opt-in (enable in Settings), runs **on-device by default**, and adds nothing to the byte-for-byte-off baseline until you turn it on. Nothing leaves the machine unless you configure a remote provider.

- **Smart Capture** — drop a vendor bill (PDF/JPG/PNG); on-device OCR (Tesseract / PaddleOCR) + a local LLM draft a purchase voucher you review in the normal form. **AI never auto-posts**; accepted drafts are logged with `actor='ai'`.
- **CA Lookup** — a floating tax/GST reference sidecar (`Ctrl/Cmd+Shift+L`). On-device **semantic search** (bge-small embeddings + a hybrid lexical boost for section / HSN codes) over a **CA-reviewed reference corpus**, with an optional **grounded, cited AI answer** above the results. Answers draw only from the retrieved corpus (never invented), cite their sources, and carry an "AI can make mistakes — double-check" note. Cited snippets render instantly even with no answer model loaded.
- **Models** — on-device via transformers.js + WebGPU: **Gemma 4 E2B/E4B** (multimodal, bill capture) and **LFM2 2.6B / LFM2.5 / LFM2 8B-A1B / Qwen 2.5** (text — the lighter CA-Lookup answer tier). Or **BYOK** cloud providers (Anthropic / OpenAI / Mistral / OpenRouter / custom). BYOK keys live in IndexedDB only — never in `.khata`, exports, or the audit log.
- **Web enrichment (optional)** — add your own **Tavily** key to let CA Lookup pull live web results into an answer (direct browser → Tavily; off by default; the query + key leave the device only when you enable it).

### Ergonomics

- **5 themes**: Crisp paper (light — the default), Sakura wash, Asagi haze, Kinari washi, Sumi (dark) — switch any time in Settings
- **Tally keyboard parity** — F4 contra, F5 payment, F6 receipt, F7 journal, F8 sales, F9 purchase, F10 other vouchers, F1 company picker, F3 company info, plus Ctrl+Z undo, Ctrl+Shift+B backup, Ctrl+Shift+M mode toggle, Ctrl+Shift+D debug, `?` help overlay
- **Shortcut help overlay** with one-click cheat-sheet PDF
- **BOFH-style action-aware sidebar search** — search the menu by what each route lets you DO, not just by label
- **Multi-company workspace switcher** in the topbar
- Sidebar restructured into Workspace / Masters / Sales / Purchases / Inventory / Money / Reports / Compliance / CA mode / Dev groups (60+ routes)

---

## Try it

The fastest path is the **demo walkthrough** at <https://bahi.naklitechie.com/demo/> — sticky section nav, modes intro, and a 3-step "try it yourself" callout that links directly to a sample `.khata` you can open in the live build.

Or do it manually:

1. Open <https://bahi.naklitechie.com/> in **Chromium** (Chrome, Edge, Brave, Arc, Opera). Safari and Firefox don't expose the File System Access API.
2. Download a sample from [`sample-data/`](sample-data/) — `pharma.khata` is the most complete (goods + services, ~600 invoices, credit notes, advances, TDS, inventory).
3. **Workspace → Open existing → pick the file**. Bahi will ask permission to read+write the file in place — allow it.
4. Click around. Dashboard / GSTR-1 / Form 26Q / Inventory / Trial Balance / Balance Sheet all populate from real data.

The three sample files are deterministically regenerated by [`sample-data/generator.py`](sample-data/generator.py) and validated by the [`sample-data/test_khata.py`](sample-data/test_khata.py) suite (45 tests across format integrity, double-entry invariants, audit-chain walk, snapshot pattern, GST routing, TDS ledger ties, stock integrity, and per-company shape).

---

## Running locally

Single HTML file. No build, no server-side code, no install.

```bash
cd Bahi
python3 -m http.server 8080
open http://localhost:8080/
```

The first time you open Bahi it lazy-fetches sql.js (~1 MB WASM), JSZip (~95 KB), and jsPDF (~360 KB) from jsdelivr. Subsequent loads are cached and offline.

---

## The `.khata` format

```
mybooks.khata  (zip)
├── manifest.json    metadata, schema version, integrity hashes, audit head, public key,
│                    company block (with changeHistory), snapshot index, mode history
├── books.sqlite     the double-entry ledger (accounts, entries, entry_lines, audit_log,
│                    customers, vendors, items, invoices, invoice_lines, purchases,
│                    purchase_lines, payments, payment_allocations, advances, credit_notes,
│                    debit_notes, tds_deductions, tcs_collections, stock_movements, batches,
│                    godowns, delivery_challans, eway_bills, stock_transfers, annotations,
│                    review_markers, bank_reconciliations, period_locks, fy_closings, meta)
├── snapshots/       rolling in-file snapshots
├── attachments/     user-uploaded bills, receipts, scans
└── exports/         cached report exports
```

Specification: [`khata-format.md`](khata-format.md). The format is intended to outlive any single app — anyone can `unzip file.khata` and inspect the SQLite + JSON inside. Reference data (states, GST rates, HSN/SAC, TDS sections) lives in the open [khata-standard](https://github.com/NakliTechie/khata-standard) repo and is fetched on demand with SHA-256 verification.

---

## Engineering decisions & failure model

> A confidence-building summary of the key choices and what protects the file in adverse conditions. If you're handing this off to someone else to evaluate, this is the section to point them at.

### Why a single file (the `.khata` zip)

The whole point of Bahi is that **your books are a single artifact you control**. One file means:
- No "where is my data?" confusion. It's the file you saved.
- Backups are `cp file.khata file-backup.khata`. No magic.
- Sync providers (Dropbox / iCloud / Drive) treat it as one unit.
- Restoration is `cp file-backup.khata file.khata`. No magic.
- The format outlives the app — anyone can `unzip file.khata` and inspect the SQLite + JSON inside.

The trade-off is that simultaneous concurrent editing across machines is genuinely hard with a single-file model. Bahi handles it via optimistic concurrency rather than pretending it can magically merge concurrent edits — see the failure model table below.

### Why integer paise

Money is stored as `INTEGER` paise everywhere — never floats. Floats lose pennies under repeated arithmetic; tax computation does a lot of repeated arithmetic. Display is `(paise / 100).toFixed(2)` with Indian comma grouping. The audit log also hashes integer payloads so signature verification is reproducible across machines.

### Why snapshots-at-posting (Invariants 1–8 from `BAHI-AGENT-MSG-HISTORICAL-INTEGRITY.md`)

When you post an invoice, Bahi freezes the company name, customer name, GSTIN, state, HSN description, tax rate, and account names into snapshot columns on the invoice row itself. Reprints, GSTR-1 export, and any historical view read from those snapshots — never from a live JOIN on the master tables. If you rename a customer six months later, last year's invoice still prints with last year's name. This is non-negotiable for tax compliance and was a one-day refactor early on that would have been a multi-day mess after release.

### Why date-parameterized tax rates

GST rates change. We don't hardcode "18% GST" anywhere in the engine. `REF.gstRates` is a list of `(rate, validFrom, validTo)` records, and every lookup is parameterized by the invoice date. Backdated invoices automatically get the rate set that was in force then. Per-rate sub-accounts (`CGST Output @ 9%` etc.) auto-create on first use so the chart of accounts stays clean.

The same date-effective principle governs anything else that moves with policy: compensation-cess rates (with the 2025-09-22 GST 2.0 cutover encoded as a `validTo`) and the B2CL reporting threshold (₹2.5 L → ₹1 L on 2024-08-01) are both looked up by the invoice date, so a rule change never silently re-states a historical document.

### Why ISO state codes (not GSTIN numeric codes)

State is stored as `ISO 3166-2:IN` (e.g. `MH`, `KA`) — the canonical FK throughout the format. The GSTIN's first two digits and the state name are derived from a lookup table at display time. This means renaming a state (Orissa → Odisha) doesn't require touching any data; it's a label change in the lookup table.

### Why an append-only audit log with a hash chain

Every meaningful action (post entry, edit company, lock period, FY close, opening stock, etc.) appends to `audit_log`. Each entry hashes `prev_hash || origin || canonicalJson(payload) || booksHash` with SHA-256, plus an ECDSA P-256 signature. The chain is never edited or rewound. The Debug Console has a verifier that walks the chain and reports any break.

This gives you three things at once:
- **Tamper evidence.** If anyone edits the SQLite directly, the books hash mismatch shows up at the next write.
- **Forensic chain-of-custody.** The `origin` field tracks where each entry was written; cross-origin opens leave a marker.
- **Crash recovery anchor.** The audit head is the comparison key for the optimistic concurrency check, the OPFS staging recovery, and the Layer 3 ancestry check.

### Why undo-via-counter-entry (not delete)

`Ctrl+Z` posts a *new* journal entry that swaps Dr and Cr against the original. Both rows stay in the audit log forever. A user-visible undo never deletes anything from the ledger; the reversal is itself an auditable action.

### Failure model

| Scenario | Protection | What the user sees |
|---|---|---|
| Browser crash mid-save | OPFS staging mirror written before disk write | Recovery banner on dashboard + Settings → Crash recovery panel with **Recover** / **Discard** buttons |
| OS crash / power outage mid-save | Same as above | Same |
| USB drive yanked mid-save | Same as above; verify-before-write on the rebuilt blob means the disk file was never partially written | Same |
| Same browser, second tab opens the file | BroadcastChannel lock | Hard block: "This company is already open in another Bahi tab" |
| Different browser / different machine writes the file | Optimistic concurrency check at next save (re-reads disk, compares audit head) | Save conflict modal: **Reload from disk** or **Save as conflict copy** (sibling `{slug}-conflict-{ts}.khata`) |
| File on Dropbox/iCloud syncing in background, outside change arrives | Same concurrency check fires | Same conflict modal |
| File moved to a different machine and reopened | Cross-origin detection reads the most recent audit entry's `origin`, compares to current | Informational toast; keypair rotation marker appended to the audit log |
| File on disk corrupted (PRAGMA fails) | Three-path corruption recovery modal | Restore from in-file snapshot **or** restore from backup zip **or** rebuild books by replaying every replayable audit entry on a fresh database |
| Wrong file opened (file-name collision) | 5-layer wrong-file detection (workspace identity, fingerprinted exports, audit-log ancestry, export-time identity, change-history walk) | Hard block on workspace replace if the identity doesn't match; export-time hard block if the active workspace doesn't match the open file |
| Schema bumped between Bahi versions | Version-tagged migration runner in `meta.schemaVersion` | Older files migrate forward silently; newer files (above this build's `SUPPORTED_FORMAT`) open read-only with a banner |
| Audit log tampered with | SHA-256 hash chain | Chain verifier in Debug Console reports any break |
| CA round-trip (owner → CA → owner) introduced silent overwrites | Layer 3 ancestry check on file open + Reconciliation View | "Same GSTIN but no shared history" warning toast for unrelated copies; divergent branches route to `#/reconcile` with side-by-side checkbox merging; merged file carries both parent hashes |
| CA actions accidentally indistinguishable from owner actions | `auditActor()` helper auto-tags every audit entry as `'ca'` in CA mode | Audit log + review report clearly attribute each entry to either owner or CA, with the CA's name + firm + ICAI membership stamped at creation time |
| Owner edits the file while CA was reviewing it | Layer 3 ancestry check fires on next CA open | Reconciliation View opens automatically; CA picks which entries to keep from each branch |
| Posting mistake — wrong amount, wrong account | Session-scoped undo stack via Ctrl+Z | Counter-entry posted via the same engine; both the original and the reversal stay in the audit log forever; the undo is auditable, not stealthy |
| User forgot to back up | 30-day nudge banner on the dashboard | Yellow banner appears when last backup is > 30 days old (or never recorded), with a "Backup Now" CTA |
| Wrong file exported on a CA handoff | Layer 4 export-time identity check | Compares active workspace entry's GSTIN + name against the open file's manifest before any export. Mismatch hard-blocks with an explanation pointing to the mismatch |
| Reference data drift over time | `#/ref-data-update` lazy-fetches from khata-standard CDN | SHA-256 verified per-dataset; updates persisted per file in the `meta` table |
| SQLite damaged AND in-file snapshots damaged | Audit-log replay restoration | Third path on the corruption recovery modal — rebuilds books by replaying every replayable audit entry on a fresh database |

**Not protected (and probably shouldn't be):**
- **Disk hardware failure.** No software can save you. Use **Backup Now** to write a dated `.khata-backup.zip` and keep one offsite.
- **Two clients writing in the exact same millisecond on a network share.** The OS filesystem decides who wins; one write may be silently dropped at the OS level. Bahi's verify-before-write keeps the file from being torn, and Layer 1 catches it on the next save attempt — but the dropped write itself is gone. Don't use Bahi as a multi-user server.
- **Sync provider conflict copies** (`Bahi (Conflicted Copy 2026-04-07).khata`). Bahi can't automatically see siblings created by Dropbox/iCloud — open them via Workspace → Open existing.

### How to be extra paranoid

- Don't put a `.khata` file on a network share that two machines mount simultaneously. Pick one machine as the "owner" or move the file between machines explicitly.
- Use sync providers for backup, not concurrent editing.
- Hit **Backup Now** at the end of every session, especially before any irreversible action (FY rollover, period lock, large data import).
- Run **Debug Console → Round-trip test** after any unusual session.

The same content (in plain English) is also visible inside the app at **Settings → Safety & failure modes**, so the user can always check the contract without leaving Bahi.

---

## Quick test

1. Open Bahi → **Workspace** → **+ Create new .khata**
2. Enter a company name + GSTIN → state autofills → save the file to disk
3. Sidebar → **Customers** → **+ Add customer**
4. Sidebar → **Items / services** → **+ Add item** (HSN auto-suggests tax rate)
5. Sidebar → **+ New invoice** → pick the customer + add a line → Post & save
6. Sidebar → **Invoices** → click **PDF** on the row → save the GST-compliant PDF
7. Sidebar → **P&L summary** → see the income from the invoice

For low-level testing (raw posting, audit chain inspection, integrity checks, snapshot management, round-trip test): sidebar → **Debug Console** or `Ctrl+Shift+D`.

---

## Known limitations

- **Chromium-only.** The File System Access API does not exist in Safari or Firefox. Bahi will refuse to open files in those browsers. There's no degraded mode yet.
- **Single-user, single-tab per file.** BroadcastChannel enforces this; concurrent editing across machines is handled by optimistic concurrency, not real-time merge.
- **Bold/italic share the regular weight TTF in Devanagari PDFs.** True bold is a small follow-up.
- **Tamil / Telugu / Bengali / Gurmukhi / Gujarati / Malayalam / Kannada / Oriya** PDFs warn at print time and fall back to Helvetica. The on-demand font-load pattern is in place; the script-specific fonts aren't wired yet.
- **e-invoicing (IRN)** is not implemented — needs GSP integration.
- **No bank-statement auto-match** in bank reconciliation; the manual matcher is fully functional.

---

## Author

Chirag Patnaik · [@NakliTechie](https://github.com/NakliTechie) · [naklitechie.github.io](https://naklitechie.github.io/)

Part of the NakliTechie browser-native tools series.
