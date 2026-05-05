# Bahi v2 — Operations Module Spec (bahi-ops-001 v0.2)

> Pre-ledger document chains for sales and procurement, folded into the existing single HTML file.

**Status:** Spec for v1.0 / v1.1. Decisions locked unless explicitly marked open.
**Schema:** bumps `.khata` from v9 → v10. Forward-compatible migration; no existing data touched.
**Author handoff target:** Claude Code, against the existing Bahi codebase.

---

## 1. Why this exists

Bahi today goes straight from a customer to an invoice, and from a vendor to a bill. The operational reality before either of those — quotes, sales orders, RFQs, purchase orders, goods receipts, three-way match — lives in spreadsheets, WhatsApp, or a separate Tally setup. Operations module closes that gap inside the same HTML file, the same `.khata` file, the same posting engine, the same audit chain.

This is not a new product. It is a sidebar group inside Bahi v2.

## 2. Non-goals (v1)

- Approval workflows / multi-step authorization. Ops stays single-user-decision-maker.
- Multi-currency on ops docs. INR-only for v1, same as the rest of Bahi.
- IRN / e-invoicing generation. Architecture becomes ready (conversion hook exists), but the GSP integration is still out of scope and tracked separately.
- Production / BOM / work orders. Separate future module group.
- Payroll. Separate future module group.
- Project / job costing. Future small addition.
- Vendor portals or customer self-service. Bahi remains a single-operator tool.
- Real-time collaborative editing. Existing Bahi concurrency model (BroadcastChannel + optimistic) carries.

## 3. Scope summary

Two parallel chains, both end where Bahi already begins:

```
Sales chain:        Quote → Sales Order → Delivery Challan → Invoice
                                             (existing)      (existing)

Procurement chain:  RFQ → Purchase Order → GRN → 3-way match → Bill
                                                                (existing as "Purchase")
```

Existing direct-entry paths to Invoice and Bill are preserved. Ops docs are optional. A user who wants to keep cutting invoices directly from the customer master, the way Bahi works today, never has to touch Operations.

## 4. Data model

All new entities live in `books.sqlite` inside the `.khata` zip. Schema bump v9 → v10 adds tables; no existing tables modified except for three foreign-key columns and one stock-movement source field.

### 4.1 New tables

```sql
-- Quotes
CREATE TABLE quotes (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,           -- Q/{FY}/{NNNN}
  series_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  customer_snap_json TEXT NOT NULL,      -- frozen at create
  date INTEGER NOT NULL,                 -- yyyymmdd
  valid_until INTEGER NOT NULL,
  status TEXT NOT NULL,                  -- draft|sent|accepted|rejected|expired|revised|superseded
  parent_quote_id INTEGER,               -- for revisions
  revision INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  terms TEXT,
  subtotal_paise INTEGER NOT NULL,
  tax_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL,
  converted_so_id INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE quote_lines (
  id INTEGER PRIMARY KEY,
  quote_id INTEGER NOT NULL,
  line_no INTEGER NOT NULL,
  item_id INTEGER,                       -- nullable for free-text
  item_snap_json TEXT NOT NULL,          -- name, hsn, uom snapshot
  description_snap TEXT NOT NULL,
  qty REAL NOT NULL,
  rate_paise INTEGER NOT NULL,
  discount_pct REAL DEFAULT 0,
  gst_rate REAL NOT NULL,
  amount_paise INTEGER NOT NULL,
  tax_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL
);

-- Sales Orders
CREATE TABLE sales_orders (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,           -- SO/{FY}/{NNNN}
  series_id INTEGER NOT NULL,
  customer_id INTEGER NOT NULL,
  customer_snap_json TEXT NOT NULL,
  quote_id INTEGER,                      -- nullable; SOs can be standalone
  date INTEGER NOT NULL,
  promised_date INTEGER,
  status TEXT NOT NULL,                  -- open|partially_fulfilled|fulfilled|closed|cancelled
  notes TEXT,
  subtotal_paise INTEGER NOT NULL,
  tax_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE sales_order_lines (
  id INTEGER PRIMARY KEY,
  so_id INTEGER NOT NULL,
  line_no INTEGER NOT NULL,
  quote_line_id INTEGER,                 -- back-link if from quote
  item_id INTEGER,
  item_snap_json TEXT NOT NULL,
  description_snap TEXT NOT NULL,
  qty_ordered REAL NOT NULL,
  qty_delivered REAL NOT NULL DEFAULT 0,
  qty_invoiced REAL NOT NULL DEFAULT 0,
  rate_paise INTEGER NOT NULL,
  discount_pct REAL DEFAULT 0,
  gst_rate REAL NOT NULL,
  amount_paise INTEGER NOT NULL,
  tax_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL
);

-- RFQs
CREATE TABLE rfqs (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,           -- RFQ/{FY}/{NNNN}
  date INTEGER NOT NULL,
  response_due INTEGER,
  status TEXT NOT NULL,                  -- draft|sent|closed|cancelled
  notes TEXT,
  subject TEXT,                          -- "5T grade-A castor seed for Mar quarter"
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE rfq_lines (
  id INTEGER PRIMARY KEY,
  rfq_id INTEGER NOT NULL,
  line_no INTEGER NOT NULL,
  item_id INTEGER,
  description TEXT NOT NULL,
  qty REAL NOT NULL,
  uom TEXT
);

CREATE TABLE rfq_vendors (
  id INTEGER PRIMARY KEY,
  rfq_id INTEGER NOT NULL,
  vendor_id INTEGER NOT NULL,
  vendor_snap_json TEXT NOT NULL,
  sent_at INTEGER,
  response_received_at INTEGER,
  response_doc_attachment_id INTEGER,    -- attachment in /attachments
  response_total_paise INTEGER,
  response_notes TEXT,
  selected INTEGER NOT NULL DEFAULT 0    -- 1 = winner; converted to PO
);

-- Purchase Orders
CREATE TABLE purchase_orders (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,           -- PO/{FY}/{NNNN}
  series_id INTEGER NOT NULL,
  vendor_id INTEGER NOT NULL,
  vendor_snap_json TEXT NOT NULL,
  rfq_id INTEGER,                        -- nullable
  rfq_vendor_id INTEGER,                 -- nullable; back-link to winning vendor row
  date INTEGER NOT NULL,
  expected_date INTEGER,
  status TEXT NOT NULL,                  -- draft|sent|partially_received|received|closed|cancelled
  ship_to_godown_id INTEGER NOT NULL,    -- destination
  rcm_applicable INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  subtotal_paise INTEGER NOT NULL,
  tax_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE purchase_order_lines (
  id INTEGER PRIMARY KEY,
  po_id INTEGER NOT NULL,
  line_no INTEGER NOT NULL,
  item_id INTEGER,
  item_snap_json TEXT NOT NULL,
  description_snap TEXT NOT NULL,
  qty_ordered REAL NOT NULL,
  qty_received REAL NOT NULL DEFAULT 0,
  qty_billed REAL NOT NULL DEFAULT 0,
  rate_paise INTEGER NOT NULL,
  discount_pct REAL DEFAULT 0,
  gst_rate REAL NOT NULL,
  amount_paise INTEGER NOT NULL,
  tax_paise INTEGER NOT NULL,
  total_paise INTEGER NOT NULL
);

-- Goods Receipt Notes
CREATE TABLE grns (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,           -- GRN/{FY}/{NNNN}
  series_id INTEGER NOT NULL,
  vendor_id INTEGER NOT NULL,
  po_id INTEGER,                         -- nullable; standalone GRNs allowed
  vendor_invoice_ref TEXT,               -- vendor's bill/DC number on the box
  vehicle_no TEXT,
  date INTEGER NOT NULL,
  godown_id INTEGER NOT NULL,
  qc_status TEXT NOT NULL,               -- pending|passed|partial|failed|na
  status TEXT NOT NULL,                  -- draft|posted|cancelled
  notes TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE grn_lines (
  id INTEGER PRIMARY KEY,
  grn_id INTEGER NOT NULL,
  line_no INTEGER NOT NULL,
  po_line_id INTEGER,                    -- nullable for standalone GRN
  item_id INTEGER NOT NULL,
  item_snap_json TEXT NOT NULL,
  qty_received REAL NOT NULL,
  qty_accepted REAL NOT NULL,
  qty_rejected REAL NOT NULL DEFAULT 0,
  rejection_reason TEXT,
  batch_no TEXT,
  mfg_date INTEGER,
  expiry_date INTEGER,
  provisional_rate_paise INTEGER NOT NULL  -- from PO line, used for stock valuation until Bill matches
);

-- 3-way match runs
CREATE TABLE match_runs (
  id INTEGER PRIMARY KEY,
  bill_id INTEGER NOT NULL,              -- references existing purchases.id
  po_id INTEGER NOT NULL,
  grn_ids_json TEXT NOT NULL,            -- array of GRN ids
  status TEXT NOT NULL,                  -- match|qty_variance|price_variance|both|override
  discrepancies_json TEXT NOT NULL,
  override_reason TEXT,
  override_by_actor TEXT,                -- 'owner' or 'ca'
  run_at INTEGER NOT NULL
);
```

### 4.2 Existing-table extensions

```sql
ALTER TABLE delivery_challans ADD COLUMN so_id INTEGER;        -- back-link
ALTER TABLE delivery_challans ADD COLUMN so_lines_json TEXT;   -- snapshot of SO lines fulfilled
ALTER TABLE invoices         ADD COLUMN so_id INTEGER;
ALTER TABLE invoices         ADD COLUMN dc_ids_json TEXT;      -- array; multi-DC consolidation
ALTER TABLE purchases        ADD COLUMN po_id INTEGER;
ALTER TABLE purchases        ADD COLUMN grn_ids_json TEXT;     -- array
ALTER TABLE stock_movements  ADD COLUMN source_doc_type TEXT;  -- 'invoice','purchase','dc','grn','transfer'
ALTER TABLE stock_movements  ADD COLUMN source_doc_id INTEGER;
```

`source_doc_type` is the dedup key. Stock movement is created exactly once per physical event. See §6 for the cascade rules.

### 4.3 Series

Five new series rows seeded in `invoice_series` table (or its sibling — extend if Bahi keeps invoice/purchase series in separate tables, the agent picks; consistent naming wins):

| Series | Default prefix | User-overridable |
|---|---|---|
| Quote | `Q/{FY}/{NNNN}` | yes |
| Sales Order | `SO/{FY}/{NNNN}` | yes |
| RFQ | `RFQ/{FY}/{NNNN}` | yes |
| Purchase Order | `PO/{FY}/{NNNN}` | yes |
| GRN | `GRN/{FY}/{NNNN}` | yes |

Resets per FY, same as invoices. Holes from cancelled docs are not refilled (consistent with Bahi today).

## 5. State machines

### 5.1 Quote

```
draft ──send──▶ sent ──accept──▶ accepted ──convert_to_so──▶ superseded
                  │                  
                  ├──reject────────▶ rejected
                  ├──expire────────▶ expired (auto on valid_until pass)
                  └──revise────────▶ creates child quote, parent → superseded
```

Editable in `draft` only. Once `sent`, edits create a revision. Revisions chain via `parent_quote_id`. Numbering: `Q/26-27/0001-R1`, `-R2`. The parent moves to `superseded` and is read-only.

`expired` is computed live from `valid_until`. No background job — UI badge derived at list time. Audit log entry posted only when user explicitly clicks "Mark expired" or when it auto-fires once on next quote-list view (debounced, audit-safe).

### 5.2 Sales Order

```
draft (only if user wanted to stage it) ──confirm──▶ open
                                                       │
            ┌──────── cancel (only if no DC/Invoice) ──┘
            ▼
        cancelled

open ──any DC posted, qty_delivered < qty_ordered ──▶ partially_fulfilled
     ──any Invoice posted, qty_invoiced == qty_ordered AND qty_delivered == qty_ordered ──▶ fulfilled
fulfilled ──manual close──▶ closed
```

Cancellation is hard-blocked once any downstream DC or Invoice exists. To "undo" you cancel the downstream doc first.

### 5.3 RFQ

```
draft ──send──▶ sent ──close──▶ closed (winner selected → PO)
              │
              └──cancel──▶ cancelled
```

Vendor responses are recorded against `rfq_vendors` rows. Comparison view (§7.4) shows side-by-side. User selects one winner. Closing the RFQ without selecting a winner is allowed (status = `closed`, no PO). Minimum 1 vendor required to send (single-vendor RFQ supported as a bid-request flow).

### 5.4 Purchase Order

```
draft ──send──▶ sent ──any GRN posted──▶ partially_received
                       ──qty_received == qty_ordered──▶ received
received ──Bill posted, qty_billed == qty_received──▶ closed
```

Cancellation of `sent` POs is allowed only before any GRN. After GRN, the PO must be closed via the natural flow (or the GRN cancelled first).

### 5.5 GRN

```
draft ──post──▶ posted (stock movement fires)
              │
              └──cancel (admin, audit-logged, posts reversing stock movement)
```

QC fields (`qc_status`, `qc_rejected_qty`, reason) are captured at posting time. `qty_accepted` is what hits stock; `qty_rejected` is recorded but does not move stock (returns are a separate inward-return DC against the vendor — existing pattern).

GRN cancellation is rare and risky. Bahi's existing `Ctrl+Z`-via-counter-entry pattern applies: cancel GRN posts a reversing stock movement, both the original and the reversal stay in the log.

### 5.6 Three-way match

Runs implicitly on every Bill that has a `po_id`. Compares:

1. PO line qty/rate × all linked GRN line qty (from `purchases.grn_ids_json`) × Bill line qty/rate.

Outputs status:

- `match` — all three agree within tolerance (default ±0.5% on rate, exact on qty).
- `qty_variance` — Bill qty ≠ GRN accepted qty.
- `price_variance` — Bill rate differs from PO rate beyond tolerance.
- `both`.
- `override` — user accepted the variance with a written reason.

Tolerance is settable per file in `meta` table. Default ±0.5% rate, 0% qty.

Exceptions surface in `Purchases → 3-way match` and on the Bill detail page. CA mode flags exceptions as review items.

## 6. Stock cascade rules

The single most important architectural rule:

> **Physical movement docs (DC, GRN) are the source of truth for stock. Tax docs (Invoice, Bill) are the source of truth for books. Each piece of stock moves exactly once. Each rupee posts to GL exactly once.**

Operationally:

| Document | Posts to GL? | Posts to stock? |
|---|---|---|
| Quote | no | no |
| SO | no | no (commits/allocates only — counter, not movement) |
| DC linked to SO/Invoice | no | yes (outward) |
| Invoice **with** linked DC(s) | yes (sales + GST + COGS) | no — already moved by DC |
| Invoice **without** linked DC | yes (sales + GST + COGS) | yes (outward) — current behavior preserved |
| RFQ | no | no |
| PO | no | no (commits/expects only — counter, not movement) |
| GRN | no | yes (inward, at provisional rate from PO) |
| Bill **with** linked GRN(s) | yes (purchases + GST input) | no — already moved by GRN |
| Bill **without** linked GRN | yes (purchases + GST input) | yes (inward) — current behavior preserved |
| 3-way match price variance | yes (adjustment to Stock-in-Hand or Purchase Variance account) | no |

The dedup gate is `stock_movements.source_doc_type` + `source_doc_id`. The posting bridge for Invoice/Bill checks: "is there already a stock movement for the linked DC/GRN covering these lines?" — if yes, skip the stock leg and write the GL leg only.

**Price variance posting** (3-way match): if Bill rate > GRN provisional rate, the difference (qty × rate_diff) posts:

- Dr Purchase Price Variance (or Stock-in-Hand if user chooses retroactive valuation)
- Cr Vendor Payable

User chooses per-file default in Settings. Default is `Purchase Price Variance` (P&L account, simpler).

**Stock allocation counters** (SO and PO `qty_ordered` minus `qty_delivered`/`qty_received`) are not stock movements. They are derived columns surfaced in dashboards as "committed stock" / "incoming stock," never written to `stock_movements`.

## 7. UI

### 7.1 Sidebar restructure

Operations is not a separate top-level group. It folds into existing **Sales** and **Purchases** sidebar groups, preserving the navigation muscle memory of current Bahi users.

```
Sales
├ Customers (existing)
├ Items / services (existing)
├ Quotes               ← NEW
│  └ + New quote       ← NEW
├ Sales orders         ← NEW
│  └ + New SO          ← NEW
├ Invoices (existing) — shows "from SO" badge where applicable
├ + New invoice (existing, accepts ?fromSO=N)
├ Credit notes (existing)
├ Delivery challans (existing) — accepts ?fromSO=N
└ Sales register (existing)

Purchases
├ Vendors (existing)
├ RFQs                 ← NEW
│  └ + New RFQ         ← NEW
├ Purchase orders      ← NEW
│  └ + New PO          ← NEW
├ GRNs                 ← NEW
│  └ + New GRN         ← NEW
├ 3-way match          ← NEW (exception list view)
├ Bills (existing) — shows "from GRN" badge where applicable
├ + New bill (existing, accepts ?fromGRN=N)
├ Debit notes (existing)
└ Purchase register (existing)
```

### 7.2 List views

Standard Bahi list pattern. Columns per doc:

- **Quotes**: number, date, customer, total, validity badge, status, action menu (send, accept, reject, revise, → SO).
- **SOs**: number, date, customer, promised date, qty progress bar (delivered/ordered, invoiced/ordered), status, action menu (→ DC, → Invoice, cancel).
- **RFQs**: number, date, subject, vendor count, response count, status, action menu (compare, → PO).
- **POs**: number, date, vendor, expected date, qty progress, status, action menu (→ GRN, cancel).
- **GRNs**: number, date, vendor, PO link, QC badge, status, action menu (→ Bill, cancel).
- **3-way match**: bill number, vendor, PO, GRN(s), variance type, amount, override status, action.

### 7.3 Detail / form views

Three column layout consistent with Bahi today:

- Left: doc header (number, date, party, status badge, action buttons).
- Center: line items grid with the same cell-level shortcuts as the existing invoice form.
- Right: chain panel — shows upstream and downstream linked docs (e.g. on a PO, shows the source RFQ above and any GRNs/Bills below).

Action buttons on detail view are state-aware. A `draft` quote shows Send / Edit / Discard. An `accepted` quote shows Convert to SO / View SO. A superseded quote shows Open child / View parent.

### 7.4 RFQ comparison view

Special view at `#/rfq/N/compare`. Side-by-side columns per responding vendor, rows per RFQ line, cell shows their rate × computed total. Bottom row shows total per vendor. Highlight cheapest cell per row in green, highlight cheapest total in green. Selecting a vendor row triggers "Convert to PO with {Vendor}" — new PO inherits RFQ lines with that vendor's rates.

### 7.5 Conversion modals

`Quote → SO`: prompts for promised date and any line tweaks. SO inherits all line snapshots; can drop lines but not change rates (rate change → revise the quote first). Posts the conversion + supersedes the parent quote in one transaction.

`SO → DC`: pick lines and quantities to deliver (default = full remaining). Captures vehicle/transporter. Posts DC + stock outward + updates `qty_delivered` on SO lines.

`SO → Invoice`: pick lines and quantities to invoice (default = remaining undelivered or based on existing DCs — see below). Two paths:

1. **Direct from SO** (no DC) — invoice posts both GL and stock.
2. **From SO via DC(s)** — invoice consolidates one or more existing DCs. Stock already moved; invoice posts GL only. Multi-DC consolidation supported (DCs from same SO and same customer only).

`PO → GRN`: select lines and received qty, capture QC, vehicle, vendor's invoice ref. Posts GRN + stock inward at provisional rate.

`GRN → Bill`: pick GRN(s) — multi-GRN consolidation supported (same vendor, optionally same PO). Bill posts GL only. 3-way match runs automatically; variance surfaces inline before save with an Override + reason flow if user wants to proceed despite mismatch.

### 7.6 PDFs

Each new doc type gets its own PDF generator following the existing Bahi invoice PDF pattern (Devanagari support, ₹ glyph, signature block):

- Quote PDF — header, validity, line items, T&C block, accept signature.
- SO confirmation PDF — for sending to customer as an order acknowledgement.
- RFQ PDF — header, subject, line items, response-by date, vendor block.
- PO PDF — header, vendor, ship-to, line items, T&C, signature.
- GRN PDF — header, vendor, vehicle, line items, QC notes, receiver signature.
- 3-way match exception report PDF — vendor, PO/GRN/Bill numbers, variance breakdown, override reason.

All PDFs share the existing letterhead block (company name, GSTIN, address, logo).

### 7.7 Keyboard shortcuts

Extend the Tally-parity scheme:

| Key | Action |
|---|---|
| `Alt+Q` | New Quote |
| `Alt+O` | New Sales Order |
| `Alt+R` | New RFQ |
| `Alt+P` | New Purchase Order |
| `Alt+G` | New GRN |
| `Alt+M` | Open 3-way match list |
| `Ctrl+Enter` (in convert modal) | Confirm conversion |

`F8` (sales) and `F9` (purchase) keep existing direct-entry behaviour.

### 7.8 Empty / error states

Each new list shows a one-sentence empty state explaining what the doc is and a "+ New X" CTA. Errors follow the existing Bahi pattern: red banner at top of form, field-level red text, hard-block save until fixes.

## 8. AI features (per-feature integration, matching v2 pattern)

Each AI feature is independently toggleable in Settings → AI. All work with both local Transformers.js and BYOK cloud, except where vision is required (BYOK only — local vision models not viable in the single-file constraint yet).

### 8.1 Quote-from-text (LLM)

User pastes a customer email or WhatsApp message into a draft quote screen. Model returns structured line items (item match against existing master via fuzzy lookup, falls back to free-text item with HSN suggestion). User reviews, edits, posts. Same pattern as v2's voucher-from-text.

### 8.2 Quote-from-photo (BYOK vision only)

User uploads phone photo of a handwritten quote pad page. Vision model extracts line items into draft quote. v1.0: v1.0 only ships if BYOK vision is connected; otherwise feature is hidden.

### 8.3 RFQ broadcast drafting (LLM)

User creates an RFQ; "Draft vendor emails" button generates one personalized email per `rfq_vendors` row, including the line items table and response-by date. User reviews and copies into their email client. No SMTP integration — Bahi never sends. Match Bahi's existing "no telemetry, no network egress beyond CDN" stance.

### 8.4 Vendor quote OCR (existing bill OCR, extended)

When `rfq_vendors.response_doc_attachment_id` is set with a PDF/image, the existing bill OCR pipeline is invoked with a different output schema (RFQ-line-keyed instead of GL-account-keyed). Result populates `response_total_paise` and per-line vendor rates for the comparison view.

### 8.5 Bill OCR routing (extension)

Existing Bahi bill OCR is extended: after extraction, the pipeline checks for open POs/GRNs against the same vendor. If a likely match is found (vendor + amount range + date proximity), the bill draft pre-fills `po_id` and `grn_ids_json`. User confirms the link. No LLM call needed for the matching step — it's pure rules over local data.

### 8.6 3-way match (rules only, no LLM)

Already covered in §5.6. Pure deterministic comparison. Reuses Bahi's existing reconciliation engine pattern.

### 8.7 Conversion automation (no AI, deterministic)

All Quote→SO, SO→DC, SO→Invoice, PO→GRN, GRN→Bill conversions are pure deterministic mapping. No model in the loop. Snapshots cascade forward at conversion time.

### 8.8 What's deliberately NOT AI-driven

- Item master matching during conversion — uses deterministic ID joins, not fuzzy. Fuzzy matching only on free-text input paths (§8.1).
- Vendor selection on RFQ winner — user choice, no scoring model.
- 3-way match override approval — user reason required, no model judgment.
- Forecasting / demand planning — out of scope.

## 9. Snapshot pattern (extension of Bahi's existing pattern)

Every doc that participates in the chain captures snapshots at creation and at each forward conversion. The principle: a printed PDF, a tax return, an audit query against a doc from any past date must reproduce exactly what was on the doc when it was originally posted, irrespective of any later master edits.

What's snapshotted on each doc:

- **Quote**: customer (name, GSTIN, billing address, place of supply); each line item (item name, HSN, UoM, description, gst_rate at quote date).
- **SO**: re-snapshots at conversion time (customer might have changed since quote sent); line items inherit from quote_lines snapshots; if line edited at conversion, fresh snapshot.
- **RFQ**: each `rfq_vendors` row snapshots vendor block at send time.
- **PO**: vendor, ship-to godown, line items snapshotted fresh at PO creation (RFQ winner → PO is a fresh snapshot, not a copy).
- **GRN**: vendor, item snapshots inherited from PO line if linked, else fresh.
- **Bill**: existing Bahi purchase snapshots apply; extended to also capture `po_id` and `grn_ids_json`.

Snapshot integrity check: extend the existing Debug Console round-trip test to include ops doc round-trip — a PO from FY 26-27 must re-render with its original vendor block even if the vendor is renamed in FY 27-28.

## 10. Audit log additions

New event types append to the existing hash-chained `audit_log`:

```
quote.create, quote.send, quote.accept, quote.reject, quote.expire,
quote.revise, quote.convert_to_so, quote.cancel
so.create, so.confirm, so.partial_fulfill, so.fulfill, so.close, so.cancel
rfq.create, rfq.send, rfq.vendor_response, rfq.select_winner, rfq.close, rfq.cancel
po.create, po.send, po.partial_receive, po.receive, po.close, po.cancel
grn.create, grn.post, grn.cancel, grn.qc_pass, grn.qc_fail
match.3way.run, match.3way.discrepancy, match.3way.override
```

Each entry follows existing payload conventions: `prev_hash || origin || canonicalJson(payload) || booksHash`, ECDSA-P256 signed, `auditActor()` tags `'owner'` or `'ca'`.

CA mode reconciliation view (§5 of Bahi README) handles divergent ops doc states the same way as ledger entries — the Layer 3 ancestry check fires identically.

## 11. Reports

New reports under existing `Reports` group:

- **Open quotes aging** — bucketed by days since sent (0–7 / 8–30 / 30+ / expired).
- **Open SOs** — by promised date; flag overdue.
- **Quote conversion ratio** — accepted/sent over date range.
- **Open POs** — by expected date; flag overdue.
- **Pending GRNs** — POs with `partially_received` and aged.
- **Pending Bills** — GRNs without matching Bill, aged.
- **3-way match exceptions** — variance type, amount, override status, reasoner.
- **Backorder report** — SO lines with `qty_ordered > qty_delivered` and SO past promised date.
- **Committed stock** — by item, sum of open SO qty_ordered − qty_delivered.
- **Incoming stock** — by item, sum of open PO qty_ordered − qty_received.

Existing Trial Balance, P&L, Balance Sheet, Day Book, Sales Register, Purchase Register: unchanged. They consume the ledger, which Operations does not touch directly. Operations docs do not appear in any GL report.

Dashboard additions (existing dashboard route): one row of KPIs across the top: "Open quotes (₹)", "Open SOs (₹)", "Open POs (₹)", "Pending GRNs (count)", "3-way exceptions (count)". Click-through to relevant list view.

## 12. Tally migration extension

Extend the existing parser to walk additional Tally voucher types:

- `Sales Order` → `sales_orders` + `sales_order_lines`
- `Purchase Order` → `purchase_orders` + `purchase_order_lines`
- `Receipt Note` → `grns` + `grn_lines`
- `Delivery Note` → existing `delivery_challans` table (Bahi already has this; extend to capture SO link if Tally has one)
- `Quotation` → `quotes` + `quote_lines`

Mapping wizard adds an Operations section. Conflicts (e.g. PO references a vendor not in Tally master) hard-block until resolved, same as existing pattern.

Posting bridges reused — every imported PO goes through `postPOToBooks()` (which posts nothing, only writes the row, but still increments `audit_log`). Atomic transaction wrap is preserved.

## 13. CA mode integration

CA mode views Operations docs as **read-mostly**. CA can:

- View any ops doc in any state.
- Add annotations on any ops doc.
- Mark any ops doc as reviewed.
- Run 3-way match exception report.
- Flag SO/PO open-at-FY-end commentary in the review report PDF.

CA cannot:

- Convert Quote → SO (state transitions are owner actions).
- Override 3-way match (override is an owner action; CA can flag).
- Create / cancel ops docs.

CA review report PDF (existing) gains a new section: **Operations status at period end** — counts of open quotes/SOs/POs/GRNs, exceptions list, optional commentary block.

## 14. Compliance hooks

- **e-invoicing readiness**: SO → Invoice conversion is the natural IRN trigger point. v1.0 stubs the IRN field on invoice (already present in Bahi) but does not generate. Architecture is now ready for a future GSP integration without restructure.
- **e-way bill**: existing Bahi e-way generation continues to fire from Invoice or DC. SO link is included in the EWB metadata so cross-doc references work.
- **GSTR-1**: unchanged. Operations docs do not appear in GSTR-1. Only Invoices do (already correct in Bahi).
- **GSTR-3B**: unchanged.
- **Period locks**: extended. A locked period also blocks ops doc backdated state transitions for that range. UI flags amendments same as existing.

## 15. Failure model additions

Append to Bahi's existing Failure Model table:

| Scenario | Protection | What the user sees |
|---|---|---|
| User tries to cancel SO with downstream DC/Invoice | Hard block | Modal: "Cancel the X downstream document(s) first" with list |
| Quote modified after sent | Hard block | "Sent quotes can't be edited. Revise it instead?" with Revise CTA |
| GRN posted, then PO cancelled attempt | Hard block | "Cancel the GRN first; this PO has received stock" |
| Multi-GRN bill consolidation across vendors | Hard block at form level | "All GRNs on a single bill must be from the same vendor" |
| 3-way match price variance, user overrides without reason | Hard block at save | Reason field required, freeform text minimum 10 chars |
| Convert SO → Invoice with insufficient stock | Soft warn | "Stock at this godown is X, invoicing Y. Continue? (negative stock allowed if file setting permits)" |
| Quote linked to deleted customer | Cannot happen — customers cannot be hard-deleted in Bahi | n/a |
| Snapshot integrity drift | Round-trip test in Debug Console | "Quote Q/26-27/0042 re-renders differently from posted version" — error with diff |
| GRN provisional rate ≠ Bill rate, override happens | Audit-log entry + match_runs row | "Variance ₹X overridden — reason: …" visible on Bill detail |
| Numbering gap from cancelled Q/SO/PO/GRN | Documented behaviour, no protection | Numbering is monotonic; cancelled docs leave numeric holes (matches Bahi's existing invoice behaviour) |

## 16. Permissions, modes, settings

- **First-run mode picker** unchanged — Owner/CA. No new mode introduced.
- **Settings → Operations** (new sub-page):
  - Quote validity default (days)
  - PO ship-to default godown
  - 3-way match tolerance (rate %, qty %)
  - Price variance posting account (Purchase Price Variance | Stock-in-Hand)
  - Negative stock on invoicing (allow / block)
  - Numbering prefixes (per series)
  - AI feature toggles (per §8 feature, on/off, local/BYOK selector inherits from global LLM provider settings)

## 17. Migration

`meta.schemaVersion` v9 → v10:

1. Create new tables (§4.1).
2. ALTER existing tables (§4.2) — all columns nullable, no defaults required for backward compat.
3. Seed five new series rows.
4. Update `SUPPORTED_FORMAT` constant in code.
5. No data backfill: a v9 file opened with v10 build silently migrates forward to an empty Operations module.
6. v10 file opened by v9 build → existing read-only banner pattern fires (already implemented in Bahi).

Migration is a single transaction. Migration runner appends an `audit_log` entry of type `meta.schema_migrate` with from/to versions.

## 18. Performance and footprint

- Existing build: ~900 KB HTML. Operations adds ~250 KB of UI/logic plus ~50 KB of new SQL definitions in init code. Target: <1.2 MB total.
- New SQLite tables and columns add no measurable startup overhead.
- Lazy-load pattern for Ops module: list views and forms code-split into a separate IIFE block, loaded on first navigation to any `#/quote*`, `#/so*`, `#/rfq*`, `#/po*`, `#/grn*`, or `#/match*` route.
- No new CDN dependencies. PDF generation reuses jsPDF already loaded by Bahi.
- The 6-step Tally migration wizard adds ~30 KB; same lazy-load pattern.

## 19. v1.0 vs v1.1 split

Goal: v1.0 ships the universal core. v1.1 covers the bits that need vision/OCR cycles or are heavier UI work.

### v1.0

- All five new tables and column extensions.
- All five state machines.
- All conversion flows (Quote→SO, SO→DC, SO→Invoice, RFQ→PO, PO→GRN, GRN→Bill).
- 3-way match engine + exception list + override flow.
- All seven new PDFs.
- Sidebar restructure.
- All 10 new reports + dashboard KPI strip.
- Tally migration extension for Quote, SO, PO, GRN.
- Snapshot pattern across all new docs.
- Audit log integration.
- CA mode read-only integration + new review report section.
- Settings → Operations sub-page.
- Quote-from-text (LLM, both local and BYOK).
- RFQ broadcast drafting (LLM).
- Bill OCR routing extension (rules only).
- Schema migration.
- Failure model coverage.

### v1.1

- Quote-from-photo (BYOK vision).
- Vendor quote OCR (extended bill OCR pipeline).
- RFQ comparison view advanced features (delta highlighting, side-by-side T&C diff).
- Multi-DC consolidation on Invoice (single-DC works in v1.0).
- Multi-GRN consolidation on Bill (single-GRN works in v1.0).
- 3-way match exception report PDF (in-app exception list works in v1.0; PDF in v1.1).
- Operations dashboard widgets (full panel; KPI strip ships in v1.0).
- Backorder auto-cancel-after-N-days policy (manual cancel works in v1.0).

Both ship at the same `bahi.naklitechie.com` URL. v1.0 deploys as Bahi v2.x; v1.1 as v2.(x+1). No separate codebase.

## 20. What NOT to do

Hard rules for the implementing agent. Violations are bugs.

- Do not break the single-HTML-file constraint. Everything ships in `index.html`. Lazy-loaded chunks are inside the file via dynamic `import()` of inline blob URLs, same pattern as Bahi today.
- Do not introduce a build step. Vanilla JS + sql.js + JSZip + jsPDF only. No bundler.
- Do not create new top-level sidebar groups. Operations folds into Sales and Purchases (§7.1).
- Do not let any ops doc post to GL except Invoice and Bill (the existing posting paths). Stock posts only via DC and GRN, dedup'd via `source_doc_type`.
- Do not edit `audit_log` rows. Append only. Cancellations are reversing entries.
- Do not let any conversion modal re-fetch master data — it must use snapshots from the upstream doc. Master changes after the upstream doc was created must not affect the downstream.
- Do not add background timers / polling. State transitions like "expired" are computed on view, not pushed.
- Do not call any non-CDN external URL. All AI features go through Bahi's existing local Transformers.js or the user-configured BYOK provider — no new endpoints.
- Do not change existing Invoice or Bill posting paths. Extend by checking for linked DC/GRN before the stock leg.
- Do not name accounts or series with hardcoded enum strings — extend the existing reference data subsystem (§Masters in Bahi README).
- Do not introduce new CDN dependencies beyond sql.js, JSZip, jsPDF, and existing fonts.
- Do not lose data on cancellation — every cancellation is a state transition, not a row delete.
- Do not gate features behind login or account creation. None of NakliTechie does this.

## 21. Gate artifacts per milestone

Implementing agent ships, in order, with the following gates Bhai will smoke-test before unblocking the next:

**Gate 1 — schema and engine**
- v10 migration runs on all three sample `.khata` files (pharma, manufacturing, consulting) without error.
- Existing 45 pytest tests still pass.
- New `audit_log` events appear correctly chained in Debug Console.
- New tables visible in Debug Console schema browser.

**Gate 2 — sales chain end-to-end**
- Create Quote → Send → Accept → Convert to SO → Create DC → Create Invoice path completes.
- Snapshots survive: rename customer mid-chain, all upstream PDFs reprint with original name.
- Stock moves once (on DC), not twice.
- 7 new audit events appear in chain.

**Gate 3 — procurement chain end-to-end**
- RFQ → 2 vendor responses → comparison view → select winner → PO → GRN → Bill path completes.
- 3-way match runs automatically; both clean match and price variance scenarios tested.
- Stock moves once (on GRN), not twice.

**Gate 4 — UI polish, PDFs, reports**
- All 7 PDFs render correctly with Devanagari sample data.
- All 10 reports populate from sample data.
- Dashboard KPI strip renders.

**Gate 5 — AI features (v1.0 subset)**
- Quote-from-text round-trips with both local Transformers.js and a BYOK provider.
- RFQ broadcast drafts produce per-vendor email text with line items table.
- Bill OCR routing pre-fills `po_id`/`grn_ids_json` correctly on a sample with a known prior PO.

**Gate 6 — Tally migration**
- Sample Tally export with quotes/SOs/POs/GRNs imports cleanly.
- Atomic rollback verified by injecting a parser error mid-import.

**Gate 7 — release candidate**
- Round-trip test extended for ops docs passes.
- 30-day backup nudge unaffected.
- Crash recovery panel unaffected.
- Bahi v2.x release notes drafted.

Each gate produces a short markdown report in `/docs/gate-N-report.md` for Bhai's review.

## 22. Escalation protocol

The agent proceeds autonomously on naming choices, implementation details, debugging, tuning, and trying alternatives. The agent stops and asks Bhai only when:

- A locked decision in this spec conflicts with an existing Bahi behaviour the agent discovers in code.
- A new dependency is needed (must be CDN-loaded, must be vetted before adoption).
- A genuine product ambiguity surfaces that this spec didn't anticipate and that materially changes user-facing behaviour.
- A stock or GL invariant cannot be preserved by the cascade rules in §6 (escalate immediately, do not "best-effort" around it).

For everything else: decide, document the decision in a code comment near the relevant function, proceed.

---

*End of bahi-ops-001 v0.2. Spec locked for handoff.*
