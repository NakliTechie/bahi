# CA mode guide

Bahi's CA mode turns the app from "owner of one company" into "CA managing many clients". Indian SMBs almost universally have a CA who reviews their books at month-end and year-end. This guide walks you through the workflow end-to-end.

---

## Why CA mode exists

Without CA mode, the workflow is:
1. Owner sends `.khata` to CA via email / WhatsApp / Drive
2. CA opens it in their own Bahi instance pretending to be the owner
3. CA makes adjustments (year-end, depreciation, prepaid, outstanding, accruals)
4. CA sends back
5. Owner opens it, has no visible record of who changed what

With CA mode:
1. Owner sends `.khata` to CA the same way
2. CA opens it in CA mode — Bahi tags every action `actor='ca'` in the audit log automatically and stamps the CA's name + firm + ICAI membership
3. CA marks entries as reviewed, attaches annotations, posts adjustment vouchers
4. CA generates a formal PDF Review Report with the CA firm letterhead
5. CA sends back via Send back to client
6. Owner opens it — sees exactly what was added by the CA, sees the review report, sees the annotations, can react to to-dos

If owner edits the file in parallel (the "we both made changes" scenario), Bahi's Layer 3 ancestry check fires on the next open and routes to the **Reconciliation View** for a clean side-by-side merge.

---

## One-time setup

### Switch to CA mode

If this is your first time opening Bahi:
- The first-run modal asks "Are you a business owner or a chartered accountant?" — pick **Chartered accountant**

If you've been using Bahi as an owner:
- Click the **OWNER** badge in the topbar
- Confirm the switch
- Or: **Settings → Mode picker → Chartered accountant**

### CA profile

The first time you switch to CA mode, Bahi shows the CA profile setup modal. Fill in:
- **Your name**
- **Firm name**
- **ICAI membership number**
- **Logo** (optional, ≤200 KB) — appears on review reports

This is stored in your browser's IndexedDB, **never inside any client `.khata` file**. It's per-machine, so if you work from two laptops you set it up on each.

You can edit the profile later via Settings → Edit CA profile.

---

## Adding a client

Workspace → **+ Add client** → pick the client's `.khata` file. Bahi reads it, validates the format, and adds it to your Client list.

Each client card shows:
- Client name + GSTIN
- Last reviewed date
- **Unreviewed entries count** (entries with no `review_markers` row)
- Last opened

The card also runs the **Layer 3 ancestry check** when you open the file:
- **Identical** — same audit head as last open → silent, proceed
- **Fast-forward** — incoming file is downstream (owner posted new entries since you last had it) → silent, proceed
- **Same GSTIN, no shared ancestry** — file shares no history with your last copy → warning toast (probable causes: fresh export, restore from old backup, or different file with the same GSTIN)
- **Divergent** — both you and the owner have new entries the other doesn't → routes to the Reconciliation View
- **Different GSTIN** — falls through to the existing wrong-file hard block

---

## The review workflow

Open a client → Sidebar → **CA → Client review** (or `F8` if you customised your shortcuts).

The review view has:
1. **KPI strip** — count of unreviewed entries by voucher type (Sales / Purchase / Journal / Receipt / Payment / Credit Note / Debit Note)
2. **Sectioned list** — one panel per voucher type, with each entry as a row showing date, voucher ref, narration, amount
3. Per-row **✓ Reviewed** button — marks the entry reviewed by you (your name + ICAI membership get stamped via the `review_markers` table)
4. Per-row **+ Note** button — opens the annotation modal pre-filled with the entry's target_type and target_id
5. Per-section **Mark all reviewed** button — bulk version for when you've eyeballed everything in a section

### Annotations

Click **+ Note** on any row, or use the cross-cutting **Sidebar → CA → Annotations** view.

Annotation types:
- **Comment** — generic note
- **To-do** — something you'll come back to
- **Flag** — needs attention but no specific action
- **Reclassified** — you posted an adjustment to move an entry to a different account; this annotation explains why
- **Missing bill** — the supporting document is missing; ask the client
- **Confirm with client** — needs the client's input before finalising

Each annotation captures your CA identity (name + firm + ICAI membership) at creation time as a snapshot. If your firm renames itself later, last year's annotations still show last year's firm name. Same invariant as Bahi's invoice / customer / vendor snapshots.

---

## Posting adjustment vouchers

Sidebar → **CA → + Adjustment voucher** (or `F7` for journal voucher and pick CA actor manually).

The form is a thin wrapper around the existing journal voucher engine with one extra field: **Adjustment type**. Pick from:
- **Year-end** — closing entries that aren't full FY rollover
- **Depreciation** — fixed asset depreciation
- **Prepaid** — prepaid expenses → reclassify as expense
- **Outstanding** — outstanding expenses → reclassify as liability
- **Accrual** — revenue / expense accrual
- **Other** — anything else

Fill in the lines (Dr / Cr), narration, voucher ref. Click **Post adjustment**.

Behind the scenes, Bahi posts via the same `postEntry` engine as native journal vouchers, but with `actor='ca'` and a dedicated `ca.adjustment` audit log action. The owner will see this entry in their audit log clearly tagged as a CA adjustment with your name, firm, and the adjustment type.

---

## Generating the review report

Sidebar → **CA → Review report**.

The view shows a live preview of the report data:
- **Header** — your name, firm, ICAI membership on the left; client name + GSTIN + as-of date on the right
- **Trial Balance** with the tie check
- **P&L Summary** — total income, total expense, net profit/loss
- **Balance Sheet** — assets / liabilities / equity totals with the tie check
- **CA Adjustments** — every entry tagged `actor='ca'` and voucher type `journal` or `ca-adjustment`
- **Observations** — every annotation in the file with `status='open'`

Click **Generate PDF report**. Bahi writes a multi-page A4 PDF with your firm letterhead at the top of every page, page numbering, and one section per panel. Save the PDF wherever (your firm's client folder, an email attachment, etc.). This is the deliverable.

---

## Sending the file back

Two options:

**Option A — file system** (simplest):
- Save the file to disk (any save action does this; or hit `Ctrl+S` if you've made unsaved changes)
- Send the `.khata` file to the client via your normal channel (email, WhatsApp, Drive)
- Tell them to open it in Bahi

**Option B — backup zip with the review report bundled** (cleaner handoff):
- Hit **Backup Now** in the topbar (or `Ctrl+Shift+B`)
- Bahi writes a dated `.khata-backup.zip` containing the file + audit log CSV + meta.json
- Add the PDF review report to the same zip manually
- Send the zip

Either way, the owner's next file open will trigger the Layer 3 ancestry check on their side (your audit log head is downstream of theirs → fast-forward, proceed silently). They'll see the new audit log entries clearly attributed to you.

---

## Reconciliation: when the owner edited in parallel

If the owner posted new entries while you were reviewing (the "we both made changes" scenario), Bahi detects it on the **owner's** next file open. Their workspace's `lastKnownHead` (= the head from the last time they saved) doesn't match the head of the file you sent back, AND their audit chain has entries you don't have, AND your audit chain has entries they don't have.

Bahi opens the **Reconciliation View** automatically for them.

The view shows:
- **Header banner** with the common ancestor hash, both branch heads, and per-side counts of unique entries
- **Side-by-side checkbox lists** — local branch (the owner's version) on the left, imported branch (your version) on the right, default = keep all from both sides
- **Pre-merge summary** of how many entries will come from each branch

The owner can uncheck anything they don't want to keep. Then **Build merged file** — Bahi runs the replay engine: takes their local DB as the base, walks the picked imported entries in chronological order, and re-executes them via the existing posting bridges. The merged file's manifest carries `integrity.parentHashes = [localHead, importedHead]` so the file knows its lineage from both branches, and the audit log gets a `merge.commit` entry.

Result: nothing is silently lost; both branches' work is preserved; the owner is in control of the merge decisions.

---

## What CA mode is, and isn't

It IS:
- A way to attribute every action to either the owner or a specific CA via the audit log's `actor` field
- A way to attach notes to ledger entries that survive handoff
- A way to generate a formal PDF review report with your firm letterhead in one click
- A way to safely round-trip a `.khata` file between owner and CA without silent overwrites

It IS NOT:
- Real-time collaboration — Bahi is local-first; multi-CA workflows on the same file are not supported (the same problem as multi-machine concurrent editing)
- A way to lock the owner out — they can still post entries in parallel; the reconciliation view exists to handle that
- A way to delete or hide owner entries — the audit log is append-only, your adjustments are additive
- A multi-firm workspace — each browser stores one CA profile. If you work for two firms with different membership numbers, use a separate browser profile or browser for each (Chrome profile, Brave profile, etc.)

---

## Quick reference

| Action | Where |
|---|---|
| Switch to CA mode | Click OWNER badge in topbar / first-run modal / Settings |
| Edit CA profile | Settings → Edit CA profile |
| Add a client | Workspace → + Add client |
| Open client review | Sidebar → CA → Client review |
| Add an annotation | Inline + Note button on any review row |
| View all annotations | Sidebar → CA → Annotations |
| Post a CA adjustment | Sidebar → CA → + Adjustment voucher |
| Generate review report PDF | Sidebar → CA → Review report → Generate PDF |
| Backup the client file | Topbar → Backup Now / `Ctrl+Shift+B` |
| Reconcile a divergent file | Automatic — opens when Layer 3 detects divergence |
