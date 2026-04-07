# Bahi — Browser-Native Accounting for Indian SMBs

> *Your books. Your file. Your browser. Nothing leaves your device.*

A browser-native, local-first accounting application for Indian SMBs. Bahi reads and writes a `.khata` file (a zip containing a SQLite double-entry ledger + manifest + attachments + in-file snapshots) on the user's own disk via the File System Access API. **No server. No account. No subscription. No telemetry.**

The app is **Bahi** (बही — the traditional bound ledger of Indian merchants). The file format it reads and writes is **`.khata`** (खाता — account/ledger), published as an open standard so any tool can implement it.

---

## Status — Phase 2C (freelancer tier complete + polish)

The Freelancer tier is live end-to-end. You can create a company file (full wizard with FY, type, composition flag, multi-GSTIN copy from existing entries), add customers and items, raise invoices across multiple series (Domestic / Export / SEZ-WP / SEZ-WOP / Bill of Supply), record advance receipts and apply them against later invoices, record regular payments, see the dashboard roll up cashflow / receivables aging / GST liability / top customers / recent activity, export GST-compliant PDFs (with Devanagari for Hindi/Marathi customer names + the proper ₹ glyph), file GSTR-1 (with B2B / B2CL / B2CS / HSN / AT / TXP) for regular dealers or CMP-08 quarterly for composition dealers, and switch between companies via the topbar dropdown — all from the browser, all stored on your own disk, never leaving your device.

### What's shipped

**Engine** (Phase 1A)
- sql.js (SQLite WASM) double-entry ledger, lazy-loaded from CDN
- `.khata` zip I/O with `manifest.json`, `books.sqlite`, `attachments/`, `exports/`, `snapshots/`
- Standard Indian Chart of Accounts seeded on file create (36 accounts)
- Posting engine with hard balance assertion (Dr = Cr or transaction rolls back)
- Append-only audit log: SHA-256 hash chain + ECDSA P-256 signatures + per-entry `origin` field
- File System Access API with **forced** read+write permission on every open
- Persistent file handles in IndexedDB
- BroadcastChannel concurrent-tab lock — one file, one tab
- Identity banner on every file open
- Clock drift sanity check
- Format version compatibility check (newer files open read-only, older migrate forward)
- Optimistic concurrency check on save with conflict modal (reload-from-disk or save-as-conflict-copy)
- Cross-origin detection on file open
- Idempotent schema migration runner with `meta.schemaVersion`

**Snapshots & recovery** (Phase 1B)
- Rolling in-file snapshot system (last 20 saves + permanent manual / FY-close)
- Snapshots panel in Debug Console with manual save + restore-as-new-file
- "Backup Now" button — dated `.khata-backup.zip` with audit-log.csv + meta.json
- Restore from backup — auto-detects `.khata` or backup zip, lists candidates, restores to a new file
- Wrong-file detection: Layer 2 (identity mismatch on workspace replace, walks `changeHistory`) and Layer 5 (fingerprinted export filenames)
- Corruption recovery modal — when `PRAGMA integrity_check` fails, lists in-file snapshots and restores to a new file
- Keypair rotation marker on cross-origin opens

**Freelancer tier** (Phase 2A)
- State stored as **ISO 3166-2:IN code** (canonical FK) with typeable input combobox
- Reference data subsystem with bundled seeds: states, GST rates, cess, TDS, TCS, RCM, composition rates, common HSN/SAC
- Customer master with GSTIN ↔ state sync
- Item / service master with HSN/SAC datalist + auto-suggested rate from history
- Invoice form with live tax computation (intra-state CGST+SGST vs inter-state IGST routing)
- Invoice posting through the double-entry engine
- Invoice list view with per-row action buttons
- P&L summary computed live from the ledger
- Indian amount-in-words helper (`Rupees X Lakh Y Thousand Only`)
- Auto invoice number per FY (`INV/26-27/0001`)
- Edit company details with per-field audit log + `manifest.company.changeHistory[]`
- Four themes (Crisp paper, Sakura wash, Asagi haze, Kinari washi) with picker in Settings

**Historical integrity** (Phase 2A.1 — `BAHI-AGENT-MSG-HISTORICAL-INTEGRITY.md`)
- Schema v2 snapshot columns: `invoices.company_snapshot`, `invoices.customer_snapshot`, `invoices.place_of_supply_name`, `invoice_lines.hsn_description`, `entry_lines.account_name`
- Posting captures snapshots from current reference data; reprint paths read snapshot columns only — no live JOINs
- All 8 invariants enforced
- 6 integrity check functions, auto-run on file open with warning toasts for legacy v1 rows

**Tax rate lifecycle** (Phase 2A.2 — `BAHI-AGENT-MSG-TAX-RATE-LIFECYCLE.md`)
- `REF.gstRates` with effective-dated records (`validFrom` / `validTo`)
- HSN seed restructured to per-code rate history
- Date-parameterized lookups: `getActiveGstRates(date)`, `getActiveHsnRate(hsnSac, date)`, `rateIdForDecimal(decimal, date)`, `getRateById(rateId)`
- Schema v3 `invoice_lines.rate_id` forensic key captured at posting time
- Both rate dropdowns (item modal + invoice line) built dynamically — **no hardcoded rate enums anywhere**
- Per-rate sub-account auto-create via `getOrCreateRateAccount`
- `postInvoiceToLedger` groups lines by rate and routes to `CGST Output @ 9%` / `IGST Output @ 18%` etc.
- `checkRateChangeResilience` integrity check
- Cess registered as separate dimension (`REF.cessRates`)

**Invoice PDF export** (Phase 2B.1 + 2B.5 Devanagari)
- jsPDF lazy CDN
- GST-compliant A4 template: TAX INVOICE title (or BILL OF SUPPLY for composition dealers), two-column header (company + invoice meta), bill-to / place-of-supply panels, lines table with multi-line description wrapping, totals + amount in words, signature block, page footer
- Reads exclusively from snapshot columns; legacy v1/v2 invoices get a peach LEGACY watermark + fall back to live joins
- Save As via FS Access with fingerprinted name (`{invoice-num}-{customer-slug}.pdf`)
- Print buttons on the invoice list (per row) and the lines modal footer
- **Devanagari**: detects Devanagari characters in any rendered text; lazy-loads Noto Sans Devanagari (~90 KB pinned-commit TTF) and switches the document font; that font also includes the ₹ rupee glyph so amounts no longer use the Helvetica "Rs." fallback

**Payments + advances** (Phase 2B.2 + 2B.6)
- Regular payment / receipt entry with multi-invoice allocation, FIFO checkboxes, bank/cash picker (with quick-add), mode + reference fields (cheque #, UTR, txn id)
- Advance receipts with back-calculated taxable from gross + GST routing, separate `advances` + `advance_adjustments` tables
- "Apply advance" section in the invoice form: open advances appear as checkboxes; on post the adjustment row is created and a reversing journal entry is automatically posted (Dr Customer Advances Received + Dr GST Output / Cr Sundry Debtors)
- Status badges (PAID / PARTIAL / DUE on invoices, OPEN / PARTIAL / FULLY ADJUSTED / REFUNDED on advances)
- Outstanding balance column on the Customers list

**Dashboard** (Phase 2B.3)
- Three KPI cards: cashflow this month vs last with delta %, total outstanding receivables, GST liability for current month
- Receivables aging table with 4 buckets (0–30 / 31–60 / 61–90 / 90+ days)
- GST liability detail panel with CGST / SGST / IGST breakdown
- Top 5 customers by outstanding amount
- Recent activity feed (last 15 audit log entries with friendly action labels: "Posted sales invoice", "Recorded receipt", "Updated company")
- Quick action buttons; auto-redirects to dashboard after file open / create / reopen

**GSTR-1 + CMP-08 export** (Phase 2B.4 + 2B.8)
- GSTR-1 monthly portal upload JSON with B2B / B2CL / B2CS / HSN / doc_issue / AT (Table 11A advances received) / TXP (Table 11B adjustments)
- CSV summary alongside the JSON for human / CA review
- Period picker (defaults to current month, supports backdated periods)
- Validation errors (missing GSTIN, missing place of supply) hard-block JSON download; CSV stays available
- Composition dealers: GSTR-1 redirects to CMP-08 quarterly view (turnover × composition rate)

**Multiple invoice series** (Phase 2B.7)
- 5 default series seeded: Domestic, Export, SEZ-WP, SEZ-WOP, Bill of Supply
- Series master CRUD; picker on the invoice form changes the auto-generated invoice number to the series's prefix
- `nextInvoiceNumber` walks invoices in the chosen series only with configured reset-on-FY behavior

**Composition scheme** (Phase 2B.8)
- `manifest.company.composition` flag with type (trader 1% / restaurant 5% / service 6%)
- Edit-company modal exposes the toggle and type picker
- When ON: invoice form hides GST routing, invoice posts without CGST/SGST/IGST, invoice PDF prints "BILL OF SUPPLY" + the mandated Rule 49 disclosure, GSTR-1 redirects to CMP-08

**Full new-company wizard** (Phase 2B.9 + 2B.10)
- Collects legal name, trade name, type (proprietorship / partnership / LLP / private / public / HUF / other), GSTIN, TAN, state (typeable combobox), address, FY start, UI tier, composition flag with type
- **PAN-aware multi-GSTIN copy**: when typing a GSTIN whose embedded PAN matches an existing workspace entry, surfaces an inline notice + Copy details button to pre-fill the legal name from the matched entry

**Company switcher** (Phase 2B.11)
- Topbar dropdown showing the current company name with a caret
- Click → menu of all workspace entries grouped by PAN with the active company highlighted
- Click an entry → save current → close → open the new file → land on dashboard

**Polish** (Phase 2C)
- **Snapshot retention**: full §9.3 policy — last 10 saves + last 7 daily + last 12 monthly + permanent (manual / FY-close), with set-union dedupe so a snapshot satisfying multiple buckets stays once
- **OPFS atomic-write staging**: every blob is mirrored to `OPFS:bahi-staging/{workspaceId}.khata` BEFORE the disk write, then cleared on success — if a save is interrupted (browser crash, OS crash, power loss, USB yank), the next file open detects the orphan staging copy with a newer audit head and surfaces a Settings → Crash recovery panel offering Recover or Discard
- **First-run welcome modal**: per-machine localStorage flag (`bahi.introSeen`), three-card explainer (Create / Open / Restore), explicit "Got it" + "Read README" buttons

---

## Running

Single HTML file. No build, no server-side code, no install.

```bash
cd Bahi
python3 -m http.server 8080
open http://localhost:8080/
```

**Chromium-only** (Chrome, Edge, Brave, Arc, Opera) — the File System Access API does not exist in Safari or Firefox.

The first time you open Bahi it lazy-fetches sql.js (~1 MB WASM), JSZip (~95 KB), and jsPDF (~360 KB) from jsdelivr. Subsequent loads are cached and offline.

---

## The `.khata` format

```
mybooks.khata  (zip)
├── manifest.json    metadata, schema version, integrity hashes, audit head, public key,
│                    company block (with changeHistory), snapshot index, mode history
├── books.sqlite     the double-entry ledger (accounts, entries, entry_lines, audit_log,
│                    customers, items, invoices, invoice_lines, meta)
├── snapshots/       rolling snapshots of previous saves (last 20 auto + permanent)
├── attachments/     user-uploaded bills, receipts, scans
└── exports/         cached report exports
```

The format is intended to outlive any single app. Reference implementation: this repo. Specification document (`khata-format.md`) will be published on naklitechie.com once the schema fully stabilises through Phase 3.

---

## Quick test

1. Open Bahi → **Workspace** → **+ Create new .khata**
2. Enter a company name + GSTIN → state autofills → save the file to disk
3. Sidebar → **Customers** → **+ Add customer** (also typeable state input)
4. Sidebar → **Items / services** → **+ Add item** (HSN auto-suggests tax rate)
5. Sidebar → **+ New invoice** → pick the customer + add a line → Post & save
6. Sidebar → **Invoices** → click **PDF** on the row → save the GST-compliant PDF
7. Sidebar → **P&L summary** → see the income from the invoice

For low-level testing (raw posting, audit chain inspection, integrity checks, snapshot management, round-trip test): sidebar → **Debug Console** or `Ctrl+Shift+D`.

---

## Limitations and parked items

**Lower priority, on the deferred list:**
- Daily/monthly snapshot bucketing (currently last-20-saves only)
- Wrong-file detection Layer 3 (audit-log ancestry on refresh — needs Phase 6 reconciliation)
- Wrong-file detection Layer 4 (export-time identity check — there are no `.khata` exports yet)
- Audit-log replay restoration (snapshots cover the recovery use case)
- Full HSN top-2000 + SAC bundle (needs `khata-standard` repo to publish)
- Reference data update UI (Phase 2 work)
- OPFS staging for true atomic writes (currently verify-before-write)
- One-time backfill flow for legacy v1 invoices
- Devanagari / Tamil / other Indian script fonts in PDF (currently Helvetica only — uses `Rs.` instead of `₹`; Phase 2B.2 lazy-loads Noto Sans Devanagari)

**Phase 2B coming next:** payment / receipt entry with multi-invoice allocation, dashboard (receivables aging, cashflow, recent activity), GSTR-1 JSON export, advance receipts with GST on advance, multiple invoice series, composition scheme handling, first-run onboarding screen, PAN-aware multi-GSTIN copy-from-existing wizard.

**Phase 3+:** Service SMB tier (vendors, purchases, credit/debit notes, journal vouchers, full reports, TDS, RCM, TCS, CMP-08, financial year rollover) → Goods SMB tier (inventory, stock, e-way bills) → Tally import → CA mode → polish & launch.

---

## Author

Chirag Patnaik · [@NakliTechie](https://github.com/NakliTechie) · [naklitechie.github.io](https://naklitechie.github.io/)

Part of the NakliTechie browser-native tools series.
