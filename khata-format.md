# `.khata` — Open file format for browser-native accounting

> *Specification for `.khata` v1.0 — the file format used by [Bahi](https://github.com/NakliTechie/Bahi) and intended to outlive any single app.*

This document is the canonical specification for the `.khata` file format. It describes the on-disk structure, the manifest schema, the SQLite schema, the audit log hashing algorithm, and the historical-integrity invariants every conforming implementation MUST honour.

The reference implementation is [Bahi](https://github.com/NakliTechie/Bahi). This spec is versioned independently from any single app — the goal is for `.khata` to outlive Bahi, the same way `.kanzen.json` and the Postman v2.1 collection format are tool-agnostic.

**Spec version: 1.0**
**Status: Stable for v1.0; new fields are additive, schema migrations are explicit.**
**License: CC0 / public domain. Use it. Fork it. Build a competing reader.**

---

## 1. What is `.khata`?

`.khata` (खाता — Hindi for *account / ledger*) is a single-file, browser-native, local-first accounting format. The whole of a company's books — chart of accounts, customers, items, invoices, payments, advances, journal entries, audit log, and rolling snapshots — lives inside one zip with the `.khata` extension on the user's own disk.

Design goals (in priority order):

1. **User-owned storage.** The `.khata` file lives on the user's disk. No server, no account, no cloud, no telemetry. The user can back it up, copy it, version-control it, or hand it to their CA — same as a Tally `.tdl` or a spreadsheet.
2. **Tamper evidence.** The audit log is append-only and cryptographically chained. Every state change is recorded. A reader can verify the chain on every open and detect any silent edit.
3. **Historical integrity.** Posted records freeze their inputs. Reprinting a 6-month-old invoice shows the customer's name *as it was at the time of posting*, not the current name. Editing the customer master never silently relabels old transactions.
4. **GST-native.** Built from day one for the Indian GST regime — CGST/SGST/IGST routing, GSTR-1 portal upload, composition scheme, multiple invoice series, advance receipts with GST on advance.
5. **Open standard.** This document. Anyone can implement a `.khata` reader / writer.
6. **Forward-compatible by construction.** State codes are ISO 3166-2:IN (not GSTIN numeric), tax rates are date-versioned reference data (not hardcoded enums), schema migrations are tracked via `meta.schemaVersion`.

---

## 2. File structure

A `.khata` file is a standard ZIP archive with the `.khata` extension. The contents:

```
mybooks.khata  (zip)
├── manifest.json       Metadata, schema version, integrity hashes, audit head, public key
├── books.sqlite        The double-entry ledger (SQLite database file)
├── snapshots/          Rolling snapshots of previous saves (Section 6)
│   ├── 2026-04-07T10-15-23-000Z-abc123def456.sqlite
│   ├── 2026-04-07T11-02-44-000Z-def456abc789.sqlite
│   └── ...
├── attachments/        User-uploaded bills, receipts, scans (Section 7)
│   ├── invoices/
│   ├── receipts/
│   └── scans/
└── exports/            Cached report exports (optional)
```

The MIME type is `application/x-khata` (custom — there is no IANA registration). Implementations MAY use `application/zip` for fallback compatibility with generic zip tools.

The zip itself is uncompressed or DEFLATE-compressed. Implementations SHOULD use DEFLATE for files in `snapshots/` and `attachments/` because the SQLite snapshots are highly compressible.

A conforming reader MUST tolerate the absence of `snapshots/`, `attachments/`, and `exports/` — only `manifest.json` and `books.sqlite` are mandatory. A conforming writer MUST always write `manifest.json` and `books.sqlite`.

---

## 3. `manifest.json` schema

The manifest is JSON. UTF-8, no BOM, pretty-printed (2-space indent recommended for human inspection but not required). Top-level keys:

```json
{
  "khataFormatVersion": "1.0",
  "schemaVersion": 5,
  "workspaceId": "550e8400-e29b-41d4-a716-446655440000",
  "createdAt": "2026-04-07T10:00:00.000Z",
  "lastModifiedAt": "2026-04-07T14:32:11.000Z",

  "company": {
    "name": "Acme Services Pvt Ltd",
    "trade_name": "Acme",
    "company_type": "private-limited",
    "gstin": "27AAAPL1234C1ZV",
    "pan": "AAAPL1234C",
    "tan": "PUNA12345B",
    "state": "MH",
    "stateName": "Maharashtra",
    "gstinStateCode": "27",
    "address": "12 MG Road, Mumbai 400001",
    "fy_start": "2026-04-01",
    "composition": { "enabled": false },
    "changeHistory": []
  },

  "uiTier": "everything",

  "snapshots": [
    {
      "filename": "2026-04-07T10-15-23-000Z-abc123def456.sqlite",
      "ts": "2026-04-07T10:15:23.000Z",
      "auditHead": "abc123def456...",
      "booksHash": "sha256-of-the-snapshot-bytes",
      "sizeBytes": 53248,
      "kind": "auto"
    }
  ],

  "integrity": {
    "booksHash": "sha256-of-the-current-books.sqlite",
    "auditHead": "current-audit-chain-head-hash",
    "signedBy": { "kty": "EC", "crv": "P-256", "x": "...", "y": "..." }
  },

  "modeHistory": [
    { "ts": "2026-04-07T10:00:00.000Z", "mode": "owner" }
  ]
}
```

### 3.1 Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `khataFormatVersion` | string | yes | Format version, semver-style. Currently `"1.0"`. |
| `schemaVersion` | integer | yes | SQLite schema version (Section 4). Drives migrations. |
| `workspaceId` | string (UUID) | yes | Stable ID for this company. Survives renames. Used by wrong-file detection. |
| `createdAt` | string (ISO 8601) | yes | When the file was first created. Never changes. |
| `lastModifiedAt` | string (ISO 8601) | yes | Updated on every successful save. |
| `company` | object | yes | Company identity block. See 3.2. |
| `uiTier` | string | yes | One of `freelancer` / `service` / `goods` / `everything`. UI hint only — engine ignores. |
| `snapshots` | array | yes | Snapshot index. See Section 6. |
| `integrity` | object | yes | Integrity hashes + signing key. See 3.3. |
| `modeHistory` | array | no | Owner / CA mode toggles. See 3.4. |

### 3.2 `company` block

The canonical identity of the company that owns this file. Edits to any of these fields MUST be logged in the audit log AND added to `company.changeHistory`.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Legal name. The primary identifier. |
| `trade_name` | string | no | Optional trade name (when different from legal name). |
| `company_type` | string | no | One of `proprietorship`, `partnership`, `llp`, `private-limited`, `public-limited`, `huf`, `other`. |
| `gstin` | string | no | 15-character GSTIN. Optional for entities below the threshold. |
| `pan` | string | no | 10-character PAN. Auto-derived from GSTIN positions 3..12 when GSTIN is present. |
| `tan` | string | no | 10-character TAN for TDS deductors. |
| `state` | string | yes | **ISO 3166-2:IN code** (`MH`, `KA`, `TN`, etc). The canonical FK used everywhere in the format. NOT the full name and NOT the GSTIN numeric code. |
| `stateName` | string | yes | Denormalized human-readable state name (e.g., `"Maharashtra"`). Convenience field — derived from `state`. |
| `gstinStateCode` | string | no | Denormalized GSTIN 2-digit state code (e.g., `"27"`). Convenience field for GST routing. |
| `address` | string | no | Free-form registered address. |
| `fy_start` | string (ISO 8601 date) | no | Financial year start date. Defaults to April 1 of the FY in which the file was created. |
| `composition` | object | no | Composition scheme flag. See 3.2.1. |
| `changeHistory` | array | no | Per-field edit history. See 3.2.2. |

#### 3.2.1 `company.composition`

```json
{ "enabled": true, "type": "service", "rate": 0.06 }
```

| Field | Type | Description |
|---|---|---|
| `enabled` | boolean | True if the company is registered under the GST composition scheme (Section 10 of the CGST Act). |
| `type` | string | One of `trader`, `restaurant`, `service`. |
| `rate` | number | Composition rate as decimal: `0.01` for trader, `0.05` for restaurant, `0.06` for service (Section 10(2A)). |

When `composition.enabled === true`:

- Sales invoices MUST NOT collect CGST/SGST/IGST
- Sales invoice PDFs MUST print `BILL OF SUPPLY` (not `TAX INVOICE`) and include the mandated Rule 49 disclosure: *"Composition Taxable Person — not eligible to collect tax on supplies"*
- The GSTR-1 export path is replaced by CMP-08 quarterly + GSTR-4 annual

#### 3.2.2 `company.changeHistory`

```json
[
  {
    "ts": "2026-04-15T09:00:00.000Z",
    "field": "name",
    "oldValue": "Acme Service",
    "newValue": "Acme Services Pvt Ltd",
    "origin": "https://bahi.naklitechie.com"
  }
]
```

Every edit to a tracked field appends one row. Implementations MUST also append a corresponding `company.update` entry to the audit log (Section 5). The wrong-file detection logic (Section 8.2) walks `changeHistory` so legitimate renames don't false-positive against older copies of the same file.

### 3.3 `integrity` block

```json
{
  "booksHash": "a3f4...",
  "auditHead": "9c2e...",
  "signedBy": { "kty": "EC", "crv": "P-256", "x": "...", "y": "..." }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `booksHash` | string (hex SHA-256) | yes | SHA-256 of the `books.sqlite` bytes embedded in this archive. Updated on every save. Readers MUST verify this matches the actual `books.sqlite` content. |
| `auditHead` | string (hex SHA-256) | yes | The hash of the most recent `audit_log` entry. Allows fast head-comparison without walking the chain. |
| `signedBy` | JWK | no | Public key (JSON Web Key, EC P-256) of the keypair currently signing audit log entries. Replaced by a `keypair.rotation` audit entry when the signing key changes (e.g., after a browser data clear). |

### 3.4 `modeHistory`

```json
[
  { "ts": "2026-04-07T10:00:00.000Z", "mode": "owner" },
  { "ts": "2026-05-01T14:30:00.000Z", "mode": "ca", "caName": "Sharma & Associates" }
]
```

Records when the file was opened in owner mode vs CA mode. The CA mode flow is part of Phase 6 of the reference implementation (not yet shipped in v1.0 — but the field is reserved).

---

## 4. `books.sqlite` schema

The ledger is a single SQLite 3 database file. The full DDL is below. Every table is `CREATE TABLE IF NOT EXISTS`. Schema migrations use a `meta(k, v)` row keyed `'schemaVersion'` for tracking the applied version.

### 4.1 Engine tables (Phase 1 — Schema v1)

```sql
CREATE TABLE accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  parent_id INTEGER,
  type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')),
  system_flag INTEGER DEFAULT 0,    -- 1=seed, 2=auto-created (e.g. per-rate sub-account), 0=user-created
  archived INTEGER DEFAULT 0
);

CREATE TABLE entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  posted_at TEXT NOT NULL,           -- ISO 8601
  voucher_type TEXT NOT NULL,        -- 'sales' | 'receipt' | 'payment' | 'journal' | 'contra' | 'purchase'
  voucher_ref TEXT,                  -- e.g. invoice number
  narration TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL,
  reversed_by_id INTEGER,
  is_amendment INTEGER DEFAULT 0
);

CREATE TABLE entry_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL REFERENCES entries(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  debit INTEGER NOT NULL DEFAULT 0,  -- paise
  credit INTEGER NOT NULL DEFAULT 0, -- paise
  account_name TEXT                  -- FROZEN snapshot at posting time (Invariant 7)
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  ref TEXT,
  origin TEXT,                       -- window.location.origin at time of write
  payload TEXT,                      -- canonical JSON
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,                -- sha256(prev_hash || origin || payload)
  signature TEXT                     -- base64 ECDSA P-256 over the hash
);

CREATE TABLE meta (
  k TEXT PRIMARY KEY,
  v TEXT
);
```

Every monetary field is stored as `INTEGER` paise (multiply rupees by 100). Floating-point arithmetic is forbidden in posting paths.

### 4.2 Books tables (Phase 2A — Schema v1)

```sql
CREATE TABLE customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  gstin TEXT,
  pan TEXT,
  state TEXT,                        -- ISO 3166-2:IN code
  email TEXT,
  phone TEXT,
  address TEXT,
  opening_balance INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  hsn_sac TEXT,
  is_service INTEGER DEFAULT 0,
  unit TEXT,
  default_rate INTEGER,              -- paise per unit
  default_tax_rate REAL,             -- 0.00 to 0.28
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_number TEXT NOT NULL UNIQUE,
  series TEXT NOT NULL DEFAULT 'Domestic',
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  invoice_date TEXT NOT NULL,
  due_date TEXT,
  place_of_supply TEXT,              -- ISO state code
  place_of_supply_name TEXT,         -- FROZEN state name (Invariant 4)
  is_export INTEGER DEFAULT 0,
  is_sez INTEGER DEFAULT 0,
  reverse_charge INTEGER DEFAULT 0,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,
  round_off INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',  -- 'draft' | 'posted' | 'cancelled'
  ledger_entry_id INTEGER REFERENCES entries(id),
  company_snapshot TEXT,             -- FROZEN JSON (Invariant 1)
  customer_snapshot TEXT,            -- FROZEN JSON (Invariant 6)
  created_at TEXT NOT NULL
);

CREATE TABLE invoice_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER REFERENCES items(id),
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,              -- FROZEN at posting time (Invariant 3)
  quantity REAL NOT NULL DEFAULT 1,
  unit TEXT,
  rate INTEGER NOT NULL,             -- paise per unit
  discount INTEGER DEFAULT 0,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,            -- 0.00 to 0.28 — FROZEN value (Invariant 2)
  rate_id TEXT,                      -- forensic key into REF.gstRates (e.g. 'gst-18')
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL
);
```

### 4.3 Payments tables (Phase 2B.2 — Schema v4)

```sql
CREATE TABLE payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_number TEXT NOT NULL UNIQUE,
  payment_date TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id),
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL DEFAULT 0,
  payment_mode TEXT,                 -- 'cash' | 'cheque' | 'neft' | 'rtgs' | 'imps' | 'upi' | 'card' | 'other'
  reference TEXT,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  customer_snapshot TEXT,            -- FROZEN
  bank_account_snapshot TEXT,        -- FROZEN account name
  created_at TEXT NOT NULL
);

CREATE TABLE payment_allocations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id INTEGER NOT NULL REFERENCES payments(id),
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  amount INTEGER NOT NULL DEFAULT 0,
  invoice_number_snapshot TEXT       -- FROZEN
);
```

### 4.4 Advances tables (Phase 2B.6 — Schema v5)

```sql
CREATE TABLE advances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advance_number TEXT NOT NULL UNIQUE,
  advance_date TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL,           -- gross paise
  taxable INTEGER NOT NULL,          -- principal portion
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  nature_of_supply TEXT,             -- 'goods' | 'services'
  payment_mode TEXT,
  reference TEXT,
  notes TEXT,
  adjusted_amount INTEGER NOT NULL DEFAULT 0,
  remaining_balance INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'fully-adjusted' | 'refunded'
  ledger_entry_id INTEGER REFERENCES entries(id),
  customer_snapshot TEXT,            -- FROZEN
  bank_account_snapshot TEXT,        -- FROZEN
  created_at TEXT NOT NULL
);

CREATE TABLE advance_adjustments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advance_id INTEGER NOT NULL REFERENCES advances(id),
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  amount INTEGER NOT NULL,
  ledger_entry_id INTEGER REFERENCES entries(id),
  advance_number_snapshot TEXT,
  invoice_number_snapshot TEXT,
  adjusted_at TEXT NOT NULL
);
```

### 4.5 Invoice series table (Phase 2B.7 — Schema v5)

```sql
CREATE TABLE invoice_series (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,         -- 'Domestic' | 'Export' | 'SEZ with payment' | etc
  prefix TEXT NOT NULL,              -- 'INV' | 'EXP' | 'SEZ-WP' | etc
  suffix TEXT,
  starting_number INTEGER NOT NULL DEFAULT 1,
  reset_on_fy INTEGER DEFAULT 1,
  default_for TEXT,                  -- 'domestic' | 'export' | 'sez-wp' | 'sez-wop' | 'bos' | 'credit-note' | NULL
  archived INTEGER DEFAULT 0,
  system_flag INTEGER DEFAULT 0,     -- 1=seeded default, 0=user-created
  created_at TEXT NOT NULL
);
```

The five default series MUST be seeded on file create: Domestic, Export, SEZ with payment, SEZ without payment, Bill of supply.

### 4.6 Schema version progression

| Version | Phase | Changes |
|---|---|---|
| 1 | 2A initial | All Phase 1 + Phase 2A tables |
| 2 | 2A.1 | `invoices.{company_snapshot, customer_snapshot, place_of_supply_name}`, `invoice_lines.hsn_description`, `entry_lines.account_name` |
| 3 | 2A.2 | `invoice_lines.rate_id` |
| 4 | 2B.2 | `payments`, `payment_allocations` tables |
| 5 | 2B.6 + 2B.7 | `advances`, `advance_adjustments`, `invoice_series` tables |

Migration steps SHOULD use `ALTER TABLE ... ADD COLUMN ...` for column additions and `CREATE TABLE IF NOT EXISTS ...` for new tables. Each step MUST be idempotent and MUST update `meta.schemaVersion` on success.

---

## 5. Audit log hashing algorithm

The `audit_log` table is append-only and cryptographically chained. A conforming reader MUST be able to verify the chain, and a conforming writer MUST never `UPDATE` or `DELETE` an `audit_log` row.

### 5.1 Append algorithm

To append an audit entry:

```
1. payload = canonicalJson(payloadObject)
2. ts = ISO 8601 string of current time
3. origin = window.location.origin (or 'file://' if served from local file system)
4. prev_hash = hash from the most recent audit_log row (or '0' * 64 if this is the first row)
5. hash = sha256(prev_hash || origin || payload)
6. signature = base64(ECDSA-P256-sign(privateKey, hash))
7. INSERT INTO audit_log (ts, actor, action, ref, origin, payload, prev_hash, hash, signature) VALUES (...)
```

`canonicalJson` is a deterministic JSON serializer that recursively sorts object keys. This makes the hash reproducible regardless of the order in which fields were assigned to the payload object.

### 5.2 Verify algorithm

```
1. SELECT id, origin, payload, prev_hash, hash FROM audit_log ORDER BY id ASC
2. expected_prev = '0' * 64
3. for each row:
4.     if row.prev_hash != expected_prev: chain is broken at row.id
5.     computed = sha256(expected_prev || row.origin || row.payload)
6.     if computed != row.hash: chain is broken at row.id
7.     expected_prev = row.hash
8. chain is verified
```

A conforming reader MUST run this verification on every file open and surface a clear failure indicator if the chain is broken.

Signature verification (Section 5.3) is recommended but not strictly required for read-only consumers.

### 5.3 Signature scheme

Signatures use ECDSA over P-256 (secp256r1) with SHA-256, via Web Crypto's `crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, privateKey, hexToBytes(hash))`. The result is base64-encoded and stored in `audit_log.signature`.

The public key is stored in `manifest.integrity.signedBy` as a JWK. A reader can verify any signature against this key. If the signing key is rotated (e.g., the user's IndexedDB was cleared and a new keypair was generated), the writer MUST append a `keypair.rotation` audit entry first, then update `manifest.integrity.signedBy` to the new public JWK. The rotation entry's payload MUST include the old `signedBy` value so signature continuity can be reconstructed.

### 5.4 Standard `action` values

Implementations SHOULD use these canonical action keys for interoperability:

| Action | Meaning |
|---|---|
| `file.create` | File was created. First audit entry. |
| `session.start` | A session opened the file. Origin field captures which install. |
| `entry.post` | A double-entry posting was made. `ref` is `entry:{id}`, payload includes the voucher details. |
| `company.update` | A field on `company` was edited. `ref` is the field name, payload has `{field, oldValue, newValue}`. |
| `customer.create` / `item.create` / `account.create` | A master record was added. |
| `snapshot.restore` | A snapshot was restored to a new file. |
| `workspace.fork` | Layer 2 wrong-file detection allocated a fresh workspace ID. |
| `keypair.rotation` | The signing keypair changed. |
| `clock.drift` | The system clock was detected as wildly off from the audit log timestamps. |

Custom actions (per-app extensions) SHOULD use a namespace prefix like `myapp.something`.

---

## 6. Snapshots

The `snapshots/` folder inside the zip holds rolling copies of `books.sqlite` from previous saves. They exist for crash recovery, undo, and forensic reconstruction.

### 6.1 Snapshot file format

Each snapshot is a complete SQLite database file (the bytes of `books.sqlite` as it was at the snapshot's `ts`). Filenames use the pattern:

```
{ISO timestamp with colons replaced by hyphens}-{first 12 hex chars of audit head}.sqlite
```

Example: `2026-04-07T10-15-23-000Z-abc123def456.sqlite`

### 6.2 Snapshot index

Every snapshot file MUST have a corresponding entry in `manifest.snapshots[]`:

```json
{
  "filename": "2026-04-07T10-15-23-000Z-abc123def456.sqlite",
  "ts": "2026-04-07T10:15:23.000Z",
  "auditHead": "abc123def456...",
  "booksHash": "sha256-of-snapshot-bytes",
  "sizeBytes": 53248,
  "kind": "auto"
}
```

| `kind` | Pruned? | When created |
|---|---|---|
| `auto` | Yes (per retention policy) | Captured by the engine on every save |
| `manual` | Never | User clicked "Save snapshot now" |
| `fy-close` | Never | Captured at financial year close |

### 6.3 Retention policy

A conforming writer SHOULD prune `auto` snapshots using a multi-bucket retention policy:

- **Last N saves**: keep the most recent N auto snapshots (recommended N = 10)
- **Last 7 daily**: for each of the previous 7 days (excluding today), keep the most recent auto snapshot from that day
- **Last 12 monthly**: for each of the previous 12 months (excluding current), keep the most recent auto snapshot from that month
- **Permanent**: `manual` and `fy-close` snapshots are never pruned

A snapshot satisfying multiple buckets stays once (set-union semantics). The reference implementation's `pruneSnapshots` function is the canonical algorithm.

---

## 7. Attachments

The `attachments/` folder holds user-uploaded supporting documents (bills, receipts, scans). Subfolder convention:

```
attachments/
├── invoices/        Invoice PDFs (generated or imported)
├── receipts/        Bill / receipt scans, vendor invoices
└── scans/           Other scanned documents
```

Filename convention: `{transaction-ref}-{original-filename}` so an attachment can be matched back to its transaction without a database lookup.

Implementations MAY store attachment metadata (filename, size, hash, link to ledger entry) in a future `attachments` table. v1.0 leaves this open.

---

## 8. Mandatory invariants for conforming implementations

These are the non-negotiable rules. A reader / writer that violates any of these is NOT a conforming `.khata` implementation.

### 8.1 Historical integrity invariants

The eight invariants from `BAHI-AGENT-MSG-HISTORICAL-INTEGRITY.md` (the source-of-truth doc that drove the snapshot pattern):

1. **Company identity is frozen on every posted document.** Reading `invoices.company_snapshot` MUST return the company info as of posting time. Editing `manifest.company.name` MUST NOT change what an existing invoice prints.

2. **Tax rate is frozen on every taxable line.** `invoice_lines.tax_rate` is the literal decimal value at posting time. `invoice_lines.rate_id` is the forensic key into the rate table. Both are immutable.

3. **HSN/SAC description is frozen on every line.** `invoice_lines.hsn_description` MUST be set at posting time from the then-current reference data. Reprint paths MUST read this column, never look up the description from current REF data.

4. **State name is frozen on every address on every document.** `invoices.place_of_supply_name` MUST be set at posting time. The Orissa → Odisha rename is the canonical example: existing transactions should print `Orissa` if they were dated before the rename.

5. **Reversals inherit, they don't re-lookup.** A credit note against an old invoice MUST use the rate from the original invoice, not today's rate. (Phase 3+ feature; the contract is reserved here.)

6. **Customer / vendor master edits don't leak backward.** `invoices.customer_snapshot` MUST be read on reprint. JOINs on `customers` are forbidden in the reprint path.

7. **CoA account renames don't break historical postings.** `entry_lines.account_name` MUST be set at posting time. The P&L / Trial Balance / Ledger views MUST read this column for line-level labels (`COALESCE(l.account_name, a.name)` is the canonical SQL pattern — fall back to live name only for legacy v1 rows).

8. **Audit log is append-only, always.** No `UPDATE` or `DELETE` on `audit_log` ever. The chain is the source of truth for who did what when.

### 8.2 Wrong-file detection layers

A conforming reader SHOULD implement at least the following layers of wrong-file detection:

- **Layer 1**: Identity banner on every file open showing company name + GSTIN + last save timestamp + last actor.
- **Layer 2**: Hard identity check on workspace replace. If a workspace entry matches by ID but has a different name / GSTIN / PAN, walk the incoming file's `manifest.company.changeHistory` — if the existing entry's name appears anywhere in the history (including `oldValue` and `newValue` fields of `name` change rows), treat the file as a legitimate match. Otherwise, block the replace and force the user to add as a new workspace entry.
- **Layer 5**: Fingerprinted export filenames in the form `{slug}-{gstin}-{purpose}-{ts}.{ext}` so recipients can identify the file before opening it.

Layers 3 (audit-log ancestry on refresh) and 4 (export-time identity verification) are reserved for Phase 6 (CA mode) of the reference implementation.

### 8.3 Tax rate lifecycle

A conforming writer MUST treat tax rates as date-versioned reference data, not as a hardcoded enum:

- Rates are stored as `{rateId, rate, type, validFrom, validTo, description}` objects
- Lookups are date-parameterized: `getActiveGstRates(date)` returns the rates in force on `date`
- HSN → rate mapping is also date-versioned: each HSN has a `rateHistory` array
- Validation MUST be inclusion against the date-active set, never enumeration against a constant list
- The literal rate value AND the `rateId` are both stored on `invoice_lines` (Invariant 2)

A retired rate band MUST still validate for transactions in its valid period. A new rate band MUST be picked up by the next refresh of reference data without a code change.

### 8.4 Atomic writes

A conforming writer MUST ensure that a partial write does not corrupt the file. Two acceptable strategies:

1. **Verify-before-write**: Build the new blob in memory, parse it back, run `PRAGMA integrity_check` on the embedded SQLite, and only call `createWritable` after the verify passes. If the verify fails, the original file is untouched.
2. **Staged write**: Write the new blob to a separate location first (OPFS, sibling temp file, etc.), verify it, then atomically replace the original.

The reference implementation uses both: verify-before-write protects against build-time corruption, OPFS staging protects against post-`createWritable` crashes.

---

## 9. Versioning policy

`khataFormatVersion` follows semver:

- **Major** (`1.x → 2.x`): breaking changes that older readers cannot understand. Requires a coordinated upgrade.
- **Minor** (`1.0 → 1.1`): additive changes. New optional fields, new tables. Older readers MUST tolerate them by ignoring unknown fields.
- **Patch** (`1.0 → 1.0.1`): clarifications to this spec, no on-disk changes.

A reader encountering a file with a HIGHER major version than it supports MUST refuse to write to the file (open it in read-only mode) and surface a clear "upgrade your reader" message. A reader encountering a LOWER major version MUST migrate the file forward to its own version on first save.

The `schemaVersion` integer is independent — it tracks the SQLite DDL only, and migrations are defined in Section 4.6.

---

## 10. Reference implementation

The reference implementation is [Bahi](https://github.com/NakliTechie/Bahi). Specifically:

- **Hashing algorithm**: see `appendAuditEntry` and `verifyAuditChain` in `index.html`
- **Snapshot pattern**: see the doc comment near "HISTORICAL INTEGRITY — the snapshot pattern"
- **Rate lifecycle**: see `getActiveGstRates`, `getActiveHsnRate`, `rateIdForDecimal`
- **Schema migrations**: see `runSchemaMigrations`
- **Snapshot pruning**: see `pruneSnapshots`
- **OPFS staging**: see `writeStaging`, `clearStaging`, `getStagingFile`
- **Wrong-file Layer 2**: see the `openHandle` block that walks `changeHistory`

Bahi is the reference for behavior. This document is the reference for the on-disk format. Where they disagree, **this document wins** — Bahi is meant to be eventually replaceable; the format is meant to outlive it.

---

## 11. License

This specification is released into the public domain (CC0). Use it, fork it, build a competing reader, embed it in commercial software, copy parts of it into your own spec — no attribution required, though attribution is appreciated.

---

## Author

Chirag Patnaik · [@NakliTechie](https://github.com/NakliTechie) · [naklitechie.github.io](https://naklitechie.github.io/)

Part of the NakliTechie browser-native tools series.
