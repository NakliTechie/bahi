#!/usr/bin/env python3
"""Generate demo/index.html from captured screenshots."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "index.html"
BAHI_BASE = "../"  # demo sits one level under the app root; works on any host

# Captions keyed on slug (after the NN- prefix)
CAPTIONS = {
    # -- file + workspace --
    "dashboard":          ("Dashboard", "KPIs for the current month: cashflow vs last month, total outstanding receivables, GST liability, receivables aging and top customers. This is the first thing the accountant sees every morning."),
    "file-info":          ("Current file", "Company identity pulled from the .khata manifest — GSTIN, legal name, state, last-modified. Also shows the backup reminder and the one-click 'Backup Now' button."),
    "workspace":          ("Workspace", "The pre-file-open home screen. Lists recently-opened .khata files and exposes 'New company', 'Open file' and 'Start from tally import'. No file is required to reach this view."),
    "settings":           ("Settings", "Theme switcher (Crisp Paper / Sumi Ink / Bengara / High Contrast), default invoice series, CA profile, autosave cadence, and the 'Reset intro' toggle. Everything persists in localStorage, nothing leaves the browser."),
    "debug":              ("Debug console", "Raw SQL runner that reads the live sql.js database. Useful when the CA wants to verify a specific figure against the ledger or audit chain."),

    # -- masters --
    "customers":          ("Customer master", "Complete customer ledger with GSTIN, state, payment terms, current outstanding and aging. Clicking a row drills through to their invoice history."),
    "vendors":            ("Vendor master", "Vendors with PAN, GSTIN, default TDS section and current dues. Used for purchase and vendor-payment workflows."),
    "items":              ("Items & services", "Unified master for HSN goods and SAC services. Pharma has both: tablet strips, surgical consumables, lab services. Manufacturing has steel products only. Consulting has only SACs."),
    "series":             ("Invoice series", "FY-scoped numbering series (INV/25-26, CN/25-26, PUR/25-26 …). Each .khata file carries its own series and resets them automatically at year-end rollover."),

    # -- daily flows --
    "invoices":           ("Sales invoices", "Every invoice with status badge (paid / partial / unpaid / cancelled), customer, date, amount and tax split. Filterable by series, customer, date range, and status."),
    "invoice-new":        ("New invoice form", "HSN/SAC items, auto-routed CGST+SGST (intra-state) or IGST (inter-state), place-of-supply captured per invoice, round-off, notes, and live preview of the outgoing ledger entry."),
    "credit-notes":       ("Credit notes", "Sales returns with a back-link to the original invoice. Pharma has 4-5 credit notes in the sample against expired stock returns."),
    "credit-note-new":    ("New credit note", "Pick parent invoice, adjust lines, auto-reverses the proportional tax, and produces a balanced journal entry."),
    "purchases":          ("Purchase bills", "Vendor bills with input GST captured separately. Consulting has zero purchases — proof that the sample data is shape-correct."),
    "purchase-new":       ("New purchase bill", "TDS section selector (194J / 194C / 194I / 194H), tax-aware totals, and a preview of the resulting vendor ledger and TDS payable postings."),
    "debit-notes":        ("Debit notes", "Purchase returns, symmetric to credit notes. Rare in the sample but the route renders correctly with the empty-state panel for companies that have none."),
    "debit-note-new":     ("New debit note", "Adjust the parent purchase bill, reverse the proportional input GST, and post the balanced ledger entry."),
    "payments":           ("Receipts & payments list", "All customer receipts and vendor payments in one register. Clicking a row shows the allocation breakdown and the underlying ledger entry."),
    "payment-new":        ("Record a customer receipt", "Pick the customer, amount, mode (bank/cash/UPI), and allocate across one or many open invoices. Enforces allocated <= received."),
    "vendor-payment-new": ("Pay a vendor (with TDS)", "Pay a vendor bill, deduct TDS under the applicable section, and post to TDS Payable in one step. The section header and certificate metadata travel with the deduction."),
    "tcs-collection-new": ("Record TCS collection", "For sellers liable under 206C(1H). Bahi computes and posts the TCS payable liability alongside the customer receipt."),
    "advances":           ("Advances", "Customer advances received before an invoice exists. Tracked separately and auto-adjusted against the first matching invoice."),
    "advance-new":        ("New advance receipt", "Capture the advance, its GST treatment (taxable on receipt or on adjustment), and the PAN/GSTIN for statutory reporting."),

    # -- inventory --
    "inventory-dashboard": ("Inventory dashboard", "Stock value on hand, count of items below reorder level, count of batches expiring soon, and a top-10 by value strip. Only goods companies see this populated."),
    "stock-on-hand":       ("Stock on hand", "Per-item current balance across godowns with WAC (weighted average cost) valuation. Used for monthly closing and the balance-sheet stock figure."),
    "stock-movements":     ("Stock movement log", "Every in/out movement — sale, purchase, transfer, adjustment, return — with source document reference. This is the source of truth the register is built from."),
    "stock-register":      ("Stock register (per item)", "Walk-through of a single item's movements with running balance and running WAC. Auditor workflow: pick an item, verify opening + movements = closing."),
    "batches":             ("Batch list", "Batch-tracked items with manufacture and expiry dates. Critical for pharma — expired batches block sale at the item-picker."),
    "valuation-summary":   ("Valuation summary", "Stock value by godown and by item class. Ties directly to the inventory line on the balance sheet."),
    "reorder-alerts":      ("Reorder alerts", "Items below reorder level. The accountant runs this weekly to trigger purchase indents."),
    "stock-aging":         ("Stock aging (batch)", "Batch-tracked stock bucketed by age (0-30 / 31-60 / 61-90 / 90+ days). Pharma's sample data doesn't cross the 0-30 day threshold so the route renders its empty-state panel — a valid result."),
    "godowns":             ("Godown master", "Named storage locations — factory, warehouse-1, consignment — with per-location stock roll-ups."),
    "delivery-challans":   ("Delivery challans", "DCs for goods dispatched without an immediate invoice (job-work, consignment, returnable)."),
    "delivery-challan-new":("New delivery challan", "Item picker, transport details, and the 'convert to invoice' button that reuses the DC lines on a new tax invoice."),
    "eway-bills":          ("E-way bills", "E-way bill register for invoices crossing the INR 50k / inter-state threshold. Each row links back to its parent invoice."),
    "eway-bill-new":       ("New e-way bill", "Transporter details, distance, vehicle number and validity. Bahi pre-fills from the selected invoice so there's no retyping."),
    "stock-transfers":     ("Stock transfers", "Inter-godown transfer register — one side of the 'out' matches the other side's 'in'."),
    "stock-transfer-out":  ("New stock transfer (outward)", "Pick source godown, destination godown, items, quantities. Produces the 'out' movement and a printable transfer slip for the receiving side."),
    "stock-transfer-in":   ("Stock transfer (inbound import)", "Import the paired 'in' side of a transfer from a sister godown .khata file. Keeps both sides reconciled without network sync."),

    # -- accounting --
    "journal-new":         ("Journal voucher", "Free-form double-entry voucher for anything the dedicated forms don't cover — depreciation, provisions, expense accruals, CA adjustments."),
    "bank-reconcile":      ("Bank reconciliation", "Pick a bank account, paste the bank statement rows, and match them against ledger entries. Unmatched items stay highlighted until resolved."),
    "day-book":            ("Day book", "Chronological voucher tape — every entry in date order with narration, ref and running totals. The auditor's first scan of the period."),
    "account-ledger":      ("Account ledger", "Ledger view for any account — sundry debtors, vendor subledger, bank, TDS payable — with opening, movements and closing balance."),
    "trial-balance":       ("Trial balance", "Opening + debits + credits + closing for every account grouped by type (asset / liability / income / expense / equity). Grand totals must tie — enforced by a data-integrity test."),
    "balance-sheet":       ("Balance sheet", "Schedule-III compliant balance sheet assembled from the trial balance in-browser. No cloud, no spreadsheet."),
    "pnl":                 ("Profit & loss", "P&L summary with income categories, direct expenses, and indirect expenses. Drilldown to account ledger from each line."),
    "sales-register":      ("Sales register", "GST-compliant sales register: invoice no, customer, GSTIN, taxable value, CGST, SGST, IGST. Used for filing GSTR-1 and also as a standalone printout for CAs."),
    "purchase-register":   ("Purchase register", "Symmetric register on the input side. Drives the ITC figures in GSTR-3B Table 4."),

    # -- tax & compliance --
    "gstr1":               ("GSTR-1", "Outward supplies summary auto-assembled from the invoice table. B2B, B2CL, B2CS, exports, CDNR, HSN summary — all tabs."),
    "gstr3b":              ("GSTR-3B", "Monthly return summary: 3.1 outward, 3.2 inter-state supplies, 4 ITC, 5 exempt, 6.1 payment. Numbers reconcile to the sales and purchase registers."),
    "cmp08":               ("CMP-08", "Composition scheme quarterly statement. Renders empty for the sample files since none are composition dealers — but the route is healthy."),
    "form-26q":            ("Form 26Q", "Quarterly TDS return for non-salary deductions. Lists every deduction with section, deductee PAN, amount, rate, date of deduction and date of deposit."),
    "form-27eq":           ("Form 27EQ", "Quarterly TCS return — counterpart to 26Q on the collection side. Renders the quarter selector and the (empty) deductee table for sample data."),
    "form-27d":            ("Form 27D certificates", "TCS certificate generator — one printable certificate per collectee per quarter."),
    "tax-challans":        ("Tax challan templates", "ITNS 280 / 281 challan printable templates pre-filled from the period's liability. No bank integration — just print and take to the bank portal."),

    # -- governance --
    "period-locks":        ("Period locks", "Lock a completed fiscal period so no backdated entries can be made. Attempted writes are blocked with a visible banner."),
    "fy-rollover":         ("FY rollover wizard", "Close the current fiscal year and carry forward balances as opening entries in the new year. Creates a snapshot before committing."),
    "annotations":         ("Annotations", "Sticky notes the CA leaves on specific entries, customers or accounts. Visible in-line and in the annotations register."),

    # -- CA flow --
    "client1-dashboard":       ("Client 1 — Dashboard", "CA opens pharma.khata. Mode badge flips to 'CA · CS'. Dashboard greets them with the client's outstanding receivables and aging."),
    "client1-trial-balance":   ("Client 1 — Trial balance", "First scan of completeness — grand totals tied, every entry balanced, suspense account empty."),
    "client1-balance-sheet":   ("Client 1 — Balance sheet", "Schedule-III grouping. Reconciles directly to the trial balance so there's no 'spreadsheet step' to audit."),
    "client1-pnl":             ("Client 1 — Profit & loss", "P&L summary. Drilldown is one click — from any line to the underlying ledger."),
    "client1-day-book":        ("Client 1 — Day book review", "Chronological voucher tape. The auditor clicks through suspicious entries and drops annotations as they go."),
    "client1-ca-review":       ("Client 1 — CA review panel", "Every voucher gets a 'Reviewed' checkbox and an inline 'Note' button. The header counts tell the CA how much is left to sign off."),
    "client1-annotations":     ("Client 1 — Annotations", "Running list of all notes the CA left on this file. Export to the review report with one click."),
    "client1-ca-report":       ("Client 1 — Review report", "Final PDF-ready report combining client identity, review checkpoints, annotations and sign-off."),
    "client2-dashboard":       ("Client 2 — Dashboard", "CA closes pharma.khata, opens manufacturing.khata. The mode badge persists, the dashboard refreshes to the new client."),
    "client2-trial-balance":   ("Client 2 — Trial balance", "Manufacturing's trial balance. Same layout, different numbers — no context switching cost."),
    "client2-balance-sheet":   ("Client 2 — Balance sheet", "Heavy on fixed assets and inventory, as you'd expect for a steel products company."),
    "client2-pnl":             ("Client 2 — Profit & loss", "High cost of goods sold relative to sales — consistent with the manufacturing margin profile."),
    "client2-ca-review":       ("Client 2 — CA review panel", "Same review workflow applied to the second client. Nothing to install or configure between files."),
    "client3-dashboard":       ("Client 3 — Dashboard", "Consulting LLP — smaller scale, services only, no inventory panel."),
    "client3-trial-balance":   ("Client 3 — Trial balance", "Fewer accounts, simpler structure — typical for a services LLP."),
    "client3-balance-sheet":   ("Client 3 — Balance sheet", "Receivables-heavy, no inventory line. The balance sheet layout adapts to the data present."),
    "client3-pnl":             ("Client 3 — Profit & loss", "Services revenue and professional expenses. TDS under 194J is auto-accumulated from the vendor payments."),
    "client3-ca-adjustment":   ("Client 3 — CA adjustment voucher", "CA-authored adjustment entry — depreciation provision, year-end expense accrual, or any reclassification. Signed with the CA's identity from the profile."),
}

# Sample file metadata for the three cards
SAMPLE_CARDS = [
    {
        "file": "pharma.khata",
        "title": "Pharma — Goods + Services",
        "company": "Vaidya Life Sciences Pvt Ltd",
        "gstin": "27AABCV1234A1Z5",
        "state": "Maharashtra",
        "desc": "Pharmaceutical wholesaler across 2 FYs. Goods (HSN 30xx/38xx) + lab services (SAC 99xxxx). 120+ invoices, credit notes, advances, TDS deductions, bank reconciliation.",
        "hero": "screenshots/pharma/01-dashboard.png",
    },
    {
        "file": "manufacturing.khata",
        "title": "Manufacturing — Goods only",
        "company": "Shree Krishna Steel Industries Ltd",
        "gstin": "24AAACS5678B1Z3",
        "state": "Gujarat",
        "desc": "Steel products manufacturer. Heavy inventory (500+ stock movements across 2 FYs), WAC valuation, multiple godowns, high-value B2B invoices with e-way bills.",
        "hero": "screenshots/manufacturing/01-dashboard.png",
    },
    {
        "file": "consulting.khata",
        "title": "Consulting — Services only",
        "company": "Arjun Rao Advisory LLP",
        "gstin": "29AAEFA9012C1Z7",
        "state": "Karnataka",
        "desc": "Professional services LLP. SAC 9982xx only, no inventory, no purchases. Smaller scale — closer to what a single-partner or boutique firm looks like.",
        "hero": "screenshots/consulting/01-dashboard.png",
    },
]

# Accountant walkthrough — ordered list of (section_title, section_intro, [(file, slug), ...])
ACCOUNTANT_SECTIONS = [
    ("Daily",
     "The work the accountant does every morning. Raise invoices, record receipts, enter purchase bills, pay vendors.",
     [
         ("pharma", "07-invoices"),
         ("pharma", "08-invoice-new"),
         ("pharma", "16-payment-new"),
         ("pharma", "11-purchases"),
         ("pharma", "12-purchase-new"),
         ("pharma", "17-vendor-payment-new"),
         ("pharma", "18-tcs-collection-new"),
     ]),
    ("Weekly",
     "Housekeeping tasks. Review masters, reconcile bank, add new items and series.",
     [
         ("pharma", "03-customers"),
         ("pharma", "04-vendors"),
         ("pharma", "05-items"),
         ("pharma", "06-series"),
         ("pharma", "38-bank-reconcile"),
         ("pharma", "09-credit-notes"),
         ("pharma", "10-credit-note-new"),
         ("pharma", "13-debit-notes"),
         ("pharma", "14-debit-note-new"),
         ("pharma", "19-advances"),
         ("pharma", "20-advance-new"),
     ]),
    ("Monthly",
     "Period close and statutory filings. Dashboard review, aging, GST returns and TDS returns.",
     [
         ("pharma", "01-dashboard"),
         ("pharma", "46-gstr1"),
         ("pharma", "47-gstr3b"),
         ("pharma", "49-form-26q"),
         ("pharma", "50-form-27eq"),
         ("pharma", "51-form-27d"),
         ("pharma", "52-tax-challans"),
         ("pharma", "48-cmp08"),
     ]),
    ("Inventory (goods companies)",
     "Every inventory route in sequence. Pharma has the full story — dashboard, stock on hand, register, valuation, batches, aging, godowns, DCs, e-way bills and transfers.",
     [
         ("pharma", "21-inventory-dashboard"),
         ("pharma", "22-stock-on-hand"),
         ("pharma", "23-stock-movements"),
         ("pharma", "24-stock-register"),
         ("pharma", "25-batches"),
         ("pharma", "26-valuation-summary"),
         ("pharma", "27-reorder-alerts"),
         ("pharma", "28-stock-aging"),
         ("pharma", "29-godowns"),
         ("pharma", "30-delivery-challans"),
         ("pharma", "31-delivery-challan-new"),
         ("pharma", "32-eway-bills"),
         ("pharma", "33-eway-bill-new"),
         ("pharma", "34-stock-transfers"),
         ("pharma", "35-stock-transfer-out"),
         ("pharma", "36-stock-transfer-in"),
     ]),
    ("Accounting & journal",
     "Free-form accounting entries — journal voucher, day book, ledger lookups, registers.",
     [
         ("pharma", "37-journal-new"),
         ("pharma", "39-day-book"),
         ("pharma", "40-account-ledger"),
         ("pharma", "44-sales-register"),
         ("pharma", "45-purchase-register"),
     ]),
    ("Yearly & governance",
     "Trial balance, financials, period locks and year-end rollover.",
     [
         ("pharma", "41-trial-balance"),
         ("pharma", "42-balance-sheet"),
         ("pharma", "43-pnl"),
         ("pharma", "53-period-locks"),
         ("pharma", "54-fy-rollover"),
         ("pharma", "55-annotations"),
     ]),
]

MANUFACTURING_HIGHLIGHTS = [
    ("manufacturing", "01-dashboard"),
    ("manufacturing", "03-invoices"),
    ("manufacturing", "04-customers"),
    ("manufacturing", "07-purchases"),
    ("manufacturing", "08-inventory"),
    ("manufacturing", "09-stock-on-hand"),
    ("manufacturing", "10-stock-movements"),
    ("manufacturing", "11-valuation-summary"),
    ("manufacturing", "12-stock-aging"),
    ("manufacturing", "13-stock-register"),
    ("manufacturing", "14-delivery-challans"),
    ("manufacturing", "15-eway-bills"),
    ("manufacturing", "16-stock-transfers"),
    ("manufacturing", "17-godowns"),
    ("manufacturing", "18-trial-balance"),
    ("manufacturing", "19-balance-sheet"),
    ("manufacturing", "20-pnl"),
    ("manufacturing", "21-gstr1"),
    ("manufacturing", "22-gstr3b"),
]

CONSULTING_HIGHLIGHTS = [
    ("consulting", "01-dashboard"),
    ("consulting", "03-invoices"),
    ("consulting", "04-customers"),
    ("consulting", "05-items"),
    ("consulting", "06-credit-notes"),
    ("consulting", "07-payments"),
    ("consulting", "08-advances"),
    ("consulting", "09-journal-new"),
    ("consulting", "10-day-book"),
    ("consulting", "11-trial-balance"),
    ("consulting", "12-balance-sheet"),
    ("consulting", "13-pnl"),
    ("consulting", "14-sales-register"),
    ("consulting", "15-gstr1"),
    ("consulting", "16-gstr3b"),
    ("consulting", "17-form-26q"),
]

CA_SECTIONS = [
    ("Client 1 — Pharma (Vaidya Life Sciences)",
     "CA opens pharma.khata. Mode badge turns into the CA tile. Review workflow begins.",
     [
         ("ca-audit", "01-client1-dashboard"),
         ("ca-audit", "02-client1-trial-balance"),
         ("ca-audit", "03-client1-balance-sheet"),
         ("ca-audit", "04-client1-pnl"),
         ("ca-audit", "05-client1-day-book"),
         ("ca-audit", "06-client1-ca-review"),
         ("ca-audit", "07-client1-annotations"),
         ("ca-audit", "08-client1-ca-report"),
     ]),
    ("Client 2 — Manufacturing (Shree Krishna Steel)",
     "Close client 1, open client 2. Same keystrokes, different client.",
     [
         ("ca-audit", "09-client2-dashboard"),
         ("ca-audit", "10-client2-trial-balance"),
         ("ca-audit", "11-client2-balance-sheet"),
         ("ca-audit", "12-client2-pnl"),
         ("ca-audit", "13-client2-ca-review"),
     ]),
    ("Client 3 — Consulting (Arjun Rao Advisory)",
     "Close client 2, open client 3. Services-only balance sheet, and a CA adjustment voucher example.",
     [
         ("ca-audit", "14-client3-dashboard"),
         ("ca-audit", "15-client3-trial-balance"),
         ("ca-audit", "16-client3-balance-sheet"),
         ("ca-audit", "17-client3-pnl"),
         ("ca-audit", "18-client3-ca-adjustment"),
     ]),
]


def slug_of(filename_stem):
    # "07-invoices" → "invoices"
    parts = filename_stem.split("-", 1)
    return parts[1] if len(parts) == 2 else filename_stem


def caption_for(slug_key):
    return CAPTIONS.get(slug_key, (slug_key.replace("-", " ").title(), ""))


def shot_path(company, file_stem):
    return f"screenshots/{company}/{file_stem}.png"


def bahi_href(file_stem):
    # derive hash route
    slug = slug_of(file_stem)
    # best-effort mapping — slug key matches the hash fragment roughly
    h = slug.replace("-new", "/new")
    # route-level exceptions
    MAP = {
        "file-info": "file",
        "inventory-dashboard": "inventory",
        "credit-note-new": "credit-note/new",
        "debit-note-new": "debit-note/new",
        "payment-new": "payment/new",
        "vendor-payment-new": "vendor-payment/new",
        "tcs-collection-new": "tcs-collection/new",
        "advance-new": "advance/new",
        "invoice-new": "invoice/new",
        "purchase-new": "purchase/new",
        "journal-new": "journal/new",
        "delivery-challan-new": "delivery-challan/new",
        "eway-bill-new": "eway-bill/new",
        "stock-transfer-out": "stock-transfer/out/new",
        "stock-transfer-in": "stock-transfer/in/import",
        "client1-dashboard": "dashboard",
        "client1-trial-balance": "trial-balance",
        "client1-balance-sheet": "balance-sheet",
        "client1-pnl": "pnl",
        "client1-day-book": "day-book",
        "client1-ca-review": "ca/review",
        "client1-annotations": "annotations",
        "client1-ca-report": "ca/report",
        "client2-dashboard": "dashboard",
        "client2-trial-balance": "trial-balance",
        "client2-balance-sheet": "balance-sheet",
        "client2-pnl": "pnl",
        "client2-ca-review": "ca/review",
        "client3-dashboard": "dashboard",
        "client3-trial-balance": "trial-balance",
        "client3-balance-sheet": "balance-sheet",
        "client3-pnl": "pnl",
        "client3-ca-adjustment": "ca/adjustment/new",
    }
    return BAHI_BASE + "#/" + MAP.get(slug, slug)


def file_badge(company):
    return {
        "pharma":        ("Pharma sample",         "pharma"),
        "manufacturing": ("Manufacturing sample",  "mfg"),
        "consulting":    ("Consulting sample",     "con"),
        "ca-audit":      ("CA audit walkthrough",  "ca"),
    }.get(company, ("", ""))


def render_shot(company, file_stem):
    slug = slug_of(file_stem)
    title, caption = caption_for(slug)
    badge_text, badge_class = file_badge(company)
    path = shot_path(company, file_stem)
    href = bahi_href(file_stem)
    return f'''<figure class="shot">
  <a class="shot-link" href="{href}"><img src="{path}" alt="{title}" loading="lazy"></a>
  <figcaption>
    <h4>{title}</h4>
    <p>{caption}</p>
    <div class="shot-meta"><span class="badge {badge_class}">{badge_text}</span><code>{href.replace(BAHI_BASE, "#/").replace("##/", "#/")}</code></div>
  </figcaption>
</figure>
'''


def render_section(title, intro, items):
    shots = "\n".join(render_shot(c, s) for c, s in items)
    return f'''<section class="flow">
  <h3>{title}</h3>
  <p class="section-intro">{intro}</p>
  <div class="grid">
    {shots}
  </div>
</section>
'''


def render_highlight_grid(items):
    return '<div class="grid">\n' + "\n".join(render_shot(c, s) for c, s in items) + '\n</div>'


def main():
    shots_dir = ROOT / "screenshots"
    counts = {
        "pharma":        len(list((shots_dir / "pharma").glob("*.png"))),
        "manufacturing": len(list((shots_dir / "manufacturing").glob("*.png"))),
        "consulting":    len(list((shots_dir / "consulting").glob("*.png"))),
        "ca-audit":      len(list((shots_dir / "ca-audit").glob("*.png"))),
    }

    accountant_html = "\n".join(
        render_section(t, i, items) for t, i, items in ACCOUNTANT_SECTIONS
    )
    ca_html = "\n".join(
        render_section(t, i, items) for t, i, items in CA_SECTIONS
    )

    sample_cards_html = "\n".join(f'''
    <article class="sample-card">
      <img src="{c['hero']}" alt="{c['title']}" loading="lazy">
      <div class="sample-body">
        <h3>{c['title']}</h3>
        <p class="muted">{c['company']}</p>
        <ul class="meta">
          <li><b>GSTIN</b> <code>{c['gstin']}</code></li>
          <li><b>State</b> {c['state']}</li>
          <li><b>File</b> <code>{c['file']}</code></li>
        </ul>
        <p>{c['desc']}</p>
      </div>
    </article>''' for c in SAMPLE_CARDS)

    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bahi — demo walkthrough</title>
<style>
  :root {{
    --saffron: #8b3a1f;
    --ink:     #1c1815;
    --navy:    #1a2b4a;
    --ash:     #f1f1ee;
    --paper:   #faf8f3;
    --line:    #d8d6cf;
    --muted:   #6b655c;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    color: var(--ink);
    background: var(--paper);
    line-height: 1.5;
    font-size: 16px;
  }}
  a {{ color: var(--saffron); }}
  code {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.88em; background: var(--ash); padding: 1px 5px; border-radius: 3px; }}

  header.hero {{
    background: var(--ink);
    color: var(--paper);
    padding: 64px 32px 56px;
    border-bottom: 4px solid var(--saffron);
  }}
  header.hero .inner {{ max-width: 1100px; margin: 0 auto; }}
  header.hero h1 {{ margin: 0 0 12px; font-size: 3rem; letter-spacing: -0.02em; font-weight: 800; }}
  header.hero h1 .alpha {{
    display: inline-block; vertical-align: middle; font-size: 0.9rem; padding: 4px 10px;
    background: var(--saffron); color: #fff; border-radius: 3px; margin-left: 12px; letter-spacing: 0.08em;
  }}
  header.hero p.lede {{ font-size: 1.2rem; max-width: 720px; opacity: 0.9; margin: 0 0 28px; }}
  header.hero .audiences {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  header.hero .audiences .who {{
    flex: 1 1 320px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.15);
    padding: 18px 20px; border-radius: 6px;
  }}
  header.hero .audiences h3 {{ margin: 0 0 8px; color: var(--saffron); font-size: 0.82rem; letter-spacing: 0.1em; text-transform: uppercase; }}
  header.hero .audiences p {{ margin: 0; opacity: 0.95; font-size: 0.95rem; }}
  header.hero code, footer code {{ background: rgba(255,255,255,0.12); color: #ffe6dc; }}
  header.hero p.lede code {{ background: rgba(255,255,255,0.12); color: #ffe6dc; }}

  .hero-shot {{ max-width: 1100px; margin: -24px auto 48px; padding: 0 32px; }}
  .hero-shot img {{ width: 100%; border-radius: 6px; box-shadow: 0 12px 40px rgba(28,24,21,0.2); border: 1px solid var(--line); display: block; }}

  main {{ max-width: 1100px; margin: 0 auto; padding: 0 32px 80px; }}

  h2 {{ font-size: 2rem; margin: 64px 0 8px; color: var(--navy); letter-spacing: -0.01em; }}
  h2::before {{ content: ""; display: inline-block; width: 6px; height: 28px; background: var(--saffron); margin-right: 12px; vertical-align: -5px; border-radius: 2px; }}
  h3 {{ font-size: 1.3rem; margin: 36px 0 4px; color: var(--ink); }}
  .section-intro {{ color: var(--muted); max-width: 780px; margin: 6px 0 20px; font-size: 0.98rem; }}
  .intro {{ color: var(--muted); max-width: 780px; margin: 8px 0 24px; font-size: 1rem; }}

  .why-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; margin: 24px 0 0; }}
  .why-grid .why {{ background: #fff; border: 1px solid var(--line); padding: 18px 20px; border-radius: 6px; }}
  .why-grid .why h4 {{ margin: 0 0 6px; color: var(--saffron); font-size: 0.95rem; letter-spacing: 0.02em; text-transform: uppercase; }}
  .why-grid .why p {{ margin: 0; font-size: 0.94rem; color: var(--ink); }}

  .samples {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin: 24px 0 0; }}
  .sample-card {{ background: #fff; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; display: flex; flex-direction: column; }}
  .sample-card img {{ width: 100%; display: block; border-bottom: 1px solid var(--line); }}
  .sample-body {{ padding: 18px 20px; }}
  .sample-body h3 {{ margin: 0 0 4px; font-size: 1.1rem; color: var(--navy); }}
  .sample-body .muted {{ color: var(--muted); margin: 0 0 10px; font-size: 0.9rem; }}
  .sample-body ul.meta {{ list-style: none; padding: 0; margin: 0 0 12px; font-size: 0.88rem; }}
  .sample-body ul.meta li {{ padding: 2px 0; color: var(--muted); }}
  .sample-body ul.meta li b {{ color: var(--ink); display: inline-block; width: 58px; }}
  .sample-body p {{ margin: 0; font-size: 0.92rem; color: var(--ink); }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
    gap: 24px;
    margin-top: 12px;
  }}
  figure.shot {{
    margin: 0;
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 6px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  figure.shot .shot-link {{ display: block; line-height: 0; }}
  figure.shot img {{ width: 100%; max-width: 1000px; display: block; border-bottom: 1px solid var(--line); }}
  figcaption {{ padding: 14px 18px 16px; }}
  figcaption h4 {{ margin: 0 0 6px; font-size: 1rem; color: var(--navy); }}
  figcaption p {{ margin: 0 0 10px; font-size: 0.9rem; color: var(--ink); }}
  .shot-meta {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 0.78rem; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 3px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.72rem;
  }}
  .badge.pharma {{ background: #fbe9e2; color: var(--saffron); }}
  .badge.mfg    {{ background: #e3ebf7; color: var(--navy); }}
  .badge.con    {{ background: #e6efe3; color: #2d5a2b; }}
  .badge.ca     {{ background: #1c1815; color: #fff; }}
  .shot-meta code {{ color: var(--muted); }}

  .flow {{ margin-top: 32px; }}

  footer {{
    margin-top: 80px;
    padding: 40px 32px 56px;
    background: var(--ink);
    color: var(--paper);
    text-align: center;
  }}
  footer a {{ color: var(--saffron); }}
  footer .alpha-note {{ opacity: 0.75; font-size: 0.85rem; margin: 16px auto 0; max-width: 620px; }}

  @media (max-width: 720px) {{
    header.hero h1 {{ font-size: 2rem; }}
    header.hero {{ padding: 40px 20px 40px; }}
    main {{ padding: 0 18px 60px; }}
    h2 {{ font-size: 1.5rem; }}
    .grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<header class="hero">
  <div class="inner">
    <h1>Bahi<span class="alpha">ALPHA</span></h1>
    <p class="lede">A local-first, browser-native accounting app for Indian SMBs. No cloud, no subscription, no data leaving the device. One <code>.khata</code> file per company.</p>
    <div class="audiences">
      <div class="who">
        <h3>For the accountant</h3>
        <p>Daily invoicing, vendor bills with TDS, bank reconciliation, GSTR-1 / 3B / 26Q. Everything a day-to-day bookkeeper needs in one HTML file.</p>
      </div>
      <div class="who">
        <h3>For the chartered accountant</h3>
        <p>Open one <code>.khata</code> per client. Trial balance, balance sheet, day book review, annotations, and a printable review report — per client, in seconds.</p>
      </div>
    </div>
  </div>
</header>

<div class="hero-shot">
  <img src="screenshots/pharma/01-dashboard.png" alt="Bahi dashboard (pharma sample)" loading="lazy">
</div>

<main>

<h2>Why local-first</h2>
<p class="intro">Every Indian accounting tool on the market sends your books to someone else's database. Bahi doesn't. The whole application is one HTML file. Your data is one <code>.khata</code> file. You own both.</p>
<div class="why-grid">
  <div class="why"><h4>One file</h4><p>Every company is a single <code>.khata</code> zip — <code>manifest.json</code> + <code>books.sqlite</code>. Copy, backup, version-control. Nothing else.</p></div>
  <div class="why"><h4>Zero servers</h4><p>Bahi is a static HTML page. There's no backend to exfiltrate from, nothing to subscribe to, nothing to renew.</p></div>
  <div class="why"><h4>Audit-proof</h4><p>Every entry appends to a signed, hash-linked audit log inside the file itself. Any tampering breaks the chain.</p></div>
  <div class="why"><h4>CA-ready</h4><p>Built-in CA mode, review markers, annotations, and a printable review report. Works across multiple client files without a login.</p></div>
</div>

<h2>The three sample files</h2>
<p class="intro">Three intentionally different shapes — goods+services, goods-only, services-only — to prove the app handles every branch of the chart of accounts. All three pass the 45-assertion data integrity test suite.</p>
<div class="samples">
{sample_cards_html}
</div>

<h2>Accountant walkthrough</h2>
<p class="intro">Every route the day-to-day accountant touches, captured against the pharma sample. Click any screenshot to open the live Bahi route in this build (load <code>pharma.khata</code> first).</p>
{accountant_html}

<h2>Manufacturing highlights</h2>
<p class="intro">High-value B2B invoices, heavy stock movement, WAC valuation. Goods-only workflow — no SACs, no credit notes in the sample.</p>
{render_highlight_grid(MANUFACTURING_HIGHLIGHTS)}

<h2>Consulting highlights</h2>
<p class="intro">Services-only LLP. No inventory, no purchases, simpler dashboard. Proof that Bahi's layout scales down as well as up.</p>
{render_highlight_grid(CONSULTING_HIGHLIGHTS)}

<h2>CA audit walkthrough</h2>
<p class="intro">One CA profile, three client files, one review workflow. The CA opens each <code>.khata</code> in sequence, runs trial balance / balance sheet / P&amp;L, uses the review panel to annotate and sign off, and exports a printable report — all without leaving the browser.</p>
{ca_html}

<h2>Capture summary</h2>
<p class="intro">Every screenshot on this page is generated by <code>capture.py</code> — a Playwright script that drives a local Bahi dev server, loads each sample file via Bahi's in-page globals, navigates to each route, and records a 1400×900 PNG. The script doubles as a regression test: any route that fails to render or throws a console error is flagged in <a href="CAPTURE-LOG.md">CAPTURE-LOG.md</a>.</p>
<div class="why-grid">
  <div class="why"><h4>Pharma</h4><p>{counts['pharma']} routes captured.</p></div>
  <div class="why"><h4>Manufacturing</h4><p>{counts['manufacturing']} routes captured.</p></div>
  <div class="why"><h4>Consulting</h4><p>{counts['consulting']} routes captured.</p></div>
  <div class="why"><h4>CA audit</h4><p>{counts['ca-audit']} routes across 3 client files.</p></div>
</div>

</main>

<footer>
  <p><b>Bahi</b> — part of the <a href="https://naklitechie.github.io/">NakliTechie browser-native series</a>.</p>
  <p>Source: <code>Bahi/index.html</code> &middot; Samples: <code>Bahi/sample-data/*.khata</code> &middot; Regenerate: <code>./regenerate.sh</code></p>
  <p class="alpha-note">Alpha build. Not tax advice. Not an audit tool. Compliance output is for review against your own filings.</p>
</footer>

</body>
</html>
'''

    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
