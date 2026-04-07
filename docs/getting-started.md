# Getting started with Bahi

Bahi is a browser-native, local-first accounting application for Indian SMBs. Your books live in a single `.khata` file on your own disk. **No server. No account. No subscription. No telemetry.**

This guide walks you from a blank slate to your first invoice in about 10 minutes.

---

## Before you start

- **Browser:** You need a Chromium-based browser (Chrome, Edge, Brave, Arc, Opera). Bahi uses the File System Access API, which doesn't exist in Safari or Firefox.
- **What you'll need handy:** your company name, GSTIN (if you have one), the state your business is registered in. That's it.

---

## Step 1 — Open Bahi and pick a mode

The first time you open Bahi, you'll see a welcome modal that asks: **Are you a business owner or a chartered accountant?**

- **Business owner** — you run a business and want to manage your own books. One company per `.khata` file.
- **Chartered accountant** — you review books for multiple client companies. Each client = one `.khata` file in your workspace.

For this guide we'll assume **Business owner**. (CA mode has its own dedicated guide at `docs/ca-guide.md`.)

Click "Got it — let me see the workspace".

---

## Step 2 — Create your first `.khata` file

On the Workspace screen, click **+ Create new .khata**. Bahi opens a save dialog — pick a folder where you want your books to live (Documents / Bahi Books / is a sensible default) and pick a name.

The new-company wizard then asks for:

- **Legal name** — the registered name of your business
- **Trade name** — what you actually call yourself (often the same)
- **Company type** — proprietorship / partnership / LLP / private limited / etc.
- **GSTIN** (optional) — your 15-digit GST number
- **State** — type the name, ISO code (MH), or the GST state code (27); Bahi auto-fills the others
- **Address**
- **FY start** — defaults to April 1 of the current FY
- **UI tier** — pick Service SMB or Goods SMB (you can change later in Settings)
- **Composition scheme** — toggle on if you're registered under section 10

Click **Create**. Bahi writes the file to disk, opens it, and lands you on the Dashboard.

---

## Step 3 — Add your first customer

Sidebar → **Customers** → **+ Add customer**.

Fill in:
- **Name**
- **GSTIN** (optional) — Bahi auto-fills the state from the GSTIN's first two digits
- **State** (auto-filled if you typed a GSTIN)
- **Email**, **Phone**, **Address** (all optional)
- **Opening balance** (₹) — only fill this if the customer owes you something on day one

Save. The customer appears in your list with an outstanding balance of ₹0.00.

---

## Step 4 — Add an item or service

Sidebar → **Items / services** → **+ Add item**.

For a service, set **Type** = Service, fill in the name, optional SAC code, unit (HR / NOS / etc.), default rate, and tax rate. Bahi auto-suggests the tax rate from the SAC code if it's in the bundled reference data.

For a goods item, set **Type** = Goods. Bahi reveals an inventory section: enable inventory tracking (yes/no), valuation method (Weighted Average Cost or FIFO), batch tracking (yes/no), reorder level, preferred vendor, opening stock quantity + value. For your first item, leave inventory tracking off — you can enable it later.

Save.

---

## Step 5 — Raise your first invoice

Sidebar → **+ New invoice**.

The form has three sections:
1. **Header** — pick the customer (default: the only one), invoice series (default: Domestic), invoice number (auto), date, place of supply (auto-filled from the customer's state), notes
2. **Lines** — pick an item from the dropdown or type a free-text description. Quantity, rate, tax rate (default from the item). The amount auto-computes.
3. **Totals** — Bahi shows the subtotal, CGST/SGST/IGST routing (intra-state vs inter-state, automatic), invoice total in both numbers and amount-in-words

Click **Post invoice & save**.

Bahi:
- Inserts the invoice header + lines into the database
- Posts the corresponding double-entry ledger entry (Dr Sundry Debtors / Cr Sales / Cr GST Output @ {rate}%)
- Captures snapshots of the company, customer, and HSN/SAC descriptions at this exact moment (so reprints stay correct even if you rename the customer later)
- Writes a signed audit log entry
- Saves the file to disk

You're now on the Invoices list with the new invoice at the top. Click **PDF** on the row to save a GST-compliant invoice PDF.

---

## Step 6 — Record a payment

Sidebar → **+ Record payment**.

- **Customer** — pick the same one
- **Date** — today
- **Amount** — partial or full
- **Bank / Cash** — pick from the dropdown (or click + to quick-add a bank account)
- **Mode** — bank transfer / cheque / UPI / etc.
- **Reference** — UTR / cheque number / etc.

Bahi shows the customer's open invoices and lets you allocate the payment across them with FIFO checkboxes (default: oldest first). Allocate, click **Post payment & save**.

---

## Step 7 — See the dashboard

Sidebar → **Dashboard**.

You should see:
- **Cashflow this month vs last** with the delta percentage
- **Total outstanding receivables** (zero if you fully allocated the payment)
- **GST liability** for the current month
- **Receivables aging** (how old your outstanding invoices are, bucketed)
- **Top customers** by outstanding amount
- **Recent activity** — the audit log in plain English

You're done. You've:
- Created a `.khata` file on your own disk
- Added a customer
- Added an item
- Raised a GST-compliant invoice with a posted ledger entry
- Recorded a payment with multi-invoice allocation
- Seen the dashboard roll up everything

---

## What's next

- **Sidebar** has 60+ routes grouped into 10 sections — explore at your own pace. Hit `?` any time for the keyboard cheat sheet.
- **Backup Now** in the topbar (or `Ctrl+Shift+B`) writes a dated archive zip — do this at the end of every working session and keep one offsite copy
- **Settings → Safety & failure modes** — read this once. It explains what's protected against (browser crash, multi-machine, file corruption, etc.) and what isn't
- **Tally users** — see `docs/tally-migration.md` for the import guide
- **CAs** — see `docs/ca-guide.md` for the multi-client review workflow

---

## Where your data lives

`mybooks.khata` (the file you saved) is a zip archive. You can `unzip` it from the command line and inspect:
- `manifest.json` — metadata, schema version, integrity hashes, audit log head
- `books.sqlite` — the double-entry ledger as a regular SQLite database
- `snapshots/` — rolling snapshots of previous saves
- `attachments/` — scanned bills (Phase 8)
- `exports/` — cached report exports

The format is published as `khata-format.md` in this repo. Anyone can write a `.khata` reader or writer — Bahi is just one implementation.
