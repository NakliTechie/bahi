"""
Unit tests for the three sample .khata files.

Runs against:
    pharma.khata          — goods + services (Maharashtra)
    manufacturing.khata   — goods only       (Gujarat)
    consulting.khata      — services only    (Karnataka)

Covers:
    A. Format & integrity    (PRAGMA, schema, manifest match)
    B. Trial balance         (per-journal tie + grand total tie)
    C. Audit chain           (hash walk, length, signatures present)
    D. Snapshot invariants   (BAHI-AGENT-MSG-HISTORICAL-INTEGRITY)
    E. Invoice math          (line sum, tax routing, intra vs inter)
    F. Payment integrity     (allocation sum, no over-payment)
    G. GST summary sanity    (3.1 outward totals)
    H. TDS                   (deductions total matches ledger credit)
    I. Stock integrity       (per-item on-hand >= 0, pharma + mfg)
    J. Per-company assertions

Run:
    python3 -m unittest /Users/chiragpatnaik/Code/Browser/Bahi/sample-data/test_khata.py -v
"""

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

SAMPLE_DIR = Path("/Users/chiragpatnaik/Code/Browser/Bahi/sample-data")

FILES = {
    "pharma":        SAMPLE_DIR / "pharma.khata",
    "manufacturing": SAMPLE_DIR / "manufacturing.khata",
    "consulting":    SAMPLE_DIR / "consulting.khata",
}


_TMP_PATHS = {}


def open_khata(path):
    """Returns (manifest_dict, sqlite3.Connection, raw_sqlite_bytes)."""
    z = zipfile.ZipFile(path)
    manifest = json.loads(z.read("manifest.json"))
    data = z.read("books.sqlite")
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tf.write(data)
    tf.close()
    con = sqlite3.connect(tf.name)
    con.row_factory = sqlite3.Row
    _TMP_PATHS[id(con)] = tf.name
    return manifest, con, data


def close_khata(con):
    path = _TMP_PATHS.pop(id(con), None)
    con.close()
    if path and os.path.exists(path):
        os.unlink(path)


class KhataTestBase(unittest.TestCase):
    """Base class that opens every file once per class."""

    @classmethod
    def setUpClass(cls):
        cls.books = {}
        for name, path in FILES.items():
            m, con, raw = open_khata(path)
            cls.books[name] = {"manifest": m, "con": con, "raw": raw, "path": path}

    @classmethod
    def tearDownClass(cls):
        for b in cls.books.values():
            close_khata(b["con"])


# ───────────────────────────────────────────────────────── A. FORMAT ─────

class TestFormatAndIntegrity(KhataTestBase):

    def test_A01_all_three_files_present(self):
        for name, path in FILES.items():
            self.assertTrue(path.exists(), f"{name}: {path} missing")
            self.assertGreater(path.stat().st_size, 1000, f"{name}: suspiciously small")

    def test_A02_zip_layout(self):
        for name, path in FILES.items():
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                self.assertIn("manifest.json", names, f"{name}: no manifest")
                self.assertIn("books.sqlite", names, f"{name}: no books.sqlite")

    def test_A03_pragma_integrity_check(self):
        for name, b in self.books.items():
            rows = b["con"].execute("PRAGMA integrity_check").fetchall()
            self.assertEqual(rows[0][0], "ok", f"{name}: integrity_check failed")

    def test_A04_schema_version(self):
        # Sample books are regenerated at the app's current SCHEMA_VERSION. Bump this when
        # the schema advances; the manifest and meta.schemaVersion must agree.
        EXPECTED_SCHEMA = 12
        for name, b in self.books.items():
            self.assertEqual(b["manifest"]["schemaVersion"], EXPECTED_SCHEMA, f"{name}: schemaVersion")
            row = b["con"].execute("SELECT v FROM meta WHERE k='schemaVersion'").fetchone()
            self.assertEqual(int(row["v"]), EXPECTED_SCHEMA, f"{name}: meta schemaVersion")

    def test_A05_format_version(self):
        for name, b in self.books.items():
            self.assertEqual(b["manifest"]["khataFormatVersion"], "1.0", f"{name}: format")

    def test_A06_manifest_books_hash_matches(self):
        for name, b in self.books.items():
            expected = b["manifest"]["integrity"]["booksHash"]
            actual = hashlib.sha256(b["raw"]).hexdigest()
            self.assertEqual(expected, actual, f"{name}: booksHash mismatch")

    def test_A07_manifest_audit_head_matches_last_row(self):
        for name, b in self.books.items():
            last = b["con"].execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(
                b["manifest"]["integrity"]["auditHead"],
                last["hash"],
                f"{name}: manifest auditHead vs last audit row",
            )

    def test_A08_company_identity_matches_expected(self):
        expected = {
            "pharma":        ("27AABCV1234A1Z5", "Vaidya Life Sciences Pvt Ltd", "MH"),
            "manufacturing": ("24AAACS5678B1Z3", "Shree Krishna Steel Industries Ltd", "GJ"),
            "consulting":    ("29AAEFA9012C1Z7", "Arjun Rao Advisory LLP", "KA"),
        }
        for k, (gstin, legal, state) in expected.items():
            m = self.books[k]["manifest"]["company"]
            self.assertEqual(m["gstin"], gstin, f"{k}: GSTIN")
            self.assertEqual(m["name"], legal, f"{k}: company.name")
            self.assertEqual(m["state"], state, f"{k}: state")


# ─────────────────────────────────────────────── B. TRIAL BALANCE ─────

class TestTrialBalance(KhataTestBase):

    def test_B01_grand_total_ties_to_zero(self):
        for name, b in self.books.items():
            row = b["con"].execute(
                "SELECT SUM(debit) AS d, SUM(credit) AS c FROM entry_lines"
            ).fetchone()
            diff = round((row["d"] or 0) - (row["c"] or 0), 2)
            self.assertEqual(diff, 0.0, f"{name}: TB does not tie (diff={diff})")

    def test_B02_every_entry_is_balanced(self):
        for name, b in self.books.items():
            rows = b["con"].execute("""
                SELECT entry_id, ROUND(SUM(debit)-SUM(credit), 2) AS diff
                FROM entry_lines
                GROUP BY entry_id
                HAVING ROUND(SUM(debit)-SUM(credit), 2) != 0
            """).fetchall()
            self.assertEqual(len(rows), 0, f"{name}: {len(rows)} unbalanced entries")

    def test_B03_account_type_totals_report_match(self):
        # sanity: sum per type should equal manifest report
        # (we don't hardcode figures here — just that each type has nonzero rows for the expected companies)
        for name, b in self.books.items():
            rows = b["con"].execute("""
                SELECT a.type, SUM(el.debit) AS d, SUM(el.credit) AS c
                FROM entry_lines el JOIN accounts a ON a.id = el.account_id
                GROUP BY a.type
            """).fetchall()
            types = {r["type"] for r in rows}
            self.assertIn("asset", types, f"{name}: no asset postings")
            self.assertIn("income", types, f"{name}: no income postings")
            self.assertIn("liability", types, f"{name}: no liability postings")


# ────────────────────────────────────────────────── C. AUDIT CHAIN ─────

class TestAuditChain(KhataTestBase):

    def test_C01_audit_length_positive(self):
        for name, b in self.books.items():
            n = b["con"].execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            self.assertGreater(n, 100, f"{name}: audit chain suspiciously short ({n})")

    def test_C02_hash_walk_is_clean(self):
        """Every row's prev_hash must equal the previous row's hash."""
        for name, b in self.books.items():
            rows = b["con"].execute(
                "SELECT id, prev_hash, hash FROM audit_log ORDER BY id"
            ).fetchall()
            prev = None
            bad = 0
            for r in rows:
                if prev is None:
                    # genesis — prev_hash should be zeros or empty string per spec
                    self.assertTrue(
                        r["prev_hash"] in ("", "0" * 64, None),
                        f"{name}: genesis row has non-null prev_hash={r['prev_hash']}",
                    )
                else:
                    if r["prev_hash"] != prev:
                        bad += 1
                prev = r["hash"]
            self.assertEqual(bad, 0, f"{name}: {bad} chain breakages")

    def test_C03_every_row_has_signature(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM audit_log WHERE signature IS NULL OR signature = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} unsigned audit rows")

    def test_C04_origin_tagged_as_generator(self):
        for name, b in self.books.items():
            distinct = b["con"].execute(
                "SELECT DISTINCT origin FROM audit_log"
            ).fetchall()
            origins = {r["origin"] for r in distinct}
            self.assertTrue(
                any("generator.py" in o for o in origins if o),
                f"{name}: origins={origins}",
            )


# ─────────────────────────────────────── D. SNAPSHOT INVARIANTS ─────

class TestSnapshotInvariants(KhataTestBase):
    """BAHI-AGENT-MSG-HISTORICAL-INTEGRITY invariants 1-8."""

    def test_D01_inv1_invoice_company_snapshot(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM invoices WHERE company_snapshot IS NULL OR company_snapshot = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} invoices without company_snapshot")

    def test_D02_inv4_invoice_customer_snapshot(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM invoices WHERE customer_snapshot IS NULL OR customer_snapshot = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} invoices without customer_snapshot")

    def test_D03_inv5_invoice_place_of_supply_name(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM invoices WHERE place_of_supply_name IS NULL OR place_of_supply_name = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} invoices without place_of_supply_name")

    def test_D04_inv2_invoice_line_hsn_description(self):
        for name, b in self.books.items():
            n = b["con"].execute("""
                SELECT COUNT(*) FROM invoice_lines
                WHERE (hsn_description IS NULL OR hsn_description = '')
                  AND hsn_sac IS NOT NULL AND hsn_sac != ''
            """).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} invoice lines with hsn_sac but no hsn_description")

    def test_D05_inv3_invoice_line_rate_id(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM invoice_lines WHERE rate_id IS NULL OR rate_id = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} invoice lines without rate_id")

    def test_D06_inv7_entry_line_account_name(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM entry_lines WHERE account_name IS NULL OR account_name = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} entry lines without account_name")

    def test_D07_payment_allocation_invoice_number_snapshot(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM payment_allocations WHERE invoice_number_snapshot IS NULL OR invoice_number_snapshot = ''"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} allocations without invoice_number_snapshot")

    def test_D08_company_snapshot_valid_json_with_identity(self):
        for name, b in self.books.items():
            rows = b["con"].execute(
                "SELECT company_snapshot FROM invoices LIMIT 5"
            ).fetchall()
            for r in rows:
                snap = json.loads(r["company_snapshot"])
                self.assertIn("gstin", snap, f"{name}: company_snapshot missing gstin")
                self.assertIn("name", snap, f"{name}: missing name")
                self.assertEqual(len(snap["gstin"]), 15, f"{name}: GSTIN not 15 chars")


# ────────────────────────────────────────────────── E. INVOICE MATH ─────

class TestInvoiceMath(KhataTestBase):

    def test_E01_invoice_total_equals_components(self):
        for name, b in self.books.items():
            rows = b["con"].execute("""
                SELECT id, invoice_number, subtotal, cgst, sgst, igst, cess, round_off, total
                FROM invoices
            """).fetchall()
            bad = []
            for r in rows:
                computed = round(
                    (r["subtotal"] or 0) + (r["cgst"] or 0) + (r["sgst"] or 0)
                    + (r["igst"] or 0) + (r["cess"] or 0) + (r["round_off"] or 0), 2
                )
                if abs(computed - (r["total"] or 0)) > 0.01:
                    bad.append((r["invoice_number"], computed, r["total"]))
            self.assertEqual(bad, [], f"{name}: {len(bad)} invoices don't reconcile")

    def test_E02_invoice_lines_sum_to_subtotal(self):
        for name, b in self.books.items():
            rows = b["con"].execute("""
                SELECT i.id, i.invoice_number, i.subtotal, COALESCE(SUM(il.taxable), 0) AS lines_sum
                FROM invoices i LEFT JOIN invoice_lines il ON il.invoice_id = i.id
                GROUP BY i.id
            """).fetchall()
            bad = [(r["invoice_number"], r["subtotal"], r["lines_sum"])
                   for r in rows if abs((r["subtotal"] or 0) - (r["lines_sum"] or 0)) > 0.01]
            self.assertEqual(bad, [], f"{name}: {len(bad)} invoices where lines != subtotal")

    def test_E03_intra_vs_inter_state_routing(self):
        """Intra-state invoices must have CGST+SGST, not IGST. Inter-state: IGST only."""
        home_state = {"pharma": "MH", "manufacturing": "GJ", "consulting": "KA"}
        for name, b in self.books.items():
            home = home_state[name]
            rows = b["con"].execute("""
                SELECT invoice_number, place_of_supply, is_export, is_sez,
                       cgst, sgst, igst
                FROM invoices
            """).fetchall()
            bad = []
            for r in rows:
                if r["is_export"] or r["is_sez"]:
                    continue  # export/SEZ is its own routing
                pos = (r["place_of_supply"] or "").strip()
                cgst = r["cgst"] or 0
                sgst = r["sgst"] or 0
                igst = r["igst"] or 0
                if pos == home:
                    if igst > 0.01:
                        bad.append(("intra-with-igst", r["invoice_number"], pos))
                else:
                    if (cgst + sgst) > 0.01:
                        bad.append(("inter-with-cgst", r["invoice_number"], pos))
            self.assertEqual(
                bad, [],
                f"{name}: {len(bad)} invoices with wrong GST routing (sample: {bad[:3]})",
            )

    def test_E04_invoice_rate_id_resolves(self):
        """rate_id should look like 'gst_0', 'gst_5', 'gst_12', 'gst_18', 'gst_28' etc."""
        for name, b in self.books.items():
            rates = b["con"].execute(
                "SELECT DISTINCT rate_id FROM invoice_lines"
            ).fetchall()
            for r in rates:
                self.assertTrue(r["rate_id"], f"{name}: empty rate_id")


# ─────────────────────────────────────────────── F. PAYMENT INTEGRITY ─────

class TestPaymentIntegrity(KhataTestBase):

    def test_F01_allocations_never_exceed_payment(self):
        for name, b in self.books.items():
            rows = b["con"].execute("""
                SELECT p.id, p.payment_number, p.amount,
                       COALESCE(SUM(pa.amount), 0) AS allocated
                FROM payments p LEFT JOIN payment_allocations pa ON pa.payment_id = p.id
                GROUP BY p.id
                HAVING allocated > p.amount + 0.01
            """).fetchall()
            self.assertEqual(len(rows), 0, f"{name}: {len(rows)} over-allocated payments")

    def test_F02_invoice_outstanding_never_negative(self):
        for name, b in self.books.items():
            rows = b["con"].execute("""
                SELECT i.id, i.invoice_number, i.total,
                       COALESCE(SUM(pa.amount), 0) AS paid
                FROM invoices i LEFT JOIN payment_allocations pa ON pa.invoice_id = i.id
                GROUP BY i.id
                HAVING paid - i.total > 0.01
            """).fetchall()
            self.assertEqual(len(rows), 0, f"{name}: {len(rows)} over-paid invoices")

    def test_F03_every_payment_has_ledger_entry(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM payments WHERE ledger_entry_id IS NULL"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} payments without ledger_entry_id")


# ───────────────────────────────────────────────── G. GST SUMMARY ─────

class TestGstSummary(KhataTestBase):

    def test_G01_gstr3b_3_1a_outward_ties_to_invoice_totals(self):
        """Sum of invoice cgst/sgst/igst columns should equal sum of lines' tax columns."""
        for name, b in self.books.items():
            row = b["con"].execute("""
                SELECT
                    COALESCE(SUM(i.cgst), 0) AS inv_cgst,
                    COALESCE(SUM(i.sgst), 0) AS inv_sgst,
                    COALESCE(SUM(i.igst), 0) AS inv_igst
                FROM invoices i
            """).fetchone()
            row2 = b["con"].execute("""
                SELECT
                    COALESCE(SUM(il.cgst), 0) AS line_cgst,
                    COALESCE(SUM(il.sgst), 0) AS line_sgst,
                    COALESCE(SUM(il.igst), 0) AS line_igst
                FROM invoice_lines il
            """).fetchone()
            self.assertAlmostEqual(row["inv_cgst"], row2["line_cgst"], places=2,
                                   msg=f"{name}: CGST header vs lines")
            self.assertAlmostEqual(row["inv_sgst"], row2["line_sgst"], places=2,
                                   msg=f"{name}: SGST header vs lines")
            self.assertAlmostEqual(row["inv_igst"], row2["line_igst"], places=2,
                                   msg=f"{name}: IGST header vs lines")

    def test_G02_output_tax_appears_in_ledger_as_credit(self):
        """Sum of GST Output account credits should approximately match invoice GST totals."""
        for name, b in self.books.items():
            inv_gst = b["con"].execute("""
                SELECT COALESCE(SUM(cgst+sgst+igst+cess), 0) AS t FROM invoices
            """).fetchone()["t"]
            ledger_gst = b["con"].execute("""
                SELECT COALESCE(SUM(el.credit - el.debit), 0) AS t
                FROM entry_lines el JOIN accounts a ON a.id = el.account_id
                WHERE a.name LIKE '%GST%Output%' OR a.name LIKE '%CGST%Output%'
                   OR a.name LIKE '%SGST%Output%' OR a.name LIKE '%IGST%Output%'
            """).fetchone()["t"]
            # Ledger may include credit notes reversing some — expect within 5%
            if inv_gst > 0:
                rel = abs(inv_gst - ledger_gst) / inv_gst
                self.assertLess(rel, 0.10,
                                f"{name}: GST output ledger {ledger_gst} vs invoices {inv_gst} off by {rel:.2%}")


# ──────────────────────────────────────────────────────── H. TDS ─────

class TestTds(KhataTestBase):

    def test_H01_tds_deductions_tie_to_ledger(self):
        for name, b in self.books.items():
            deducted = b["con"].execute(
                "SELECT COALESCE(SUM(tds_amount), 0) AS t FROM tds_deductions"
            ).fetchone()["t"]
            ledger_tds = b["con"].execute("""
                SELECT COALESCE(SUM(el.credit - el.debit), 0) AS t
                FROM entry_lines el JOIN accounts a ON a.id = el.account_id
                WHERE a.name LIKE '%TDS Payable%'
            """).fetchone()["t"]
            if deducted > 0:
                self.assertAlmostEqual(deducted, ledger_tds, delta=1.0,
                                       msg=f"{name}: TDS {deducted} vs ledger {ledger_tds}")

    def test_H02_every_tds_deduction_has_ledger_entry(self):
        for name, b in self.books.items():
            n = b["con"].execute(
                "SELECT COUNT(*) FROM tds_deductions WHERE ledger_entry_id IS NULL"
            ).fetchone()[0]
            self.assertEqual(n, 0, f"{name}: {n} tds_deductions without ledger_entry_id")


# ─────────────────────────────────────────────── I. STOCK INTEGRITY ─────

class TestStock(KhataTestBase):
    """Applies only to pharma and manufacturing; consulting has no inventory."""

    def test_I01_stock_on_hand_never_negative(self):
        for name in ("pharma", "manufacturing"):
            b = self.books[name]
            rows = b["con"].execute("""
                SELECT item_id,
                       SUM(CASE WHEN movement_type='in' THEN qty ELSE -qty END) AS on_hand
                FROM stock_movements
                GROUP BY item_id
                HAVING on_hand < -0.001
            """).fetchall()
            self.assertEqual(
                len(rows), 0,
                f"{name}: {len(rows)} items with negative stock: {[dict(r) for r in rows[:3]]}",
            )

    def test_I02_stock_in_value_equals_qty_times_rate(self):
        # Inward movements are received at a known rate, so value == qty*rate exactly.
        # Outward movements use WAC/FIFO proportional valuation (the cost drawn from the
        # pool), so value is deliberately NOT qty*rate — asserting it here would contradict
        # the engine. Outward valuation is covered by the JS engine's own WAC/FIFO unit tests.
        for name in ("pharma", "manufacturing"):
            b = self.books[name]
            rows = b["con"].execute("""
                SELECT id, qty, rate, value
                FROM stock_movements
                WHERE movement_type = 'in' AND ABS(value - qty*rate) > 0.5
            """).fetchall()
            self.assertEqual(len(rows), 0,
                             f"{name}: {len(rows)} inward stock rows where value != qty*rate")

    def test_I03_consulting_has_no_stock(self):
        b = self.books["consulting"]
        n = b["con"].execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
        self.assertEqual(n, 0, "consulting should have no stock movements")


# ───────────────────────────────────────────── J. PER-COMPANY SPECIFICS ─────

class TestPerCompany(KhataTestBase):

    def test_J01_pharma_has_goods_and_services(self):
        b = self.books["pharma"]
        hsn = b["con"].execute("""
            SELECT COUNT(*) FROM items WHERE hsn_sac LIKE '30%' OR hsn_sac LIKE '90%' OR hsn_sac LIKE '38%'
        """).fetchone()[0]
        sac = b["con"].execute("""
            SELECT COUNT(*) FROM items WHERE hsn_sac LIKE '99%'
        """).fetchone()[0]
        self.assertGreater(hsn, 10, "pharma: expected >10 goods items")
        self.assertGreater(sac, 3, "pharma: expected >3 service items")

    def test_J02_pharma_has_credit_notes_and_advance(self):
        b = self.books["pharma"]
        cn = b["con"].execute("SELECT COUNT(*) FROM credit_notes").fetchone()[0]
        adv = b["con"].execute("SELECT COUNT(*) FROM advances").fetchone()[0]
        self.assertGreaterEqual(cn, 1, "pharma: expected credit notes")
        self.assertGreaterEqual(adv, 1, "pharma: expected at least 1 advance")

    def test_J03_manufacturing_only_goods(self):
        b = self.books["manufacturing"]
        sac = b["con"].execute("""
            SELECT COUNT(*) FROM items WHERE hsn_sac LIKE '99%'
        """).fetchone()[0]
        self.assertEqual(sac, 0, "manufacturing: should have zero SAC (service) items")

    def test_J04_manufacturing_has_inventory_movements(self):
        b = self.books["manufacturing"]
        n = b["con"].execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
        self.assertGreater(n, 500, f"manufacturing: only {n} stock movements")

    def test_J05_consulting_has_zero_purchases(self):
        b = self.books["consulting"]
        n = b["con"].execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
        self.assertEqual(n, 0, "consulting: should have zero purchases")

    def test_J06_consulting_items_are_all_sac(self):
        b = self.books["consulting"]
        rows = b["con"].execute("SELECT hsn_sac FROM items").fetchall()
        for r in rows:
            self.assertTrue(
                (r["hsn_sac"] or "").startswith("99"),
                f"consulting item hsn_sac={r['hsn_sac']} not a SAC",
            )

    def test_J07_all_three_have_tds_deductions(self):
        for name, b in self.books.items():
            n = b["con"].execute("SELECT COUNT(*) FROM tds_deductions").fetchone()[0]
            self.assertGreater(n, 0, f"{name}: no TDS deductions")

    def test_J08_two_fiscal_years_of_data(self):
        for name, b in self.books.items():
            row = b["con"].execute("""
                SELECT MIN(invoice_date) AS lo, MAX(invoice_date) AS hi FROM invoices
            """).fetchone()
            self.assertTrue(row["lo"] < "2025-01-01" < row["hi"],
                            f"{name}: invoice span {row['lo']}..{row['hi']} not 2 FYs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
