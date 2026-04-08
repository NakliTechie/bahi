#!/usr/bin/env python3
"""
Bahi demo screenshot capture — drives the live app via Playwright + Bahi's
in-page `readKhata` / `openDbFromBytes` globals (bypassing the FS Access picker).

Requirements:
    pip3 install playwright
    python3 -m playwright install chromium

Prerequisites:
    A dev server must be serving the Bahi/ directory at http://localhost:8101/.
    (Run `regenerate.sh` — it will start one if needed.)

Outputs:
    screenshots/<company>/NN-<slug>.png
    CAPTURE-LOG.md
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, Error as PWError, ConsoleMessage

ROOT     = Path(__file__).resolve().parent
SHOT_DIR = ROOT / "screenshots"
LOG_PATH = ROOT / "CAPTURE-LOG.md"
BASE_URL = "http://localhost:8101/"
VIEWPORT = {"width": 1400, "height": 900}

# ---------------------------------------------------------------------------
# Route plans
# ---------------------------------------------------------------------------
# Each row: (slug, hash, wait_ms, pre_js, post_js, caption_kind)
#   pre_js  — JS to run BEFORE nav() (e.g. set period selector defaults)
#   post_js — JS to run AFTER nav(), BEFORE screenshot (e.g. click first row)
#   wait_ms — ms to sleep after nav (and after post_js)

# Period picker helper — set a value and re-render the report
SET_PERIOD = """(sel, val) => {
    const el = document.querySelector(sel);
    if (el) { el.value = val; el.dispatchEvent(new Event('change', {bubbles:true})); }
}"""

# Full accountant walkthrough for pharma
PHARMA_ROUTES = [
    # Workspace & file
    ("01", "dashboard",           "#/dashboard",           700, None, None),
    ("02", "file-info",           "#/file",                400, None, None),

    # Masters
    ("03", "customers",           "#/customers",           400, None, None),
    ("04", "vendors",             "#/vendors",             400, None, None),
    ("05", "items",               "#/items",               400, None, None),
    ("06", "series",              "#/series",              400, None, None),

    # Sales daily
    ("07", "invoices",            "#/invoices",            500, None, None),
    ("08", "invoice-new",         "#/invoice/new",         500, None, None),
    ("09", "credit-notes",        "#/credit-notes",        400, None, None),
    ("10", "credit-note-new",     "#/credit-note/new",     500, None, None),

    # Purchase daily
    ("11", "purchases",           "#/purchases",           500, None, None),
    ("12", "purchase-new",        "#/purchase/new",        500, None, None),
    ("13", "debit-notes",         "#/debit-notes",         400, None, None),
    ("14", "debit-note-new",      "#/debit-note/new",      500, None, None),

    # Payments
    ("15", "payments",            "#/payments",            500, None, None),
    ("16", "payment-new",         "#/payment/new",         500, None, None),
    ("17", "vendor-payment-new",  "#/vendor-payment/new",  500, None, None),
    ("18", "tcs-collection-new",  "#/tcs-collection/new",  500, None, None),
    ("19", "advances",            "#/advances",            400, None, None),
    ("20", "advance-new",         "#/advance/new",         500, None, None),

    # Inventory
    ("21", "inventory-dashboard", "#/inventory",           500, None, None),
    ("22", "stock-on-hand",       "#/stock-on-hand",       500, None, None),
    ("23", "stock-movements",     "#/stock-movements",     500, None, None),
    ("24", "stock-register",      "#/stock-register",      500, None, None),
    ("25", "batches",             "#/batches",             400, None, None),
    ("26", "valuation-summary",   "#/valuation-summary",   500, None, None),
    ("27", "reorder-alerts",      "#/reorder-alerts",      400, None, None),
    ("28", "stock-aging",         "#/stock-aging",         500, None, None),
    ("29", "godowns",             "#/godowns",             400, None, None),

    # Delivery / e-way / transfers
    ("30", "delivery-challans",   "#/delivery-challans",   400, None, None),
    ("31", "delivery-challan-new","#/delivery-challan/new",500, None, None),
    ("32", "eway-bills",          "#/eway-bills",          400, None, None),
    ("33", "eway-bill-new",       "#/eway-bill/new",       500, None, None),
    ("34", "stock-transfers",     "#/stock-transfers",     400, None, None),
    ("35", "stock-transfer-out",  "#/stock-transfer/out/new", 500, None, None),
    ("36", "stock-transfer-in",   "#/stock-transfer/in/import", 500, None, None),

    # Accounting
    ("37", "journal-new",         "#/journal/new",         500, None, None),
    ("38", "bank-reconcile",      "#/bank-reconcile",      600, None, None),
    ("39", "day-book",            "#/day-book",            500, None, None),
    ("40", "account-ledger",      "#/account-ledger",      500, None, None),

    # Reports
    ("41", "trial-balance",       "#/trial-balance",       600, None, None),
    ("42", "balance-sheet",       "#/balance-sheet",       600, None, None),
    ("43", "pnl",                 "#/pnl",                 600, None, None),
    ("44", "sales-register",      "#/sales-register",      500, None, None),
    ("45", "purchase-register",   "#/purchase-register",   500, None, None),

    # Tax / compliance
    ("46", "gstr1",               "#/gstr1",               700, None, None),
    ("47", "gstr3b",              "#/gstr3b",              700, None, None),
    ("48", "cmp08",               "#/cmp08",               500, None, None),
    ("49", "form-26q",            "#/form-26q",            700, None, None),
    ("50", "form-27eq",           "#/form-27eq",           500, None, None),
    ("51", "form-27d",            "#/form-27d",            500, None, None),
    ("52", "tax-challans",        "#/tax-challans",        500, None, None),

    # Governance / year-end
    ("53", "period-locks",        "#/period-locks",        400, None, None),
    ("54", "fy-rollover",         "#/fy-rollover",         500, None, None),
    ("55", "annotations",         "#/annotations",         400, None, None),
    ("56", "settings",            "#/settings",            400, None, None),
    ("57", "debug",               "#/debug",               400, None, None),
    ("58", "workspace",           "#/workspace",           400, None, None),
]

# Manufacturing subset — goods-heavy, high-value B2B
MANUFACTURING_ROUTES = [
    ("01", "dashboard",          "#/dashboard",          700, None, None),
    ("02", "file-info",          "#/file",               400, None, None),
    ("03", "invoices",           "#/invoices",           500, None, None),
    ("04", "customers",          "#/customers",          400, None, None),
    ("05", "vendors",            "#/vendors",            400, None, None),
    ("06", "items",              "#/items",              400, None, None),
    ("07", "purchases",          "#/purchases",          500, None, None),
    ("08", "inventory",          "#/inventory",          500, None, None),
    ("09", "stock-on-hand",      "#/stock-on-hand",      500, None, None),
    ("10", "stock-movements",    "#/stock-movements",    500, None, None),
    ("11", "valuation-summary",  "#/valuation-summary",  500, None, None),
    ("12", "stock-aging",        "#/stock-aging",        500, None, None),
    ("13", "stock-register",     "#/stock-register",     500, None, None),
    ("14", "delivery-challans",  "#/delivery-challans",  400, None, None),
    ("15", "eway-bills",         "#/eway-bills",         400, None, None),
    ("16", "stock-transfers",    "#/stock-transfers",    400, None, None),
    ("17", "godowns",            "#/godowns",            400, None, None),
    ("18", "trial-balance",      "#/trial-balance",      600, None, None),
    ("19", "balance-sheet",      "#/balance-sheet",      600, None, None),
    ("20", "pnl",                "#/pnl",                600, None, None),
    ("21", "gstr1",              "#/gstr1",              700, None, None),
    ("22", "gstr3b",             "#/gstr3b",             700, None, None),
]

# Consulting subset — services only, simple
CONSULTING_ROUTES = [
    ("01", "dashboard",          "#/dashboard",          700, None, None),
    ("02", "file-info",          "#/file",               400, None, None),
    ("03", "invoices",           "#/invoices",           500, None, None),
    ("04", "customers",          "#/customers",          400, None, None),
    ("05", "items",              "#/items",              400, None, None),
    ("06", "credit-notes",       "#/credit-notes",       400, None, None),
    ("07", "payments",           "#/payments",           500, None, None),
    ("08", "advances",           "#/advances",           400, None, None),
    ("09", "journal-new",        "#/journal/new",        500, None, None),
    ("10", "day-book",           "#/day-book",           500, None, None),
    ("11", "trial-balance",      "#/trial-balance",      600, None, None),
    ("12", "balance-sheet",      "#/balance-sheet",      600, None, None),
    ("13", "pnl",                "#/pnl",                600, None, None),
    ("14", "sales-register",     "#/sales-register",     500, None, None),
    ("15", "gstr1",              "#/gstr1",              700, None, None),
    ("16", "gstr3b",             "#/gstr3b",             700, None, None),
    ("17", "form-26q",           "#/form-26q",           700, None, None),
]

# CA audit flow: each entry is (file, slug, hash, wait)
CA_AUDIT_ROUTES = [
    ("pharma",        "01", "client1-dashboard",      "#/dashboard",      700),
    ("pharma",        "02", "client1-trial-balance",  "#/trial-balance",  700),
    ("pharma",        "03", "client1-balance-sheet",  "#/balance-sheet",  700),
    ("pharma",        "04", "client1-pnl",            "#/pnl",            700),
    ("pharma",        "05", "client1-day-book",       "#/day-book",       600),
    ("pharma",        "06", "client1-ca-review",      "#/ca/review",      600),
    ("pharma",        "07", "client1-annotations",    "#/annotations",    500),
    ("pharma",        "08", "client1-ca-report",      "#/ca/report",      600),
    ("manufacturing", "09", "client2-dashboard",      "#/dashboard",      700),
    ("manufacturing", "10", "client2-trial-balance",  "#/trial-balance",  700),
    ("manufacturing", "11", "client2-balance-sheet",  "#/balance-sheet",  700),
    ("manufacturing", "12", "client2-pnl",            "#/pnl",            700),
    ("manufacturing", "13", "client2-ca-review",      "#/ca/review",      600),
    ("consulting",    "14", "client3-dashboard",      "#/dashboard",      700),
    ("consulting",    "15", "client3-trial-balance",  "#/trial-balance",  700),
    ("consulting",    "16", "client3-balance-sheet",  "#/balance-sheet",  700),
    ("consulting",    "17", "client3-pnl",            "#/pnl",            700),
    ("consulting",    "18", "client3-ca-adjustment",  "#/ca/adjustment/new", 600),
]

# ---------------------------------------------------------------------------
# The bypass-load JavaScript — pasted into evaluate()
# ---------------------------------------------------------------------------
BYPASS_LOAD_JS = """
async (fileName) => {
    const resp = await fetch('/sample-data/' + fileName);
    const blob = await resp.blob();
    const { manifest, dbBytes } = await readKhata(blob);
    const db = await openDbFromBytes(dbBytes);
    STATE.manifest = manifest;
    STATE.db = db;
    STATE.readOnly = false;
    STATE.fileHandle = {
        name: fileName,
        queryPermission: async () => 'granted',
        requestPermission: async () => 'granted',
    };
    applyTheme('crisp-paper');
    localStorage.setItem('bahi.theme', 'crisp-paper');
    localStorage.setItem('bahi.introSeen', '1');
    const modal = document.getElementById('modal');
    if (modal) { modal.innerHTML = ''; modal.classList.add('hidden'); }
    return { company: manifest.company?.name };
}
"""

NAV_AND_CLEAN_JS = """
async (hash) => {
    // Close any open modal from previous route
    const modal = document.getElementById('modal');
    if (modal) { modal.innerHTML = ''; modal.classList.add('hidden'); }
    nav(hash);
    return true;
}
"""

CHECK_RENDERED_JS = """
() => {
    const main = document.getElementById('main');
    if (!main) return { ok: false, reason: 'no main element' };
    const len = main.innerHTML.length;
    return { ok: len > 50, len, route: location.hash };
}
"""


def run():
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ("pharma", "manufacturing", "consulting", "ca-audit"):
        (SHOT_DIR / sub).mkdir(exist_ok=True)

    log_sections = {}   # name -> list of row dicts

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = context.new_page()

        console_errors = []
        def _on_console(msg: ConsoleMessage):
            if msg.type in ("error", "warning"):
                console_errors.append({"type": msg.type, "text": msg.text})
        page.on("console", _on_console)

        def load_file(file_name):
            console_errors.clear()
            page.goto(BASE_URL, wait_until="networkidle")
            result = page.evaluate(BYPASS_LOAD_JS, file_name)
            return result

        def capture_route(company, slug_num, slug, hash_, wait_ms):
            console_errors.clear()
            t0 = time.time()
            try:
                page.evaluate(NAV_AND_CLEAN_JS, hash_)
                page.wait_for_timeout(wait_ms)
                status = page.evaluate(CHECK_RENDERED_JS)
                path = SHOT_DIR / company / f"{slug_num}-{slug}.png"
                page.screenshot(path=str(path), full_page=False)
                elapsed = int((time.time() - t0) * 1000)
                errs = [e for e in console_errors if e["type"] == "error"]
                return {
                    "num": slug_num,
                    "route": hash_,
                    "slug": slug,
                    "status": "ok" if status.get("ok") else "empty",
                    "ms": elapsed,
                    "errors": errs,
                    "path": str(path.relative_to(ROOT)),
                }
            except Exception as e:
                return {
                    "num": slug_num,
                    "route": hash_,
                    "slug": slug,
                    "status": "fail",
                    "ms": int((time.time() - t0) * 1000),
                    "errors": [{"type": "exception", "text": str(e)}],
                    "path": None,
                }

        # ---------- pharma ----------
        print("[pharma] bypass-loading...", flush=True)
        load_file("pharma.khata")
        rows = []
        for slug_num, slug, hash_, wait, _pre, _post in PHARMA_ROUTES:
            row = capture_route("pharma", slug_num, slug, hash_, wait)
            print(f"  [{row['status']:4}] {slug_num} {hash_} ({row['ms']}ms)"
                  + (f"  ERRORS: {len(row['errors'])}" if row['errors'] else ""), flush=True)
            rows.append(row)
        log_sections["pharma.khata"] = rows

        # ---------- manufacturing ----------
        print("[manufacturing] bypass-loading...", flush=True)
        load_file("manufacturing.khata")
        rows = []
        for slug_num, slug, hash_, wait, _pre, _post in MANUFACTURING_ROUTES:
            row = capture_route("manufacturing", slug_num, slug, hash_, wait)
            print(f"  [{row['status']:4}] {slug_num} {hash_} ({row['ms']}ms)"
                  + (f"  ERRORS: {len(row['errors'])}" if row['errors'] else ""), flush=True)
            rows.append(row)
        log_sections["manufacturing.khata"] = rows

        # ---------- consulting ----------
        print("[consulting] bypass-loading...", flush=True)
        load_file("consulting.khata")
        rows = []
        for slug_num, slug, hash_, wait, _pre, _post in CONSULTING_ROUTES:
            row = capture_route("consulting", slug_num, slug, hash_, wait)
            print(f"  [{row['status']:4}] {slug_num} {hash_} ({row['ms']}ms)"
                  + (f"  ERRORS: {len(row['errors'])}" if row['errors'] else ""), flush=True)
            rows.append(row)
        log_sections["consulting.khata"] = rows

        # ---------- CA audit flow ----------
        print("[ca-audit] walkthrough across 3 files...", flush=True)
        rows = []
        current_file = None
        for file_name, slug_num, slug, hash_, wait in CA_AUDIT_ROUTES:
            fname = f"{file_name}.khata"
            if fname != current_file:
                load_file(fname)
                # Switch mode to CA for these routes
                page.evaluate("""() => {
                    STATE.mode = 'ca';
                    STATE.caProfile = STATE.caProfile || { name: 'CA Sample', firm: 'Sample & Co' };
                    try { localStorage.setItem('bahi.mode', 'ca'); } catch (_) {}
                }""")
                current_file = fname
            row = capture_route("ca-audit", slug_num, slug, hash_, wait)
            row["source_file"] = fname
            print(f"  [{row['status']:4}] {slug_num} {hash_} ({file_name}, {row['ms']}ms)"
                  + (f"  ERRORS: {len(row['errors'])}" if row['errors'] else ""), flush=True)
            rows.append(row)
        log_sections["ca-audit (across 3 files)"] = rows

        browser.close()

    # ---------- write CAPTURE-LOG.md ----------
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Capture run — {ts}", ""]
    grand_ok = 0
    grand_total = 0
    grand_errors = 0
    for section, rows in log_sections.items():
        lines.append(f"## {section}")
        lines.append("")
        lines.append("| # | Route | Status | ms | Console errors |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            grand_total += 1
            if r["status"] == "ok":
                grand_ok += 1
            grand_errors += len(r.get("errors", []))
            err_text = "—"
            if r.get("errors"):
                err_text = "; ".join(e["text"][:80] for e in r["errors"][:2])
                err_text = err_text.replace("|", "\\|").replace("\n", " ")
                if len(r["errors"]) > 2:
                    err_text += f" (+{len(r['errors']) - 2} more)"
            lines.append(f"| {r['num']} | `{r['route']}` | {r['status']} | {r['ms']} | {err_text} |")
        lines.append("")

    lines.insert(2, f"**Summary**: {grand_ok}/{grand_total} routes rendered ok · {grand_errors} total console errors")
    lines.insert(3, "")

    LOG_PATH.write_text("\n".join(lines))
    print(f"\nLog written: {LOG_PATH}")
    print(f"Summary: {grand_ok}/{grand_total} ok, {grand_errors} errors")


if __name__ == "__main__":
    run()
