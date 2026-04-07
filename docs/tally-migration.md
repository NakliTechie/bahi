# Migrating from Tally to Bahi

Bahi has a built-in Tally XML importer that handles both Tally Prime and Tally ERP 9. The typical migration takes 30 minutes for a year of bookkeeping. This guide walks you through it end-to-end.

---

## Before you start

- **You'll need:** a Tally export of your company's data in XML format (see Step 1 below)
- **What gets imported:** masters (groups, ledgers, stock items, units, godowns) + vouchers (Sales / Purchase / Receipt / Payment / Journal / Contra / Credit Note / Debit Note + variants)
- **What doesn't:** cost centres (ignored with a warning), multi-currency (taken at face value from the INR column), Tally `.tcp` backup files (proprietary binary format — not happening), Tally Cloud / TallyVault encrypted files (proprietary, not happening)

---

## Step 1 — Export from Tally

### Tally Prime
1. Open your company in Tally Prime
2. **Gateway of Tally → Export → All Masters**, format **XML** → save to a known folder
3. **Gateway of Tally → Export → Day Book**, format **XML**, set the date range (or full year), → save to the same folder

You'll end up with two XML files. You can either combine them into one (most CAs do) or import them sequentially. Bahi handles both cases.

### Tally ERP 9
1. Open your company in Tally ERP 9
2. **Gateway of Tally → Display → List of Accounts → Alt+E (Export)**, pick XML, save
3. **Gateway of Tally → Display → Day Book → Alt+E (Export)**, pick XML, set the period, save

Same two-file output. Same import flow.

---

## Step 2 — Open Bahi and start the import

If you don't already have a Bahi `.khata` file, you have two choices:

- **Create a fresh `.khata` file first** and then merge the Tally data into it (recommended if you want to keep some Bahi-only fields like UI tier or composition flag pre-set)
- **Let the importer create a new file from the Tally data** (faster, the Tally company info auto-populates the new-company wizard)

Either way: **Workspace → Import from Tally…** → pick your Tally XML file.

Bahi parses the file (this is fast — usually under 2 seconds for a typical SMB year) and routes you to a 6-step wizard.

---

## Step 3 — Step 1 of the wizard: File summary

The summary shows:
- Source company name + GSTIN (extracted from the Tally `<COMPANY>` element)
- Detected format (Tally Prime / ERP 9)
- Counts: **groups**, **ledgers**, **stock items**, **godowns**, **vouchers**
- **Date range** of vouchers found in the file
- **Voucher type breakdown** with a supported / unsupported flag for each type

Look at the unsupported types. Common ones that won't import:
- Stock Journal (manual stock adjustments) — you'll need to recreate these in Bahi via journal vouchers if material
- Memorandum, Reversing Journal, Sales Order, Purchase Order, Payroll vouchers — none are part of the standard double-entry books, so they're informational only

If the unsupported count is small (< 5% of total), you're fine. If it's large, look at the breakdown — you may want to address them in Tally before exporting.

Click **Continue → Date range**.

---

## Step 4 — Step 2: Date range filter

Defaults to the full file range. The picker has a **live count** of "vouchers in range" that updates as you change the dates.

Common scenarios:
- **First migration:** import everything. Set the range to the full file.
- **Year-by-year migration:** import only the current FY first; verify; then come back and import the previous FY into the same file.
- **Period-end migration:** import only entries since the last period close.

Click **Continue → Mapping**.

---

## Step 5 — Step 3: Mapping review

Tally and Bahi both use a chart-of-accounts hierarchy, but Tally has 28 reserved groups + however many you've created. Bahi auto-maps the 28 reserved groups to its standard CoA. Your custom groups go into a **"Needs mapping"** panel that hard-blocks the Continue button until every row is resolved.

For each unmapped group, pick the Bahi account it should fold into. Common choices:
- A custom expense group ("Marketing", "Office") → Indirect Expenses
- A custom income group → Sales
- A custom liability group → Current Liabilities
- A custom asset group → Current Assets

The auto-mapped groups are in a collapsible section above. Click any row to override its mapping if Bahi got it wrong.

Click **Continue → Commit target**.

---

## Step 6 — Step 4: Commit target

Two options:
- **Create new `.khata` file** — Bahi creates a fresh file with the Tally company info pre-populated. Safer. Recommended for first-time imports.
- **Merge into currently-open file** — Bahi adds the Tally data to the file you have open. Customers and vendors are deduped by GSTIN (or name if no GSTIN). Voucher number collisions get a `TALLY-` prefix so you can see which records came from import. Available only if a file is currently open.

For merge mode, Bahi shows a **live preview** of how many customers will be matched vs created and the same for vendors.

Click **Continue → Preview**.

---

## Step 7 — Step 5: Dry run preview

Final counts before committing. Categories:
- Customers, Vendors, Items, Godowns
- Vouchers in range (supported)
- Vouchers in range (unsupported — will be skipped)

Verify the date range and commit target. **Click Commit import.**

---

## Step 8 — Step 6: Result

Bahi runs the import in a single SQL transaction (any failure rolls back cleanly) and shows:
- Created / matched counts per category
- **Auto-cleaned to services** — stock items that looked service-shaped (zero opening stock, no HSN code, name contains "service" / "consulting" / "advice" / "fee") were imported as services with `is_service=1` and `enable_inventory=0` instead of as inventory items
- **Cost-centre warning** — count of vouchers that had cost-centre allocations (Bahi doesn't import these — see "What doesn't import" above)
- **Multi-currency warning** — count of vouchers with non-INR currency tags (Bahi takes the INR column value at face)
- **Skipped vouchers** with reasons (the most common reason is "unbalanced — Dr ≠ Cr", which usually means the source voucher was malformed in Tally)
- **Unsupported voucher types** with counts

Click **Download import report** to save a JSON file with the full result for your records (skipped vouchers list, mapping decisions, all warnings). Keep this with your original Tally export file as the audit trail of the migration.

---

## Step 9 — Verify the import

Don't skip this. Migration mistakes are easier to catch on day one than six months later.

1. **Trial Balance** (Sidebar → Reports → Trial Balance) — verify the total debits and total credits tie. Bahi will surface a warning if they don't, which usually means a few vouchers were skipped during import. Cross-check the count against the import report.
2. **Customer + vendor totals** — pick three customers and three vendors at random and verify their outstanding balances match what Tally showed.
3. **Stock on hand** (Sidebar → Inventory → Stock on hand) — for goods items, verify the opening + post-import quantities are right.
4. **Sales register** (Sidebar → Reports → Sales register) for the most recent month — count of invoices should match Tally.
5. **GSTR-3B summary** (Sidebar → Compliance → GSTR-3B) for the current period — total CGST/SGST/IGST should match the Tally summary.

---

## Step 10 — Once you're confident

- Hit **Backup Now** (`Ctrl+Shift+B`) to save a dated `.khata-backup.zip`. Keep this offsite.
- Decide your handoff date with Tally — usually the start of a new month or a new financial year
- From that date forward, post directly into Bahi. Don't dual-post into both Tally and Bahi (it's the same problem as a multi-machine concurrent edit — keeping two systems in sync manually is impossible)
- After 30 days of clean Bahi posting, retire the Tally license (or keep it as read-only for historical reference)

---

## Common gotchas

- **"Customer not found" skips on sales vouchers** — usually means the customer ledger was under a custom group you didn't map to Sundry Debtors in Step 5. Re-import after fixing the mapping.
- **Tax amounts don't match** — check if the original Tally vouchers had inclusive vs exclusive tax handling. Bahi assumes exclusive (line subtotal + GST = total). Inclusive-tax vouchers may need a manual journal voucher to correct.
- **Stock valuation differs by a few rupees** — rounding. Tally uses different rounding rules than Bahi. The difference should be material only if your stock has many low-value items.
- **Period overlap with native Bahi vouchers** — if you've already posted some entries in Bahi for the same period the Tally import covers, you'll see a yellow banner in Step 4 (merge mode only). Importing anyway will result in duplicate ledger entries — better to either narrow the import date range or roll back the Bahi entries first.

---

## If something goes wrong

The import is wrapped in a single SQL transaction. If anything fails mid-import, the database rolls back to its pre-import state and a `tally.import.failed` entry appears in the audit log with the error message.

If the import "succeeded" but the result looks wrong:
- Open Settings → Snapshots — Bahi captured a snapshot just before the import. Restore it to a fresh `.khata` file and start over with different mapping decisions.
- If you used the merge-into-existing flow, restore the snapshot to undo the merge.
- If you used the create-new flow, just delete the new file and re-create from the original Tally XML.

---

## What the Tally importer is, and isn't

It IS:
- A one-way migration tool (Tally → Bahi)
- An orchestrator over Bahi's existing posting engine — every imported voucher goes through the same `postInvoiceToLedger` / `postPurchaseToLedger` / `postEntry` functions native posting uses, so imported records are forensically and behaviorally indistinguishable from natively-posted ones

It IS NOT:
- A bidirectional sync tool — going Bahi → Tally is a separate (and much lower-value) feature
- A way to read Tally `.tcp` backup files — those are proprietary binary, not handled
- A way to read encrypted Tally Cloud / TallyVault files — same
- An IRN / e-invoicing data preserver — Tally Prime exports include IRN data, but Bahi has no IRN field yet (Phase 8 polish item)
