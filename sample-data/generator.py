#!/usr/bin/env python3
"""
Bahi sample-data generator.

Produces three realistic .khata files (pharma, manufacturing, consulting)
that fully conform to the v1.0 .khata format and Bahi schema v12.

Re-running with the same Python version produces byte-identical output
(deterministic seeds, fixed timestamps).

Usage:
    python3 generator.py
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import sqlite3
import sys
import uuid
import zipfile
from base64 import b64encode
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

# === Constants matching index.html ===

KHATA_FORMAT_VERSION = "1.0"
SCHEMA_VERSION = 12
GENESIS_PREV = "0" * 64

# Origin tag — non-browser context. Bahi uses 'file://' as the fallback;
# we use a distinct origin to mark these as synthetic.
GENERATOR_ORIGIN = "local-file://generator.py"

# A fixed pseudo-"now" for deterministic output. Use today's date as
# captured by the task spec; the actual file create flows treat this as
# the moment of creation.
FIXED_NOW = datetime(2026, 4, 8, 9, 0, 0, tzinfo=timezone.utc)

# GST 2.0 — compensation cess was discontinued for all but the tobacco family w.e.f. this date.
# The seeded sample cess (aerated waters 12% ad valorem, coal ₹400/tonne specific) therefore
# applies only to invoices/bills dated before the cutover; on/after it the cess is zero.
CESS_CUTOVER = "2025-09-22"
def cess_active_on(date_iso: str) -> bool:
    return date_iso < CESS_CUTOVER

OUT_DIR = Path(__file__).resolve().parent

# === Reference data (mirror of index.html) ===

# State list: (iso, gstin_code, full_name)
STATE_LIST = [
    ("JK", "01", "Jammu and Kashmir"), ("HP", "02", "Himachal Pradesh"),
    ("PB", "03", "Punjab"), ("CH", "04", "Chandigarh"),
    ("UT", "05", "Uttarakhand"), ("HR", "06", "Haryana"),
    ("DL", "07", "Delhi"), ("RJ", "08", "Rajasthan"),
    ("UP", "09", "Uttar Pradesh"), ("BR", "10", "Bihar"),
    ("SK", "11", "Sikkim"), ("AR", "12", "Arunachal Pradesh"),
    ("NL", "13", "Nagaland"), ("MN", "14", "Manipur"),
    ("MZ", "15", "Mizoram"), ("TR", "16", "Tripura"),
    ("ML", "17", "Meghalaya"), ("AS", "18", "Assam"),
    ("WB", "19", "West Bengal"), ("JH", "20", "Jharkhand"),
    ("OR", "21", "Odisha"), ("CT", "22", "Chhattisgarh"),
    ("MP", "23", "Madhya Pradesh"), ("GJ", "24", "Gujarat"),
    ("DH", "26", "Dadra and Nagar Haveli and Daman and Diu"),
    ("MH", "27", "Maharashtra"), ("KA", "29", "Karnataka"),
    ("GA", "30", "Goa"), ("LD", "31", "Lakshadweep"),
    ("KL", "32", "Kerala"), ("TN", "33", "Tamil Nadu"),
    ("PY", "34", "Puducherry"), ("AN", "35", "Andaman and Nicobar Islands"),
    ("TG", "36", "Telangana"), ("AP", "37", "Andhra Pradesh"),
    ("LA", "38", "Ladakh"),
]
STATE_BY_ISO = {iso: (iso, gst, name) for iso, gst, name in STATE_LIST}

# HSN/SAC seed (mirror of HSN_SEED + SAC_SEED in index.html)
HSN_SEED = {
    "0401": ("Milk and cream, not concentrated nor sweetened", "gst-0"),
    "1006": ("Rice", "gst-0"),
    "1701": ("Cane or beet sugar", "gst-5"),
    "3003": ("Medicaments (bulk / not retail), two or more constituents", "gst-12"),
    "3004": ("Medicaments, packaged for retail sale", "gst-12"),
    "3822": ("Diagnostic or laboratory reagents", "gst-12"),
    "3917": ("Plastic tubes, pipes and fittings", "gst-18"),
    "4818": ("Toilet paper, tissues, towels (paper)", "gst-18"),
    "5208": ("Woven cotton fabrics, ≤200 g/m²", "gst-5"),
    "6109": ("T-shirts, singlets, knitted or crocheted", "gst-5"),
    "7208": ("Hot-rolled flat steel, width ≥ 600 mm", "gst-18"),
    "7213": ("Hot-rolled bars and rods of iron or non-alloy steel", "gst-18"),
    "7214": ("Other bars and rods of iron or non-alloy steel", "gst-18"),
    "7216": ("Angles, shapes and sections of iron or non-alloy steel", "gst-18"),
    "7217": ("Wire of iron or non-alloy steel", "gst-18"),
    "7304": ("Tubes, pipes, seamless, of iron or steel", "gst-18"),
    "7308": ("Structures of iron or steel", "gst-18"),
    "8471": ("Automatic data-processing machines (computers)", "gst-18"),
    "8517": ("Telephone sets, smartphones", "gst-18"),
    "8703": ("Motor cars and other passenger vehicles", "gst-28"),
    "9018": ("Medical, surgical, dental or veterinary instruments", "gst-18"),
    "9403": ("Other furniture and parts", "gst-18"),
}
SAC_SEED = {
    "998311": ("Management consulting services", "gst-18"),
    "998313": ("Information technology consulting services", "gst-18"),
    "998314": ("Information technology design and development services", "gst-18"),
    "998315": ("Hosting and IT infrastructure provisioning services", "gst-18"),
    "998361": ("Advertising services", "gst-18"),
    "998511": ("Executive search services", "gst-18"),
    "998596": ("Events, exhibitions and conventions", "gst-18"),
    "999293": ("Commercial training and coaching", "gst-18"),
    "996511": ("Road transport of goods (refrigerated / non-refrigerated)", "gst-5"),
    "996819": ("Other delivery services", "gst-18"),
}
ALL_HSN = {**HSN_SEED, **SAC_SEED}

# Forensic rate IDs → percentage (only the rates we actually use)
RATE_BY_ID = {
    "gst-0": 0, "gst-5": 5, "gst-12": 12, "gst-18": 18, "gst-28": 28,
}

# Standard Indian Chart of Accounts seed (mirror of COA_SEED). Two-pass.
COA_SEED: List[Tuple[str, str, Optional[str]]] = [
    # Assets
    ("Current Assets", "asset", None),
    ("Bank Accounts", "asset", "Current Assets"),
    ("Cash", "asset", "Current Assets"),
    ("Sundry Debtors", "asset", "Current Assets"),
    ("Customer Advances Paid", "asset", "Current Assets"),
    ("TDS Receivable", "asset", "Current Assets"),
    ("Stock-in-Hand", "asset", "Current Assets"),
    ("Fixed Assets", "asset", None),
    # Liabilities
    ("Current Liabilities", "liability", None),
    ("Sundry Creditors", "liability", "Current Liabilities"),
    ("Customer Advances Received", "liability", "Current Liabilities"),
    ("TCS Payable", "liability", "Current Liabilities"),
    ("TDS Payable", "liability", "Current Liabilities"),
    ("Duties & Taxes", "liability", None),
    ("CGST Output", "liability", "Duties & Taxes"),
    ("SGST Output", "liability", "Duties & Taxes"),
    ("IGST Output", "liability", "Duties & Taxes"),
    ("CGST Input", "liability", "Duties & Taxes"),
    ("SGST Input", "liability", "Duties & Taxes"),
    ("IGST Input", "liability", "Duties & Taxes"),
    ("GST RCM Input", "liability", "Duties & Taxes"),
    ("GST RCM Output", "liability", "Duties & Taxes"),
    ("Cess", "liability", "Duties & Taxes"),
    ("Composition Tax Payable", "liability", "Duties & Taxes"),
    # Equity
    ("Capital Account", "equity", None),
    ("Drawings", "equity", None),
    ("P&L Summary", "equity", None),
    # Income
    ("Sales Accounts", "income", None),
    ("Sales", "income", "Sales Accounts"),
    ("Sales Returns", "income", "Sales Accounts"),
    # Expenses
    ("Purchase Accounts", "expense", None),
    ("Purchases", "expense", "Purchase Accounts"),
    ("Purchase Returns", "expense", "Purchase Accounts"),
    ("Cost of Goods Sold", "expense", "Purchase Accounts"),
    ("Direct Expenses", "expense", None),
    ("Indirect Expenses", "expense", None),
    ("Round-Off", "expense", None),
]

INVOICE_SERIES_DEFAULTS = [
    ("Domestic", "INV", "domestic"),
    ("Export", "EXP", "export"),
    ("SEZ with payment", "SEZ-WP", "sez-wp"),
    ("SEZ without payment", "SEZ-WOP", "sez-wop"),
    ("Bill of supply", "BOS", "bos"),
]

# === DDL — copied verbatim from index.html (Phase 1 + 2A..8A + H1/H8, schema v12:
# audit_log.hash_version, invoice_lines.cess, purchase_lines.cess) ===
# Including the v6→v12 ALTER TABLE additions inlined into CREATE TABLE so a
# fresh DB lands at v12 without needing to run the migration walker.

DDL = r"""
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  parent_id INTEGER,
  type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')),
  system_flag INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_accounts_name ON accounts(name);
CREATE INDEX IF NOT EXISTS idx_accounts_parent ON accounts(parent_id);

CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  posted_at TEXT NOT NULL,
  voucher_type TEXT NOT NULL,
  voucher_ref TEXT,
  narration TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL,
  reversed_by_id INTEGER,
  is_amendment INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_posted ON entries(posted_at);
CREATE INDEX IF NOT EXISTS idx_entries_voucher ON entries(voucher_type);

CREATE TABLE IF NOT EXISTS entry_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL REFERENCES entries(id),
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  debit INTEGER NOT NULL DEFAULT 0,
  credit INTEGER NOT NULL DEFAULT 0,
  account_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_lines_entry ON entry_lines(entry_id);
CREATE INDEX IF NOT EXISTS idx_lines_account ON entry_lines(account_id);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  ref TEXT,
  origin TEXT,
  payload TEXT,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  signature TEXT,
  hash_version INTEGER
);

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  gstin TEXT,
  pan TEXT,
  state TEXT,
  email TEXT,
  phone TEXT,
  address TEXT,
  opening_balance INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_gstin ON customers(gstin);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  hsn_sac TEXT,
  is_service INTEGER DEFAULT 0,
  unit TEXT,
  default_rate INTEGER,
  default_tax_rate REAL,
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  enable_inventory INTEGER DEFAULT 0,
  valuation_method TEXT DEFAULT 'wac',
  track_batches INTEGER DEFAULT 0,
  reorder_level INTEGER DEFAULT 0,
  preferred_vendor_id INTEGER,
  opening_stock_qty INTEGER DEFAULT 0,
  opening_stock_value INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_number TEXT NOT NULL UNIQUE,
  series TEXT NOT NULL DEFAULT 'default',
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  invoice_date TEXT NOT NULL,
  due_date TEXT,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
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
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  company_snapshot TEXT,
  customer_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);

CREATE TABLE IF NOT EXISTS invoice_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER REFERENCES items(id),
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,
  quantity REAL NOT NULL DEFAULT 1,
  unit TEXT,
  rate INTEGER NOT NULL,
  discount INTEGER DEFAULT 0,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  cess INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice ON invoice_lines(invoice_id);

CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_number TEXT NOT NULL UNIQUE,
  payment_date TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id),
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL DEFAULT 0,
  payment_mode TEXT,
  reference TEXT,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  customer_snapshot TEXT,
  bank_account_snapshot TEXT,
  created_at TEXT NOT NULL,
  vendor_id INTEGER,
  payment_direction TEXT DEFAULT 'in',
  tds_amount INTEGER DEFAULT 0,
  tds_section TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_customer ON payments(customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);

CREATE TABLE IF NOT EXISTS payment_allocations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id INTEGER NOT NULL REFERENCES payments(id),
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  amount INTEGER NOT NULL DEFAULT 0,
  invoice_number_snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_alloc_payment ON payment_allocations(payment_id);
CREATE INDEX IF NOT EXISTS idx_alloc_invoice ON payment_allocations(invoice_id);

CREATE TABLE IF NOT EXISTS advances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advance_number TEXT NOT NULL UNIQUE,
  advance_date TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  nature_of_supply TEXT,
  payment_mode TEXT,
  reference TEXT,
  notes TEXT,
  adjusted_amount INTEGER NOT NULL DEFAULT 0,
  remaining_balance INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  ledger_entry_id INTEGER REFERENCES entries(id),
  customer_snapshot TEXT,
  bank_account_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advances_customer ON advances(customer_id);
CREATE INDEX IF NOT EXISTS idx_advances_date ON advances(advance_date);
CREATE INDEX IF NOT EXISTS idx_advances_status ON advances(status);

CREATE TABLE IF NOT EXISTS advance_adjustments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  advance_id INTEGER NOT NULL REFERENCES advances(id),
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  amount INTEGER NOT NULL,
  ledger_entry_id INTEGER REFERENCES entries(id),
  advance_number_snapshot TEXT,
  invoice_number_snapshot TEXT,
  adjusted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advadj_advance ON advance_adjustments(advance_id);
CREATE INDEX IF NOT EXISTS idx_advadj_invoice ON advance_adjustments(invoice_id);

CREATE TABLE IF NOT EXISTS invoice_series (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  suffix TEXT,
  starting_number INTEGER NOT NULL DEFAULT 1,
  reset_on_fy INTEGER DEFAULT 1,
  default_for TEXT,
  archived INTEGER DEFAULT 0,
  system_flag INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoice_series_default ON invoice_series(default_for);

CREATE TABLE IF NOT EXISTS vendors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  gstin TEXT,
  pan TEXT,
  state TEXT,
  email TEXT,
  phone TEXT,
  address TEXT,
  rcm_applicable INTEGER DEFAULT 0,
  tds_section TEXT,
  opening_balance INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vendors_name ON vendors(name);
CREATE INDEX IF NOT EXISTS idx_vendors_gstin ON vendors(gstin);

CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_number TEXT NOT NULL,
  internal_ref TEXT NOT NULL UNIQUE,
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  bill_date TEXT NOT NULL,
  due_date TEXT,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  is_import INTEGER DEFAULT 0,
  reverse_charge INTEGER DEFAULT 0,
  itc_eligible INTEGER DEFAULT 1,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  company_snapshot TEXT,
  vendor_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(bill_date);
CREATE INDEX IF NOT EXISTS idx_purchases_vendor ON purchases(vendor_id);

CREATE TABLE IF NOT EXISTS purchase_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id INTEGER NOT NULL REFERENCES purchases(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER REFERENCES items(id),
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,
  quantity REAL NOT NULL DEFAULT 1,
  unit TEXT,
  rate INTEGER NOT NULL,
  discount INTEGER DEFAULT 0,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  itc_eligible INTEGER DEFAULT 1,
  total INTEGER NOT NULL,
  cess INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_purchase_lines_purchase ON purchase_lines(purchase_id);

CREATE TABLE IF NOT EXISTS credit_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cn_number TEXT NOT NULL UNIQUE,
  cn_date TEXT NOT NULL,
  original_invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  original_invoice_number TEXT NOT NULL,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  reason TEXT,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  company_snapshot TEXT,
  customer_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cn_date ON credit_notes(cn_date);
CREATE INDEX IF NOT EXISTS idx_cn_invoice ON credit_notes(original_invoice_id);

CREATE TABLE IF NOT EXISTS credit_note_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cn_id INTEGER NOT NULL REFERENCES credit_notes(id),
  line_no INTEGER NOT NULL,
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,
  quantity REAL NOT NULL DEFAULT 1,
  rate INTEGER NOT NULL,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS debit_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dn_number TEXT NOT NULL UNIQUE,
  dn_date TEXT NOT NULL,
  original_purchase_id INTEGER NOT NULL REFERENCES purchases(id),
  original_bill_number TEXT NOT NULL,
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  reason TEXT,
  place_of_supply TEXT,
  place_of_supply_name TEXT,
  subtotal INTEGER NOT NULL DEFAULT 0,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  ledger_entry_id INTEGER REFERENCES entries(id),
  company_snapshot TEXT,
  vendor_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dn_date ON debit_notes(dn_date);
CREATE INDEX IF NOT EXISTS idx_dn_purchase ON debit_notes(original_purchase_id);

CREATE TABLE IF NOT EXISTS debit_note_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dn_id INTEGER NOT NULL REFERENCES debit_notes(id),
  line_no INTEGER NOT NULL,
  description TEXT NOT NULL,
  hsn_sac TEXT,
  hsn_description TEXT,
  quantity REAL NOT NULL DEFAULT 1,
  rate INTEGER NOT NULL,
  taxable INTEGER NOT NULL,
  tax_rate REAL NOT NULL,
  rate_id TEXT,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tds_deductions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id INTEGER REFERENCES payments(id),
  vendor_id INTEGER REFERENCES vendors(id),
  section TEXT NOT NULL,
  rate REAL NOT NULL,
  taxable_amount INTEGER NOT NULL,
  tds_amount INTEGER NOT NULL,
  payment_date TEXT NOT NULL,
  vendor_pan TEXT,
  vendor_name_snapshot TEXT,
  ledger_entry_id INTEGER REFERENCES entries(id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tds_vendor ON tds_deductions(vendor_id);
CREATE INDEX IF NOT EXISTS idx_tds_section ON tds_deductions(section);

CREATE TABLE IF NOT EXISTS tcs_collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER REFERENCES invoices(id),
  customer_id INTEGER REFERENCES customers(id),
  section TEXT NOT NULL,
  rate REAL NOT NULL,
  taxable_amount INTEGER NOT NULL,
  tcs_amount INTEGER NOT NULL,
  invoice_date TEXT NOT NULL,
  customer_pan TEXT,
  customer_name_snapshot TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tcs_customer ON tcs_collections(customer_id);

CREATE TABLE IF NOT EXISTS period_locks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  return_type TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  filed_at TEXT NOT NULL,
  filed_by TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_period_locks_type ON period_locks(return_type);

CREATE TABLE IF NOT EXISTS fy_closings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fy_start TEXT NOT NULL,
  fy_end TEXT NOT NULL,
  closed_at TEXT NOT NULL,
  closing_entry_id INTEGER REFERENCES entries(id),
  net_profit INTEGER NOT NULL DEFAULT 0,
  carried_forward INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fy_closings ON fy_closings(fy_start);

CREATE TABLE IF NOT EXISTS godowns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  address TEXT,
  state TEXT,
  is_default INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  godown_id INTEGER NOT NULL REFERENCES godowns(id),
  batch_no TEXT,
  mfg_date TEXT,
  expiry_date TEXT,
  source_purchase_id INTEGER REFERENCES purchases(id),
  source_purchase_line_id INTEGER REFERENCES purchase_lines(id),
  qty_in INTEGER NOT NULL DEFAULT 0,
  qty_out INTEGER NOT NULL DEFAULT 0,
  qty_balance INTEGER NOT NULL DEFAULT 0,
  rate INTEGER NOT NULL,
  value_in INTEGER NOT NULL DEFAULT 0,
  value_out INTEGER NOT NULL DEFAULT 0,
  value_balance INTEGER NOT NULL DEFAULT 0,
  is_wac_synthetic INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_batches_item ON batches(item_id);
CREATE INDEX IF NOT EXISTS idx_batches_godown ON batches(godown_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);

CREATE TABLE IF NOT EXISTS stock_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  godown_id INTEGER NOT NULL REFERENCES godowns(id),
  batch_id INTEGER REFERENCES batches(id),
  movement_type TEXT NOT NULL,
  voucher_type TEXT NOT NULL,
  voucher_id INTEGER,
  voucher_ref TEXT,
  posted_at TEXT NOT NULL,
  qty INTEGER NOT NULL,
  rate INTEGER NOT NULL,
  value INTEGER NOT NULL,
  item_name_snapshot TEXT,
  unit_snapshot TEXT,
  godown_name_snapshot TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_mov_item ON stock_movements(item_id);
CREATE INDEX IF NOT EXISTS idx_stock_mov_date ON stock_movements(posted_at);
CREATE INDEX IF NOT EXISTS idx_stock_mov_voucher ON stock_movements(voucher_type, voucher_id);

CREATE TABLE IF NOT EXISTS delivery_challans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  challan_number TEXT NOT NULL UNIQUE,
  challan_date TEXT NOT NULL,
  challan_type TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id),
  vendor_id INTEGER REFERENCES vendors(id),
  godown_id INTEGER NOT NULL REFERENCES godowns(id),
  destination TEXT,
  vehicle_no TEXT,
  transporter TEXT,
  reason TEXT,
  is_returnable INTEGER DEFAULT 0,
  expected_return_date TEXT,
  linked_invoice_id INTEGER REFERENCES invoices(id),
  status TEXT NOT NULL DEFAULT 'open',
  company_snapshot TEXT,
  party_snapshot TEXT,
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dc_date ON delivery_challans(challan_date);

CREATE TABLE IF NOT EXISTS delivery_challan_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  challan_id INTEGER NOT NULL REFERENCES delivery_challans(id),
  line_no INTEGER NOT NULL,
  item_id INTEGER NOT NULL REFERENCES items(id),
  description TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit TEXT,
  batch_id INTEGER REFERENCES batches(id),
  rate INTEGER,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS eway_bills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ewb_number TEXT,
  ewb_date TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id INTEGER NOT NULL,
  source_ref TEXT NOT NULL,
  transporter_name TEXT,
  transporter_id TEXT,
  vehicle_no TEXT,
  vehicle_type TEXT,
  mode TEXT,
  distance_km INTEGER,
  reason_code TEXT,
  supplier_snapshot TEXT,
  recipient_snapshot TEXT,
  goods_snapshot TEXT,
  taxable_value INTEGER NOT NULL,
  cgst INTEGER NOT NULL DEFAULT 0,
  sgst INTEGER NOT NULL DEFAULT 0,
  igst INTEGER NOT NULL DEFAULT 0,
  cess INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ewb_date ON eway_bills(ewb_date);
CREATE INDEX IF NOT EXISTS idx_ewb_number ON eway_bills(ewb_number);

CREATE TABLE IF NOT EXISTS stock_transfers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  transfer_number TEXT NOT NULL UNIQUE,
  transfer_date TEXT NOT NULL,
  direction TEXT NOT NULL,
  from_gstin TEXT NOT NULL,
  from_state TEXT NOT NULL,
  to_gstin TEXT NOT NULL,
  to_state TEXT NOT NULL,
  from_godown_id INTEGER REFERENCES godowns(id),
  to_godown_id INTEGER REFERENCES godowns(id),
  linked_invoice_id INTEGER REFERENCES invoices(id),
  linked_purchase_id INTEGER REFERENCES purchases(id),
  ewb_id INTEGER REFERENCES eway_bills(id),
  total_value INTEGER NOT NULL,
  payload_snapshot TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_st_date ON stock_transfers(transfer_date);

CREATE TABLE IF NOT EXISTS annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  target_ref TEXT,
  note_type TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  ca_name TEXT,
  ca_firm TEXT,
  ca_membership TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_annotations_target ON annotations(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_annotations_status ON annotations(status);
CREATE INDEX IF NOT EXISTS idx_annotations_created_at ON annotations(created_at);

CREATE TABLE IF NOT EXISTS review_markers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id INTEGER NOT NULL REFERENCES entries(id),
  reviewed_at TEXT NOT NULL,
  reviewed_by TEXT NOT NULL,
  ca_membership TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_markers_entry ON review_markers(entry_id);

CREATE TABLE IF NOT EXISTS bank_reconciliations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bank_account_id INTEGER NOT NULL REFERENCES accounts(id),
  reconciled_through_date TEXT NOT NULL,
  closing_balance_per_book INTEGER NOT NULL,
  closing_balance_per_statement INTEGER NOT NULL,
  uncleared_debits INTEGER DEFAULT 0,
  uncleared_credits INTEGER DEFAULT 0,
  difference INTEGER DEFAULT 0,
  matched_entry_lines TEXT,
  notes TEXT,
  reconciled_at TEXT NOT NULL,
  reconciled_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bankrec_account ON bank_reconciliations(bank_account_id);
"""


# === Helpers ===

def canonical_json(obj: Any) -> str:
    """Match index.html canonicalJson — recursively sorted keys, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def audit_preimage_v2(prev_hash: str, ts: str, actor: str, action: str,
                      ref: Optional[str], origin: str, payload_str: str) -> str:
    """Mirror index.html auditPreimageV2 — the v2 all-field tamper-evident hash preimage.
    v1 (legacy) hashed only prev+origin+payload; v2 covers every semantic field so ts/actor/
    action/ref can't be edited without breaking the chain. canonical_json provably matches the
    app's canonicalJson (sorted keys, no spaces), so this preimage is byte-identical."""
    return canonical_json({
        "v": 2, "prev": prev_hash, "ts": ts, "actor": actor,
        "action": action, "ref": ref if ref is not None else None,
        "origin": origin, "payload": payload_str,
    })


def sha256_bytes_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


def iso_now(dt: Optional[datetime] = None) -> str:
    """Match JS toISOString() — milliseconds + 'Z'."""
    d = (dt or FIXED_NOW).astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def fy_label_from_date(d: datetime) -> str:
    """e.g. 2024-04-01 -> '24-25'"""
    y = d.year - 1 if d.month < 4 else d.year
    return f"{str(y)[-2:]}-{str(y + 1)[-2:]}"


def b64url_to_int(s: str) -> int:
    import base64
    pad = "=" * (-len(s) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(s + pad), "big")


def jwk_from_public_key(pub_key: ec.EllipticCurvePublicKey) -> Dict[str, str]:
    """Export an EC P-256 public key as a JWK matching crypto.subtle.exportKey('jwk')."""
    nums = pub_key.public_numbers()
    x_bytes = nums.x.to_bytes(32, "big")
    y_bytes = nums.y.to_bytes(32, "big")
    import base64
    def b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64u(x_bytes),
        "y": b64u(y_bytes),
        "ext": True,
        "key_ops": ["verify"],
    }


def sign_hash_hex(priv_key: ec.EllipticCurvePrivateKey, hash_hex: str) -> str:
    """
    Match index.html signHashHex:
        crypto.subtle.sign({name:'ECDSA', hash:'SHA-256'}, privKey, hexToBytes(hashHex))
    Web Crypto signs the *bytes* (no extra hashing — wait — actually it DOES hash with
    SHA-256 because we passed hash:'SHA-256'). The "data" is hexToBytes(hashHex).
    Web Crypto returns raw r||s (64 bytes for P-256), then b64encode.
    """
    msg = hex_to_bytes(hash_hex)
    # RFC 6979 deterministic ECDSA — derive the nonce k from (private key + message) instead of
    # randomness, so re-running the generator produces byte-identical .khata files. The signatures
    # are ordinary valid ECDSA and verify identically under Web Crypto (verification is k-agnostic).
    der_sig = priv_key.sign(msg, ec.ECDSA(hashes.SHA256(), deterministic_signing=True))
    r, s = asym_utils.decode_dss_signature(der_sig)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return b64encode(raw).decode("ascii")


# === Builder ===

@dataclass
class Customer:
    id: int
    name: str
    gstin: Optional[str]
    pan: Optional[str]
    state: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]


@dataclass
class Vendor:
    id: int
    name: str
    gstin: Optional[str]
    pan: Optional[str]
    state: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    rcm_applicable: int
    tds_section: Optional[str]


@dataclass
class Item:
    id: int
    name: str
    hsn_sac: str
    is_service: int
    unit: str
    default_rate: int  # paise
    default_tax_rate: float  # 0.18 etc
    enable_inventory: int
    valuation_method: str  # 'wac' | 'fifo'
    track_batches: int


class KhataBuilder:
    def __init__(self, *, company: Dict[str, Any], ui_tier: str, fy_start: str, seed: int, clock_start: datetime):
        self.company = company
        self.ui_tier = ui_tier
        self.fy_start = fy_start
        self.rng = random.Random(seed)

        # Deterministic clock — every audit / created_at call advances by a fixed delta
        # so the file is reproducible byte-for-byte.
        self._clock = clock_start
        self._clock_step = timedelta(milliseconds=1)

        self.workspace_id = self._deterministic_uuid(seed)

        # ECDSA P-256 keypair from a deterministic seed (so files are reproducible).
        # We derive a 32-byte secret from SHA-256(seed_str) and load it as a private value.
        seed_hash = hashlib.sha256(f"khata-sample-{seed}".encode()).digest()
        # Reduce mod curve order to get a valid private scalar
        from cryptography.hazmat.backends import default_backend
        n = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
        k = (int.from_bytes(seed_hash, "big") % (n - 1)) + 1
        self.priv_key = ec.derive_private_key(k, ec.SECP256R1(), default_backend())
        self.pub_key = self.priv_key.public_key()
        self.public_jwk = jwk_from_public_key(self.pub_key)

        # In-memory SQLite
        self.conn = sqlite3.connect(":memory:")
        self.conn.isolation_level = None  # autocommit OFF via explicit BEGIN/COMMIT
        self.cur = self.conn.cursor()

        # Bookkeeping
        self.account_id_by_name: Dict[str, int] = {}
        self.customers: List[Customer] = []
        self.vendors: List[Vendor] = []
        self.items: List[Item] = []
        # Per-item running stock for inventory items: {item_id: {qty: int, value: int}}
        self.stock: Dict[int, Dict[str, int]] = {}
        # Invoice number counters per (series, fy)
        self._invoice_counter: Dict[Tuple[str, str], int] = {}
        self._purchase_counter: Dict[str, int] = {}
        self._payment_counter: Dict[str, int] = {}
        self._cn_counter: Dict[str, int] = {}
        self._dn_counter: Dict[str, int] = {}
        self._adv_counter: Dict[str, int] = {}

        self.created_at_iso = iso_now(clock_start)
        self.row_counts: Dict[str, int] = {}

    def _now(self) -> str:
        ts = iso_now(self._clock)
        self._clock += self._clock_step
        return ts

    def _deterministic_uuid(self, seed: int) -> str:
        # UUID v4-style but seeded — uses uuid.UUID with bytes
        b = hashlib.sha256(f"ws-{seed}".encode()).digest()[:16]
        # Set version 4 and variant bits
        b = b[:6] + bytes([(b[6] & 0x0F) | 0x40]) + b[7:8] + bytes([(b[8] & 0x3F) | 0x80]) + b[9:]
        return str(uuid.UUID(bytes=b))

    # ----- Schema + seed -----

    def create_db(self) -> None:
        self.cur.executescript(DDL)
        self.cur.execute(
            "INSERT OR REPLACE INTO meta (k, v) VALUES ('schemaVersion', ?)",
            (str(SCHEMA_VERSION),),
        )

    def seed_invoice_series(self) -> None:
        for name, prefix, default_for in INVOICE_SERIES_DEFAULTS:
            self.cur.execute(
                "INSERT OR IGNORE INTO invoice_series (name, prefix, starting_number, reset_on_fy, default_for, system_flag, created_at) VALUES (?, ?, 1, 1, ?, 1, ?)",
                (name, prefix, default_for, self._now()),
            )

    def seed_default_godown(self) -> None:
        self.cur.execute(
            "INSERT INTO godowns (name, address, state, is_default, created_at) VALUES ('Main', NULL, NULL, 1, ?)",
            (self._now(),),
        )

    def seed_coa(self) -> None:
        # Pass 1 — top-level
        for name, type_, parent in COA_SEED:
            if parent is not None:
                continue
            self.cur.execute(
                "INSERT INTO accounts (name, type, parent_id, system_flag) VALUES (?, ?, NULL, 1)",
                (name, type_),
            )
            self.account_id_by_name[name] = self.cur.lastrowid
        # Pass 2 — children
        for name, type_, parent in COA_SEED:
            if parent is None:
                continue
            pid = self.account_id_by_name.get(parent)
            self.cur.execute(
                "INSERT INTO accounts (name, type, parent_id, system_flag) VALUES (?, ?, ?, 1)",
                (name, type_, pid),
            )
            self.account_id_by_name[name] = self.cur.lastrowid
        # Auto-create a single Bank account child under "Bank Accounts" so we have
        # a non-cash bank account for receipts/payments.
        bank_parent = self.account_id_by_name["Bank Accounts"]
        self.cur.execute(
            "INSERT INTO accounts (name, type, parent_id, system_flag) VALUES ('HDFC Current A/c', 'asset', ?, 0)",
            (bank_parent,),
        )
        self.account_id_by_name["HDFC Current A/c"] = self.cur.lastrowid

    def get_or_create_rate_account(self, parent_name: str, rate_pct: float) -> int:
        """Mirror of getOrCreateRateAccount in index.html."""
        # Format the rate as the JS code does: integer-no-dot, else trimmed decimal
        if rate_pct == int(rate_pct):
            formatted = str(int(rate_pct))
        else:
            formatted = f"{rate_pct:.2f}".rstrip("0").rstrip(".")
        sub_name = f"{parent_name} @ {formatted}%"
        if sub_name in self.account_id_by_name:
            return self.account_id_by_name[sub_name]
        pid = self.account_id_by_name[parent_name]
        ptype_row = self.cur.execute(
            "SELECT type FROM accounts WHERE id = ?", (pid,)
        ).fetchone()
        ptype = ptype_row[0]
        self.cur.execute(
            "INSERT INTO accounts (name, parent_id, type, system_flag) VALUES (?, ?, ?, 2)",
            (sub_name, pid, ptype),
        )
        new_id = self.cur.lastrowid
        self.account_id_by_name[sub_name] = new_id
        return new_id

    def get_or_create_tds_payable_account(self, section: str) -> int:
        sub_name = f"TDS Payable - {section}"
        if sub_name in self.account_id_by_name:
            return self.account_id_by_name[sub_name]
        pid = self.account_id_by_name["TDS Payable"]
        self.cur.execute(
            "INSERT INTO accounts (name, parent_id, type, system_flag) VALUES (?, ?, 'liability', 2)",
            (sub_name, pid),
        )
        new_id = self.cur.lastrowid
        self.account_id_by_name[sub_name] = new_id
        return new_id

    def get_or_create_cess_account(self, name: str, type_: str) -> int:
        """Mirror of getOrCreateCessAccount — a single Cess Output / Cess Input / Cess RCM
        account under Duties & Taxes, created lazily the first time cess is posted (system_flag=1)."""
        if name in self.account_id_by_name:
            return self.account_id_by_name[name]
        pid = self.account_id_by_name["Duties & Taxes"]
        self.cur.execute(
            "INSERT INTO accounts (name, parent_id, type, system_flag) VALUES (?, ?, ?, 1)",
            (name, pid, type_),
        )
        new_id = self.cur.lastrowid
        self.account_id_by_name[name] = new_id
        return new_id

    # ----- Audit chain -----

    def get_audit_head(self) -> str:
        row = self.cur.execute(
            "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return GENESIS_PREV
        return row[0]

    def append_audit(self, *, actor: str, action: str, ref: Optional[str], payload: Dict[str, Any]) -> None:
        ts = self._now()
        origin = GENERATOR_ORIGIN
        prev_hash = self.get_audit_head()
        payload_str = canonical_json(payload or {})
        # v2 all-field hash (hash_version = 2), matching index.html appendAuditEntry.
        hash_hex = sha256_hex(audit_preimage_v2(prev_hash, ts, actor, action, ref, origin, payload_str))
        sig = sign_hash_hex(self.priv_key, hash_hex)
        self.cur.execute(
            "INSERT INTO audit_log (ts, actor, action, ref, origin, payload, prev_hash, hash, signature, hash_version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ts, actor, action, ref, origin, payload_str, prev_hash, hash_hex, sig, 2),
        )

    # ----- Posting engine -----

    def post_entry(self, *, voucher_type: str, voucher_ref: Optional[str], narration: Optional[str],
                   posted_at: str, lines: List[Dict[str, int]], actor: str = "owner") -> int:
        """Mirror of postEntry — inserts entries + entry_lines, freezes account_name, appends audit."""
        if len(lines) < 2:
            raise ValueError("At least 2 lines required")
        total_dr = sum(l.get("debit", 0) for l in lines)
        total_cr = sum(l.get("credit", 0) for l in lines)
        if total_dr != total_cr:
            raise ValueError(f"Unbalanced: Dr {total_dr} != Cr {total_cr} ({voucher_type} {voucher_ref})")
        if total_dr == 0:
            raise ValueError("Zero-amount entry")

        # Look up frozen names
        name_by_id: Dict[int, str] = {}
        for ln in lines:
            aid = ln["accountId"]
            if aid not in name_by_id:
                row = self.cur.execute("SELECT name FROM accounts WHERE id = ?", (aid,)).fetchone()
                name_by_id[aid] = row[0] if row else None

        created_at = self._now()
        self.cur.execute(
            "INSERT INTO entries (posted_at, voucher_type, voucher_ref, narration, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (posted_at, voucher_type, voucher_ref, narration, actor, created_at),
        )
        entry_id = self.cur.lastrowid
        for ln in lines:
            self.cur.execute(
                "INSERT INTO entry_lines (entry_id, account_id, debit, credit, account_name) VALUES (?,?,?,?,?)",
                (entry_id, ln["accountId"], ln.get("debit", 0), ln.get("credit", 0), name_by_id[ln["accountId"]]),
            )
        self.append_audit(
            actor=actor,
            action="entry.post",
            ref=f"entry:{entry_id}",
            payload={
                "entryId": entry_id,
                "voucherType": voucher_type,
                "voucherRef": voucher_ref,
                "postedAt": posted_at,
                "totalDr": total_dr,
                "lineCount": len(lines),
            },
        )
        return entry_id

    # ----- Tax computation (mirror of computeInvoiceTax) -----

    @staticmethod
    def compute_tax(company_state: str, customer_state: str, lines: List[Dict[str, Any]],
                    *, is_export: bool = False, is_sez: bool = False) -> Dict[str, int]:
        intra = (not is_export) and (not is_sez) and bool(company_state) and bool(customer_state) and (company_state == customer_state)
        subtotal = cgst = sgst = igst = 0
        for ln in lines:
            taxable = max(0, round(ln["taxable"]))
            ln["taxable"] = taxable
            rate = float(ln.get("tax_rate", 0))
            subtotal += taxable
            if is_export or is_sez:
                ln["cgst"] = ln["sgst"] = ln["igst"] = 0
            elif intra:
                half = round((taxable * rate) / 2)
                ln["cgst"] = half
                ln["sgst"] = half
                ln["igst"] = 0
                cgst += half
                sgst += half
            else:
                i = round(taxable * rate)
                ln["cgst"] = ln["sgst"] = 0
                ln["igst"] = i
                igst += i
            ln["total"] = taxable + ln["cgst"] + ln["sgst"] + ln["igst"]
        total = subtotal + cgst + sgst + igst
        return {"subtotal": subtotal, "cgst": cgst, "sgst": sgst, "igst": igst, "total": total, "intra": intra}

    # ----- Master record creation -----

    def add_customer(self, *, name: str, gstin: Optional[str], state: str,
                     email: Optional[str] = None, phone: Optional[str] = None,
                     address: Optional[str] = None) -> Customer:
        pan = gstin[2:12] if gstin and len(gstin) >= 12 else None
        self.cur.execute(
            "INSERT INTO customers (name, gstin, pan, state, email, phone, address, opening_balance, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, gstin, pan, state, email, phone, address, 0, self._now()),
        )
        c = Customer(self.cur.lastrowid, name, gstin, pan, state, email, phone, address)
        self.customers.append(c)
        self.append_audit(actor="owner", action="customer.create", ref=f"customer:{c.id}",
                          payload={"customerId": c.id, "name": name, "gstin": gstin, "state": state})
        return c

    def add_vendor(self, *, name: str, gstin: Optional[str], state: str,
                   email: Optional[str] = None, phone: Optional[str] = None,
                   address: Optional[str] = None, rcm_applicable: int = 0,
                   tds_section: Optional[str] = None) -> Vendor:
        pan = gstin[2:12] if gstin and len(gstin) >= 12 else None
        self.cur.execute(
            "INSERT INTO vendors (name, gstin, pan, state, email, phone, address, rcm_applicable, tds_section, opening_balance, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, gstin, pan, state, email, phone, address, rcm_applicable, tds_section, 0, self._now()),
        )
        v = Vendor(self.cur.lastrowid, name, gstin, pan, state, email, phone, address, rcm_applicable, tds_section)
        self.vendors.append(v)
        self.append_audit(actor="owner", action="vendor.create", ref=f"vendor:{v.id}",
                          payload={"vendorId": v.id, "name": name, "gstin": gstin, "state": state})
        return v

    def add_item(self, *, name: str, hsn_sac: str, is_service: int, unit: str,
                 default_rate: int, default_tax_rate: float,
                 enable_inventory: int = 0, valuation_method: str = "wac",
                 track_batches: int = 0) -> Item:
        self.cur.execute(
            "INSERT INTO items (name, hsn_sac, is_service, unit, default_rate, default_tax_rate, enable_inventory, valuation_method, track_batches, opening_stock_qty, opening_stock_value, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, hsn_sac, is_service, unit, default_rate, default_tax_rate,
             enable_inventory, valuation_method, track_batches, 0, 0, self._now()),
        )
        it = Item(self.cur.lastrowid, name, hsn_sac, is_service, unit,
                  default_rate, default_tax_rate, enable_inventory, valuation_method, track_batches)
        self.items.append(it)
        if enable_inventory:
            self.stock[it.id] = {"qty": 0, "value": 0}
        self.append_audit(actor="owner", action="item.create", ref=f"item:{it.id}",
                          payload={"itemId": it.id, "name": name, "hsn": hsn_sac, "isService": is_service})
        return it

    # ----- Numbering helpers -----

    def next_invoice_number(self, series_name: str, date_iso: str) -> str:
        prefix_map = {n: p for n, p, _ in INVOICE_SERIES_DEFAULTS}
        prefix = prefix_map.get(series_name, "INV")
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        fy = fy_label_from_date(d)
        key = (series_name, fy)
        n = self._invoice_counter.get(key, 0) + 1
        self._invoice_counter[key] = n
        return f"{prefix}/{fy}/{n:04d}"

    def next_purchase_ref(self, date_iso: str) -> str:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        fy = fy_label_from_date(d)
        n = self._purchase_counter.get(fy, 0) + 1
        self._purchase_counter[fy] = n
        return f"PUR/{fy}/{n:04d}"

    def next_payment_number(self, date_iso: str) -> str:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        fy = fy_label_from_date(d)
        n = self._payment_counter.get(fy, 0) + 1
        self._payment_counter[fy] = n
        return f"PAY/{fy}/{n:04d}"

    def next_cn_number(self, date_iso: str) -> str:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        fy = fy_label_from_date(d)
        n = self._cn_counter.get(fy, 0) + 1
        self._cn_counter[fy] = n
        return f"CN/{fy}/{n:04d}"

    def next_dn_number(self, date_iso: str) -> str:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        fy = fy_label_from_date(d)
        n = self._dn_counter.get(fy, 0) + 1
        self._dn_counter[fy] = n
        return f"DN/{fy}/{n:04d}"

    def next_advance_number(self, date_iso: str) -> str:
        d = datetime.strptime(date_iso, "%Y-%m-%d")
        fy = fy_label_from_date(d)
        n = self._adv_counter.get(fy, 0) + 1
        self._adv_counter[fy] = n
        return f"ARV/{fy}/{n:04d}"

    # ----- Invoice posting -----

    def _company_snapshot_json(self) -> str:
        return json.dumps(self.company)

    def _customer_snapshot_json(self, c: Customer) -> str:
        st = STATE_BY_ISO.get(c.state)
        return json.dumps({
            "name": c.name,
            "gstin": c.gstin,
            "pan": c.pan,
            "state": c.state,
            "stateName": st[2] if st else None,
            "gstinStateCode": st[1] if st else None,
            "email": c.email,
            "phone": c.phone,
            "address": c.address,
        })

    def _vendor_snapshot_json(self, v: Vendor) -> str:
        st = STATE_BY_ISO.get(v.state)
        return json.dumps({
            "name": v.name,
            "gstin": v.gstin,
            "pan": v.pan,
            "state": v.state,
            "stateName": st[2] if st else None,
            "gstinStateCode": st[1] if st else None,
            "email": v.email,
            "phone": v.phone,
            "address": v.address,
        })

    def post_invoice(self, *, customer: Customer, date_iso: str, line_specs: List[Dict[str, Any]],
                     series: str = "Domestic", notes: Optional[str] = None) -> int:
        """
        line_specs: list of {item, quantity, rate (paise per unit, optional - falls back to default), description (optional)}
        """
        company_state = self.company["state"]
        # Build computed lines
        lines: List[Dict[str, Any]] = []
        for i, spec in enumerate(line_specs):
            it: Item = spec["item"]
            qty = spec["quantity"]
            rate = spec.get("rate", it.default_rate)
            taxable = qty * rate
            tax_rate = it.default_tax_rate
            # rate_id from forensic table
            rate_pct = round(tax_rate * 100)
            rate_id = f"gst-{int(rate_pct)}" if rate_pct > 0 else "gst-0"
            if rate_pct == 0:
                rate_id = "gst-0"
            elif rate_pct == 12:
                rate_id = "gst-12"
            elif rate_pct == 18:
                rate_id = "gst-18"
            elif rate_pct == 5:
                rate_id = "gst-5"
            elif rate_pct == 28:
                rate_id = "gst-28"
            lines.append({
                "line_no": i + 1,
                "item_id": it.id,
                "description": spec.get("description") or it.name,
                "hsn_sac": it.hsn_sac,
                "hsn_description": (ALL_HSN[it.hsn_sac][0] if it.hsn_sac in ALL_HSN else it.name),
                "quantity": qty,
                "unit": it.unit,
                "rate": rate,
                "discount": 0,
                "taxable": taxable,
                "tax_rate": tax_rate,
                "rate_id": rate_id,
                "cess": int(spec.get("cess", 0) or 0),
            })

        totals = self.compute_tax(company_state, customer.state, lines)
        # Compensation cess rides on top of the invoice; invoice.total INCLUDES it (mirrors the app),
        # so Dr Sundry Debtors below stays balanced against Sales + GST + Cess Output.
        total_cess = sum(ln.get("cess", 0) for ln in lines)
        invoice_total = totals["total"] + total_cess
        invoice_number = self.next_invoice_number(series, date_iso)
        st = STATE_BY_ISO.get(customer.state)
        place_of_supply_name = st[2] if st else None

        company_snapshot = self._company_snapshot_json()
        customer_snapshot = self._customer_snapshot_json(customer)

        self.cur.execute(
            "INSERT INTO invoices (invoice_number, series, customer_id, invoice_date, place_of_supply, place_of_supply_name, subtotal, cgst, sgst, igst, cess, total, notes, status, company_snapshot, customer_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (invoice_number, series, customer.id, date_iso, customer.state, place_of_supply_name,
             totals["subtotal"], totals["cgst"], totals["sgst"], totals["igst"], total_cess, invoice_total,
             notes, "posted", company_snapshot, customer_snapshot, self._now()),
        )
        invoice_id = self.cur.lastrowid

        for ln in lines:
            self.cur.execute(
                "INSERT INTO invoice_lines (invoice_id, line_no, item_id, description, hsn_sac, hsn_description, quantity, unit, rate, discount, taxable, tax_rate, rate_id, cgst, sgst, igst, total, cess) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (invoice_id, ln["line_no"], ln["item_id"], ln["description"], ln["hsn_sac"],
                 ln["hsn_description"], ln["quantity"], ln["unit"], ln["rate"], ln["discount"],
                 ln["taxable"], ln["tax_rate"], ln["rate_id"], ln["cgst"], ln["sgst"], ln["igst"], ln["total"], ln["cess"]),
            )

        # Post to ledger via the bridge
        posting_lines = [
            {"accountId": self.account_id_by_name["Sundry Debtors"], "debit": invoice_total, "credit": 0},
            {"accountId": self.account_id_by_name["Sales"], "debit": 0, "credit": totals["subtotal"]},
        ]
        # Group by tax rate
        by_rate: Dict[float, Dict[str, int]] = {}
        for ln in lines:
            r = ln["tax_rate"]
            g = by_rate.setdefault(r, {"cgst": 0, "sgst": 0, "igst": 0})
            g["cgst"] += ln["cgst"]
            g["sgst"] += ln["sgst"]
            g["igst"] += ln["igst"]
        for rate, g in by_rate.items():
            rate_pct_full = rate * 100
            if g["cgst"] > 0:
                aid = self.get_or_create_rate_account("CGST Output", rate_pct_full / 2)
                posting_lines.append({"accountId": aid, "debit": 0, "credit": g["cgst"]})
            if g["sgst"] > 0:
                aid = self.get_or_create_rate_account("SGST Output", rate_pct_full / 2)
                posting_lines.append({"accountId": aid, "debit": 0, "credit": g["sgst"]})
            if g["igst"] > 0:
                aid = self.get_or_create_rate_account("IGST Output", rate_pct_full)
                posting_lines.append({"accountId": aid, "debit": 0, "credit": g["igst"]})

        # H8 — compensation cess leg (Cr Cess Output). invoice_total already includes it.
        if total_cess > 0:
            posting_lines.append({"accountId": self.get_or_create_cess_account("Cess Output", "liability"), "debit": 0, "credit": total_cess})

        entry_id = self.post_entry(
            voucher_type="sales",
            voucher_ref=invoice_number,
            narration=f"Invoice {invoice_number} to {customer.name}",
            posted_at=date_iso,
            lines=posting_lines,
        )
        self.cur.execute("UPDATE invoices SET ledger_entry_id = ? WHERE id = ?", (entry_id, invoice_id))

        # Stock effect for goods items
        for spec in line_specs:
            it: Item = spec["item"]
            if not it.enable_inventory:
                continue
            stock = self.stock.setdefault(it.id, {"qty": 0, "value": 0})
            qty = spec["quantity"]
            if stock["qty"] < qty:
                # Skip stock posting if insufficient — generator should ensure purchases happen first.
                continue
            avg_rate = stock["value"] // stock["qty"] if stock["qty"] > 0 else 0
            cogs_value = avg_rate * qty
            stock["qty"] -= qty
            stock["value"] -= cogs_value
            # Stock movement row
            self.cur.execute(
                "INSERT INTO stock_movements (item_id, godown_id, batch_id, movement_type, voucher_type, voucher_id, voucher_ref, posted_at, qty, rate, value, item_name_snapshot, unit_snapshot, godown_name_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (it.id, 1, None, "out", "invoice", invoice_id, invoice_number, date_iso,
                 -qty, avg_rate, -cogs_value, it.name, it.unit, "Main", self._now()),
            )
            # COGS posting: Dr COGS / Cr Stock-in-Hand
            if cogs_value > 0:
                self.post_entry(
                    voucher_type="journal",
                    voucher_ref=f"COGS:{invoice_number}",
                    narration=f"COGS for {invoice_number} ({it.name} x{qty})",
                    posted_at=date_iso,
                    lines=[
                        {"accountId": self.account_id_by_name["Cost of Goods Sold"], "debit": cogs_value, "credit": 0},
                        {"accountId": self.account_id_by_name["Stock-in-Hand"], "debit": 0, "credit": cogs_value},
                    ],
                )

        return invoice_id

    # ----- Purchase posting -----

    def post_purchase(self, *, vendor: Vendor, bill_number: str, date_iso: str,
                      line_specs: List[Dict[str, Any]], reverse_charge: int = 0,
                      itc_eligible: int = 1) -> int:
        company_state = self.company["state"]
        lines: List[Dict[str, Any]] = []
        for i, spec in enumerate(line_specs):
            it: Item = spec["item"]
            qty = spec["quantity"]
            rate = spec["rate"]
            taxable = qty * rate
            tax_rate = it.default_tax_rate
            rate_pct = round(tax_rate * 100)
            rate_id = f"gst-{int(rate_pct)}" if rate_pct in (0, 5, 12, 18, 28) else "gst-18"
            lines.append({
                "line_no": i + 1,
                "item_id": it.id,
                "description": spec.get("description") or it.name,
                "hsn_sac": it.hsn_sac,
                "hsn_description": (ALL_HSN[it.hsn_sac][0] if it.hsn_sac in ALL_HSN else it.name),
                "quantity": qty,
                "unit": it.unit,
                "rate": rate,
                "discount": 0,
                "taxable": taxable,
                "tax_rate": tax_rate,
                "rate_id": rate_id,
                "cess": int(spec.get("cess", 0) or 0),
            })

        totals = self.compute_tax(company_state, vendor.state, lines)
        # Cess on purchases (e.g. coal): purchase.total INCLUDES it; the Dr Cess Input leg below
        # claims it as ITC (or Cess RCM Input/Output, net 0, under reverse charge).
        total_cess = sum(ln.get("cess", 0) for ln in lines)
        purchase_total = totals["total"] + total_cess
        internal_ref = self.next_purchase_ref(date_iso)
        st = STATE_BY_ISO.get(vendor.state)
        place_of_supply_name = st[2] if st else None

        self.cur.execute(
            "INSERT INTO purchases (bill_number, internal_ref, vendor_id, bill_date, place_of_supply, place_of_supply_name, reverse_charge, itc_eligible, subtotal, cgst, sgst, igst, cess, total, notes, status, company_snapshot, vendor_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bill_number, internal_ref, vendor.id, date_iso, vendor.state, place_of_supply_name,
             reverse_charge, itc_eligible, totals["subtotal"], totals["cgst"], totals["sgst"],
             totals["igst"], total_cess, purchase_total, None, "posted",
             self._company_snapshot_json(), self._vendor_snapshot_json(vendor), self._now()),
        )
        purchase_id = self.cur.lastrowid

        for ln in lines:
            self.cur.execute(
                "INSERT INTO purchase_lines (purchase_id, line_no, item_id, description, hsn_sac, hsn_description, quantity, unit, rate, discount, taxable, tax_rate, rate_id, cgst, sgst, igst, itc_eligible, total, cess) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (purchase_id, ln["line_no"], ln["item_id"], ln["description"], ln["hsn_sac"],
                 ln["hsn_description"], ln["quantity"], ln["unit"], ln["rate"], ln["discount"],
                 ln["taxable"], ln["tax_rate"], ln["rate_id"], ln["cgst"], ln["sgst"], ln["igst"],
                 itc_eligible, ln["total"], ln["cess"]),
            )

        # Ledger posting (mirror of postPurchaseToLedger)
        posting_lines = [
            {"accountId": self.account_id_by_name["Purchases"], "debit": totals["subtotal"], "credit": 0},
        ]
        by_rate: Dict[float, Dict[str, int]] = {}
        for ln in lines:
            r = ln["tax_rate"]
            g = by_rate.setdefault(r, {"cgst": 0, "sgst": 0, "igst": 0})
            g["cgst"] += ln["cgst"]
            g["sgst"] += ln["sgst"]
            g["igst"] += ln["igst"]

        if reverse_charge:
            for rate, g in by_rate.items():
                rate_pct_full = rate * 100
                tot_tax = g["cgst"] + g["sgst"] + g["igst"]
                if tot_tax > 0:
                    posting_lines.append({"accountId": self.get_or_create_rate_account("GST RCM Input", rate_pct_full), "debit": tot_tax, "credit": 0})
                    posting_lines.append({"accountId": self.get_or_create_rate_account("GST RCM Output", rate_pct_full), "debit": 0, "credit": tot_tax})
            # Cess under RCM: Dr Cess RCM Input + Cr Cess RCM Output (net 0; input claimable).
            if total_cess > 0:
                posting_lines.append({"accountId": self.get_or_create_cess_account("Cess RCM Input", "asset"), "debit": total_cess, "credit": 0})
                posting_lines.append({"accountId": self.get_or_create_cess_account("Cess RCM Output", "liability"), "debit": 0, "credit": total_cess})
            posting_lines.append({"accountId": self.account_id_by_name["Sundry Creditors"], "debit": 0, "credit": totals["subtotal"]})
        else:
            for rate, g in by_rate.items():
                rate_pct_full = rate * 100
                if g["cgst"] > 0:
                    posting_lines.append({"accountId": self.get_or_create_rate_account("CGST Input", rate_pct_full / 2), "debit": g["cgst"], "credit": 0})
                if g["sgst"] > 0:
                    posting_lines.append({"accountId": self.get_or_create_rate_account("SGST Input", rate_pct_full / 2), "debit": g["sgst"], "credit": 0})
                if g["igst"] > 0:
                    posting_lines.append({"accountId": self.get_or_create_rate_account("IGST Input", rate_pct_full), "debit": g["igst"], "credit": 0})
            # Compensation cess: Dr Cess Input (claimable ITC); Sundry Creditors below includes it.
            if total_cess > 0:
                posting_lines.append({"accountId": self.get_or_create_cess_account("Cess Input", "asset"), "debit": total_cess, "credit": 0})
            posting_lines.append({"accountId": self.account_id_by_name["Sundry Creditors"], "debit": 0, "credit": purchase_total})

        entry_id = self.post_entry(
            voucher_type="purchase",
            voucher_ref=internal_ref,
            narration=f"Purchase {internal_ref} (vendor bill {bill_number}) from {vendor.name}" + (" [RCM]" if reverse_charge else ""),
            posted_at=date_iso,
            lines=posting_lines,
        )
        self.cur.execute("UPDATE purchases SET ledger_entry_id = ? WHERE id = ?", (entry_id, purchase_id))

        # Stock effect for goods items: increment running stock + WAC value
        for spec in line_specs:
            it: Item = spec["item"]
            if not it.enable_inventory:
                continue
            qty = spec["quantity"]
            rate = spec["rate"]
            stock = self.stock.setdefault(it.id, {"qty": 0, "value": 0})
            stock["qty"] += qty
            stock["value"] += qty * rate
            self.cur.execute(
                "INSERT INTO stock_movements (item_id, godown_id, batch_id, movement_type, voucher_type, voucher_id, voucher_ref, posted_at, qty, rate, value, item_name_snapshot, unit_snapshot, godown_name_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (it.id, 1, None, "in", "purchase", purchase_id, internal_ref, date_iso,
                 qty, rate, qty * rate, it.name, it.unit, "Main", self._now()),
            )
            # Inventory value posting: Dr Stock-in-Hand / Cr Purchases (for the goods value)
            self.post_entry(
                voucher_type="journal",
                voucher_ref=f"STK-IN:{internal_ref}",
                narration=f"Stock inward from {internal_ref} ({it.name} x{qty})",
                posted_at=date_iso,
                lines=[
                    {"accountId": self.account_id_by_name["Stock-in-Hand"], "debit": qty * rate, "credit": 0},
                    {"accountId": self.account_id_by_name["Purchases"], "debit": 0, "credit": qty * rate},
                ],
            )

        return purchase_id

    # ----- Customer payment (in) -----

    def post_customer_payment(self, *, customer: Customer, date_iso: str, amount: int,
                              payment_mode: str, reference: Optional[str],
                              allocations: List[Tuple[int, str, int]]) -> int:
        """
        allocations: list of (invoice_id, invoice_number, amount)
        """
        bank_id = self.account_id_by_name["HDFC Current A/c"]
        bank_name = "HDFC Current A/c"
        payment_number = self.next_payment_number(date_iso)

        self.cur.execute(
            "INSERT INTO payments (payment_number, payment_date, customer_id, bank_account_id, amount, payment_mode, reference, notes, status, customer_snapshot, bank_account_snapshot, created_at, vendor_id, payment_direction, tds_amount, tds_section) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payment_number, date_iso, customer.id, bank_id, amount, payment_mode, reference, None, "posted",
             self._customer_snapshot_json(customer), bank_name, self._now(), None, "in", 0, None),
        )
        payment_id = self.cur.lastrowid

        for inv_id, inv_num, alloc_amt in allocations:
            self.cur.execute(
                "INSERT INTO payment_allocations (payment_id, invoice_id, amount, invoice_number_snapshot) VALUES (?,?,?,?)",
                (payment_id, inv_id, alloc_amt, inv_num),
            )

        entry_id = self.post_entry(
            voucher_type="receipt",
            voucher_ref=payment_number,
            narration=f"Payment {payment_number} from {customer.name} via {payment_mode}",
            posted_at=date_iso,
            lines=[
                {"accountId": bank_id, "debit": amount, "credit": 0},
                {"accountId": self.account_id_by_name["Sundry Debtors"], "debit": 0, "credit": amount},
            ],
        )
        self.cur.execute("UPDATE payments SET ledger_entry_id = ? WHERE id = ?", (entry_id, payment_id))
        return payment_id

    # ----- Vendor payment (with optional TDS) -----

    def post_vendor_payment(self, *, vendor: Vendor, date_iso: str, gross_amount: int,
                            payment_mode: str, reference: Optional[str],
                            tds_section: Optional[str] = None, tds_rate: Optional[float] = None) -> int:
        """
        gross_amount = bill total. TDS is computed off the bill (taxable portion);
        net to vendor = gross - tds. We post:
            Dr Sundry Creditors (gross)
            Cr Bank (net)
            Cr TDS Payable (tds)
        """
        bank_id = self.account_id_by_name["HDFC Current A/c"]
        bank_name = "HDFC Current A/c"
        payment_number = self.next_payment_number(date_iso)

        tds_amount = 0
        if tds_section and tds_rate:
            # Approximation: deduct on the gross. (Real life: on taxable portion.)
            tds_amount = round(gross_amount * tds_rate)

        net_to_vendor = gross_amount - tds_amount

        self.cur.execute(
            "INSERT INTO payments (payment_number, payment_date, customer_id, bank_account_id, amount, payment_mode, reference, notes, status, customer_snapshot, bank_account_snapshot, created_at, vendor_id, payment_direction, tds_amount, tds_section) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payment_number, date_iso, None, bank_id, net_to_vendor, payment_mode, reference, None, "posted",
             self._vendor_snapshot_json(vendor), bank_name, self._now(), vendor.id, "out", tds_amount, tds_section),
        )
        payment_id = self.cur.lastrowid

        lines = [
            {"accountId": self.account_id_by_name["Sundry Creditors"], "debit": gross_amount, "credit": 0},
            {"accountId": bank_id, "debit": 0, "credit": net_to_vendor},
        ]
        if tds_amount > 0 and tds_section:
            tds_acc = self.get_or_create_tds_payable_account(tds_section)
            lines.append({"accountId": tds_acc, "debit": 0, "credit": tds_amount})

        entry_id = self.post_entry(
            voucher_type="payment",
            voucher_ref=payment_number,
            narration=f"Payment {payment_number} to {vendor.name} via {payment_mode}" + (f" [TDS {tds_section}]" if tds_section else ""),
            posted_at=date_iso,
            lines=lines,
        )
        self.cur.execute("UPDATE payments SET ledger_entry_id = ? WHERE id = ?", (entry_id, payment_id))

        if tds_amount > 0 and tds_section:
            self.cur.execute(
                "INSERT INTO tds_deductions (payment_id, vendor_id, section, rate, taxable_amount, tds_amount, payment_date, vendor_pan, vendor_name_snapshot, ledger_entry_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (payment_id, vendor.id, tds_section, tds_rate, gross_amount, tds_amount, date_iso,
                 vendor.pan, vendor.name, entry_id, self._now()),
            )
            self.append_audit(actor="owner", action="tds.deduction", ref=f"payment:{payment_id}",
                              payload={"paymentId": payment_id, "section": tds_section, "tds": tds_amount,
                                       "vendorId": vendor.id})

        return payment_id

    # ----- Journal voucher -----

    def post_journal(self, *, date_iso: str, narration: str, lines: List[Dict[str, int]],
                     voucher_ref: Optional[str] = None) -> int:
        return self.post_entry(
            voucher_type="journal",
            voucher_ref=voucher_ref,
            narration=narration,
            posted_at=date_iso,
            lines=lines,
        )

    # ----- Finalize -----

    def collect_row_counts(self) -> Dict[str, int]:
        tables = [
            "accounts", "entries", "entry_lines", "audit_log", "customers", "vendors",
            "items", "invoices", "invoice_lines", "purchases", "purchase_lines",
            "payments", "payment_allocations", "advances", "advance_adjustments",
            "credit_notes", "credit_note_lines", "debit_notes", "debit_note_lines",
            "tds_deductions", "tcs_collections", "stock_movements", "godowns",
            "invoice_series",
        ]
        out = {}
        for t in tables:
            row = self.cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
            out[t] = row[0] if row else 0
        self.row_counts = out
        return out

    def trial_balance_check(self) -> Tuple[int, int, int]:
        row = self.cur.execute("SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM entry_lines").fetchone()
        dr, cr = row[0], row[1]
        return dr, cr, dr - cr

    def export_db_bytes(self) -> bytes:
        # Sqlite3 in-memory backup → bytes
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            tmp_path = tf.name
        try:
            with sqlite3.connect(tmp_path) as bk:
                self.conn.backup(bk)
            data = Path(tmp_path).read_bytes()
        finally:
            os.unlink(tmp_path)
        return data

    def build_manifest(self, db_bytes: bytes) -> Dict[str, Any]:
        manifest = {
            "khataFormatVersion": KHATA_FORMAT_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "workspaceId": self.workspace_id,
            "createdAt": self.created_at_iso,
            "lastModifiedAt": iso_now(self._clock),
            "company": self.company,
            "uiTier": self.ui_tier,
            "snapshots": [],
            "integrity": {
                "booksHash": sha256_bytes_hex(db_bytes),
                "auditHead": self.get_audit_head(),
                "signedBy": self.public_jwk,
            },
            "modeHistory": [{"ts": self.created_at_iso, "mode": "owner"}],
        }
        return manifest

    def write_khata(self, out_path: Path) -> Dict[str, Any]:
        # Final audit entry: a session.start to wrap things up
        self.append_audit(
            actor="system",
            action="generator.complete",
            ref=str(out_path.name),
            payload={"generator": "sample-data/generator.py", "schemaVersion": SCHEMA_VERSION,
                     "rowCounts": self.collect_row_counts()},
        )
        db_bytes = self.export_db_bytes()
        manifest = self.build_manifest(db_bytes)
        manifest_json = json.dumps(manifest, indent=2)

        # Build zip with deterministic timestamp
        buf = io.BytesIO()
        # Use a fixed date_time for reproducibility
        date_time = (2026, 4, 8, 9, 0, 0)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zi = zipfile.ZipInfo("manifest.json", date_time=date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, manifest_json)
            zi2 = zipfile.ZipInfo("books.sqlite", date_time=date_time)
            zi2.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi2, db_bytes)
            # Empty folder entries
            for folder in ("attachments/", "exports/"):
                zi3 = zipfile.ZipInfo(folder, date_time=date_time)
                zf.writestr(zi3, b"")
        out_path.write_bytes(buf.getvalue())
        return manifest


# === Utility: deterministic naming/data pools ===

INDIAN_CITY_BY_STATE = {
    "MH": ["Mumbai", "Pune", "Nagpur", "Nashik", "Aurangabad"],
    "GJ": ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar"],
    "KA": ["Bangalore", "Mysore", "Hubli", "Mangalore", "Belgaum"],
    "TN": ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"],
    "DL": ["New Delhi", "Delhi"],
    "WB": ["Kolkata", "Howrah", "Durgapur"],
    "TG": ["Hyderabad", "Warangal"],
    "AP": ["Visakhapatnam", "Vijayawada", "Guntur"],
    "UP": ["Lucknow", "Kanpur", "Noida", "Ghaziabad"],
    "HR": ["Gurgaon", "Faridabad"],
    "KL": ["Kochi", "Trivandrum", "Calicut"],
    "RJ": ["Jaipur", "Jodhpur", "Udaipur"],
    "MP": ["Bhopal", "Indore"],
    "PB": ["Ludhiana", "Amritsar", "Chandigarh"],
}

PHARMA_HOSPITAL_NAMES = [
    "Apollo Hospitals", "Fortis Healthcare", "Max Health Centre", "Lilavati Trust",
    "Hinduja Hospital", "Wockhardt Clinic", "Manipal Health", "Narayana Health",
    "Kokilaben Mehta Hospital", "Jaslok Foundation",
]
PHARMA_CHEMIST_CHAINS = [
    "MedPlus Pharmacy", "Apollo Pharmacy", "Wellness Forever", "Trust Chemists",
    "Noble Chemists", "Health & Glow Pharmacy", "1mg Stores",
]
PHARMA_CLINICS = [
    "Sunrise Polyclinic", "Janta Clinic", "Aastha Diagnostic Centre",
    "Vedanta Clinic", "Sai Health Centre",
]
PHARMA_GOODS = [
    ("Paracetamol 500mg (10x10)", "3004", 0.12, "strip", 1200),
    ("Amoxicillin 500mg caps (10x10)", "3004", 0.12, "strip", 4500),
    ("Cetirizine 10mg (10x10)", "3004", 0.12, "strip", 800),
    ("Azithromycin 500mg (10x6)", "3004", 0.12, "strip", 3200),
    ("Pantoprazole 40mg (10x10)", "3004", 0.12, "strip", 1100),
    ("Metformin 500mg (10x10)", "3004", 0.12, "strip", 750),
    ("Atorvastatin 10mg (10x10)", "3004", 0.12, "strip", 2500),
    ("Telmisartan 40mg (10x10)", "3004", 0.12, "strip", 1800),
    ("Losartan 50mg (10x10)", "3004", 0.12, "strip", 1600),
    ("Ondansetron 4mg (10x10)", "3004", 0.12, "strip", 950),
    ("Vitamin D3 60K (4 caps)", "3004", 0.12, "strip", 320),
    ("ORS sachet (pack of 10)", "3004", 0.12, "pack", 280),
    ("Insulin Glargine 100IU/ml (3ml)", "3004", 0.12, "vial", 19500),
    ("Cough syrup 100ml", "3004", 0.12, "bottle", 12500),
    ("Antiseptic cream 50g", "3004", 0.12, "tube", 18500),
    ("Surgical gloves (box of 100)", "9018", 0.18, "box", 45000),
    ("Disposable syringe 5ml (box of 100)", "9018", 0.18, "box", 32000),
    ("Glucometer test strips (50)", "9018", 0.18, "pack", 65000),
    ("Blood pressure monitor", "9018", 0.18, "pcs", 175000),
    ("RT-PCR test kit (10)", "3822", 0.12, "pack", 95000),
]
PHARMA_SERVICES = [
    ("Quality testing — finished goods", "998311", 0.18, "lot", 2500000),
    ("Stability study — accelerated", "998311", 0.18, "study", 4500000),
    ("Bioavailability study", "998311", 0.18, "study", 8500000),
    ("Pharmacovigilance review", "998311", 0.18, "monthly", 1850000),
    ("Regulatory dossier preparation", "998311", 0.18, "dossier", 12500000),
    ("Contract manufacturing — tablets", "998311", 0.12, "lakh tabs", 950000),
    ("Method development", "998311", 0.18, "method", 6500000),
    ("Cleaning validation", "998311", 0.18, "study", 3500000),
    ("Microbial limit testing", "998311", 0.18, "test", 350000),
    ("API impurity profiling", "998311", 0.18, "test", 4500000),
]

PHARMA_VENDORS = [
    ("Sigma Chemicals Ltd", "GJ", "supplier", None),
    ("Lupin Bulk Drugs", "MH", "supplier", None),
    ("Reliance Polypack", "GJ", "packaging", None),
    ("Schott Kaisha (glass vials)", "MH", "packaging", None),
    ("Nilkamal Crates", "MH", "packaging", None),
    ("Blue Dart Express", "MH", "logistics", "194C"),
    ("Gati KWE Ltd", "MH", "logistics", "194C"),
    ("VRL Logistics", "KA", "logistics", "194C"),
    ("Sun Pharma — CMO", "GJ", "cmo", None),
    ("Cipla Contract Mfg", "MH", "cmo", None),
    ("Watson Pharma Services", "MH", "cmo", None),
    ("Patel & Associates (CA)", "MH", "consultant", "194J"),
    ("Deshmukh Legal", "MH", "consultant", "194J"),
    ("Karnik & Co Auditors", "MH", "consultant", "194J"),
    ("Tata AIG Insurance", "MH", "consultant", "194J"),
    ("Shree Sai Security Pvt Ltd", "MH", "facility", "194C"),
    ("Sparkle Housekeeping", "MH", "facility", "194C"),
    ("Maharashtra State Electricity", "MH", "utility", None),
    ("Mahanagar Gas", "MH", "utility", None),
    ("Tata Communications", "MH", "utility", None),
]

MFG_CUSTOMERS = [
    ("Tata Motors Ltd", "MH"),
    ("Mahindra & Mahindra Ltd", "MH"),
    ("Hero MotoCorp Ltd", "DL"),
    ("Maruti Suzuki India Ltd", "HR"),
    ("Bajaj Auto Ltd", "MH"),
    ("Larsen & Toubro Ltd", "MH"),
    ("Godrej & Boyce", "MH"),
    ("Voltas Ltd", "MH"),
    ("Whirlpool of India", "HR"),
    ("Havells India Ltd", "HR"),
    ("Crompton Greaves", "MH"),
    ("Jindal Steel Buyers Co", "GJ"),
    ("Surya Roshni Steel", "GJ"),
    ("Bhushan Power Buyers", "GJ"),
    ("Ashok Leyland Ltd", "TN"),
]
MFG_VENDORS = [
    ("Adani Mining Pvt Ltd", "GJ", "raw"),
    ("Vedanta Limited", "MH", "raw"),
    ("Hindalco Industries", "MH", "raw"),
    ("NMDC Limited", "TG", "raw"),
    ("MOIL Limited", "MH", "raw"),
    ("Torrent Power Ltd", "GJ", "utility"),
    ("ABB India (mtce)", "MH", "service"),
    ("Siemens India (mtce)", "MH", "service"),
    ("Jindal Logistics", "GJ", "logistics"),
    ("Patel Manpower Services", "GJ", "labour"),
]
MFG_ITEMS = [
    ("Hot rolled coil 1.6mm", "7308", 0.18, "tonne", 5800000),
    ("Cold rolled sheet 1.0mm", "7308", 0.18, "tonne", 6500000),
    ("Galvanised sheet 0.5mm", "7308", 0.18, "tonne", 7200000),
    ("Steel bar 12mm TMT", "7308", 0.18, "tonne", 6200000),
    ("Steel bar 16mm TMT", "7308", 0.18, "tonne", 6300000),
    ("Steel bar 20mm TMT", "7308", 0.18, "tonne", 6400000),
    ("Steel pipe 100mm dia", "7308", 0.18, "tonne", 7800000),
    ("Steel pipe 50mm dia", "7308", 0.18, "tonne", 7600000),
    ("Wire rod 5.5mm", "7308", 0.18, "tonne", 5900000),
    ("Square section 25mm", "7308", 0.18, "tonne", 6700000),
    ("Angle iron 50x50x5", "7308", 0.18, "tonne", 6450000),
    ("Channel section 100mm", "7308", 0.18, "tonne", 6800000),
    ("MS plate 8mm", "7308", 0.18, "tonne", 6600000),
    ("MS plate 12mm", "7308", 0.18, "tonne", 6700000),
    ("Round bar 25mm", "7308", 0.18, "tonne", 6350000),
]
MFG_RAW_ITEMS = [
    ("Iron ore (Fe 62%)", "7308", 0.18, "tonne", 850000),
    ("Coking coal", "2701", 0.18, "tonne", 1850000),
    ("Manganese ore", "7308", 0.18, "tonne", 1450000),
    ("Steel scrap (HMS-1)", "7308", 0.18, "tonne", 2950000),
    ("Ferro silicon", "7308", 0.18, "tonne", 9500000),
]

CONSULTING_CLIENTS = [
    ("Stitch Labs Pvt Ltd", "KA", "techstartup"),
    ("Razorpath Tech", "KA", "techstartup"),
    ("Bluefin Analytics", "MH", "techstartup"),
    ("Karnataka Bank Limited", "KA", "bank"),
    ("EduFutures Foundation", "KA", "nonprofit"),
    ("Singh Family Office", "MH", "familyoffice"),
    ("R. Iyer (NRI)", "TN", "individual"),
    ("S. Mehta (NRI)", "GJ", "individual"),
]
CONSULTING_VENDORS = [
    ("WeWork Galaxy (Indiranagar)", "KA", None),
    ("Atlassian India (subscriptions)", "KA", None),
    ("R. Krishnan & Co (CA)", "KA", "194J"),
]
CONSULTING_ITEMS = [
    ("Management consulting — monthly retainer", "998311", 0.18, "month", 6500000),
    ("Strategy advisory project", "998311", 0.18, "project", 12500000),
    ("M&A advisory — buy-side", "998311", 0.18, "engagement", 25000000),
    ("Financial modelling", "998311", 0.18, "model", 4500000),
    ("Board advisory", "998311", 0.18, "monthly", 8500000),
]


# === Per-company generation logic ===

def business_dates_in_month(rng: random.Random, year: int, month: int, n: int) -> List[str]:
    """Pick n unique weekday dates in a given year/month."""
    out = []
    days = []
    for d in range(1, 29):  # safe upper bound
        try:
            dt = datetime(year, month, d)
        except ValueError:
            continue
        if dt.weekday() < 5:
            days.append(dt)
    if not days:
        return []
    for _ in range(n):
        out.append(rng.choice(days).strftime("%Y-%m-%d"))
    out.sort()
    return out


def gen_pharma() -> KhataBuilder:
    print("[pharma] starting…")
    company = {
        "name": "Vaidya Life Sciences Pvt Ltd",
        "trade_name": "Vaidya Pharma",
        "company_type": "private-limited",
        "gstin": "27AABCV1234A1Z5",
        "pan": "AABCV1234A",
        "tan": "MUMB12345A",
        "state": "MH",
        "stateName": "Maharashtra",
        "gstinStateCode": "27",
        "address": "Plot 47, MIDC Industrial Area, Andheri East, Mumbai 400093",
        "fy_start": "2021-04-01",
        "composition": {"enabled": False},
    }
    b = KhataBuilder(company=company, ui_tier="goods", fy_start="2021-04-01",
                     seed=42, clock_start=datetime(2021, 4, 1, 9, 0, 0, tzinfo=timezone.utc))
    rng = b.rng

    b.create_db()
    b.seed_invoice_series()
    b.seed_default_godown()
    b.seed_coa()
    b.append_audit(actor="owner", action="file.create", ref="pharma.khata",
                   payload={"companyName": company["name"], "gstin": company["gstin"],
                            "stateIso": company["state"], "schemaVersion": SCHEMA_VERSION,
                            "formatVersion": KHATA_FORMAT_VERSION})
    b.append_audit(actor="owner", action="session.start", ref=None,
                   payload={"origin": GENERATOR_ORIGIN})

    # 40 customers
    cust_specs = []
    for name in PHARMA_HOSPITAL_NAMES + PHARMA_CHEMIST_CHAINS + PHARMA_CLINICS:
        # Spread across states
        state = rng.choice(["MH", "MH", "MH", "GJ", "KA", "DL", "TG", "TN"])
        cust_specs.append((name, state))
    while len(cust_specs) < 38:
        i = len(cust_specs)
        cust_specs.append((f"City Pharmacy #{i}", rng.choice(["MH", "GJ", "KA", "DL"])))
    # Two B2C walk-ins (no GSTIN)
    cust_specs.append(("Walk-in customer (Mumbai)", "MH"))
    cust_specs.append(("Walk-in customer (Pune)", "MH"))

    for name, state in cust_specs[:40]:
        gstin = None
        if "Walk-in" not in name:
            st = STATE_BY_ISO[state]
            gstin = f"{st[1]}{rng_gstin_pan(rng)}1Z{rng.choice('123456789')}"
        city = rng.choice(INDIAN_CITY_BY_STATE.get(state, [STATE_BY_ISO[state][2]]))
        b.add_customer(name=name, gstin=gstin, state=state,
                       email=f"{name.lower().replace(' ', '.').replace('&','and')}@example.com" if "Walk-in" not in name else None,
                       phone=f"+91 9{rng.randint(100000000, 999999999)}",
                       address=f"{city}, {STATE_BY_ISO[state][2]}")

    # 20 vendors
    for name, state, vtype, tds in PHARMA_VENDORS:
        gstin = f"{STATE_BY_ISO[state][1]}{rng_gstin_pan(rng)}1Z{rng.choice('123456789')}"
        city = rng.choice(INDIAN_CITY_BY_STATE.get(state, [STATE_BY_ISO[state][2]]))
        b.add_vendor(name=name, gstin=gstin, state=state,
                     email=None, phone=None,
                     address=f"{city}, {STATE_BY_ISO[state][2]}",
                     rcm_applicable=0, tds_section=tds)

    # 30 items: 20 goods + 10 services
    for name, hsn, rate, unit, paise_per_unit in PHARMA_GOODS:
        valuation = "fifo" if rng.random() < 0.2 else "wac"
        b.add_item(name=name, hsn_sac=hsn, is_service=0, unit=unit,
                   default_rate=paise_per_unit, default_tax_rate=rate,
                   enable_inventory=1, valuation_method=valuation, track_batches=0)
    for name, sac, rate, unit, paise_per_unit in PHARMA_SERVICES:
        b.add_item(name=name, hsn_sac=sac, is_service=1, unit=unit,
                   default_rate=paise_per_unit, default_tax_rate=rate,
                   enable_inventory=0)

    goods_items = [it for it in b.items if not it.is_service]
    service_items = [it for it in b.items if it.is_service]

    # Aerated health beverage — carries 12% compensation cess before the 2025-09-22 cutover.
    # Created AFTER the goods/service lists (inventory off) so the random activity loops ignore it;
    # it is sold via a dedicated quarterly block after the main loop to demonstrate cess.
    aerated = b.add_item(name="Vaidya Glucose-D Fizz 250ml (case of 24)", hsn_sac="22021010",
                         is_service=0, unit="case", default_rate=48000, default_tax_rate=0.28,
                         enable_inventory=0)

    # ----- 60 months of activity -----
    # First seed opening stock via initial purchases (so sales never short)
    print("[pharma] seeding opening stock…")
    seed_vendor = b.vendors[0]
    seed_date = "2021-04-02"
    for it in goods_items:
        # Buy a healthy initial stock at ~85% of sale rate
        cost_rate = round(it.default_rate * 0.65)
        qty = rng.randint(50, 150)
        b.post_purchase(vendor=seed_vendor, bill_number=f"OPEN-{it.id:03d}",
                        date_iso=seed_date,
                        line_specs=[{"item": it, "quantity": qty, "rate": cost_rate}])

    # Track outstanding invoices (id, num, balance) for receipts
    outstanding: List[Tuple[int, str, int]] = []

    months = []
    for fy in (2021, 2022, 2023, 2024, 2025):
        for m in range(4, 13):
            months.append((fy, m))
        for m in range(1, 4):
            months.append((fy + 1, m))

    print(f"[pharma] generating {len(months)} months of activity…")
    for (year, month) in months:
        # Invoices: 25/month
        for date_iso in business_dates_in_month(rng, year, month, 25):
            cust = rng.choice(b.customers)
            n_lines = rng.randint(1, 4)
            line_specs = []
            # Pharma mix: mostly goods, occasional service
            for _ in range(n_lines):
                if rng.random() < 0.85 and goods_items:
                    it = rng.choice(goods_items)
                    qty = rng.randint(1, 8)
                    # Slight rate variation +/-5%
                    rate = round(it.default_rate * rng.uniform(0.97, 1.05))
                else:
                    it = rng.choice(service_items)
                    qty = 1
                    rate = round(it.default_rate * rng.uniform(0.95, 1.10))
                line_specs.append({"item": it, "quantity": qty, "rate": rate})
            inv_id = b.post_invoice(customer=cust, date_iso=date_iso, line_specs=line_specs)
            row = b.cur.execute("SELECT invoice_number, total FROM invoices WHERE id = ?", (inv_id,)).fetchone()
            outstanding.append((inv_id, row[0], row[1]))

        # Purchases: 10/month
        for date_iso in business_dates_in_month(rng, year, month, 10):
            ven = rng.choice(b.vendors)
            n_lines = rng.randint(1, 3)
            line_specs = []
            for _ in range(n_lines):
                it = rng.choice(goods_items)
                qty = rng.randint(20, 80)
                cost = round(it.default_rate * 0.65 * rng.uniform(0.95, 1.05))
                line_specs.append({"item": it, "quantity": qty, "rate": cost})
            b.post_purchase(vendor=ven, bill_number=f"BILL-{ven.id:02d}-{date_iso.replace('-','')}",
                            date_iso=date_iso, line_specs=line_specs)

        # Customer receipts: 20/month — pay oldest invoices first
        for date_iso in business_dates_in_month(rng, year, month, 20):
            if not outstanding:
                continue
            # Allocate some open invoices
            target = outstanding[0]
            inv_id, num, bal = target
            amt = bal
            b.post_customer_payment(
                customer_for_id(b, inv_id),
                date_iso=date_iso, amount=amt,
                payment_mode=rng.choice(["neft", "rtgs", "upi", "cheque"]),
                reference=f"UTR{rng.randint(100000, 999999)}",
                allocations=[(inv_id, num, amt)],
            ) if False else None
            # The above is a NoOp pattern — replace with real call:
            cust = customer_for_id(b, inv_id)
            b.post_customer_payment(
                customer=cust, date_iso=date_iso, amount=amt,
                payment_mode=rng.choice(["neft", "rtgs", "upi", "cheque"]),
                reference=f"UTR{rng.randint(100000, 999999)}",
                allocations=[(inv_id, num, amt)],
            )
            outstanding.pop(0)

        # Vendor payments: 15/month — some with TDS
        for date_iso in business_dates_in_month(rng, year, month, 15):
            ven = rng.choice(b.vendors)
            tds_section = ven.tds_section
            tds_rate = None
            if tds_section == "194C":
                tds_rate = 0.02
            elif tds_section == "194J":
                tds_rate = 0.10
            gross = rng.randint(2500000, 35000000)  # ₹25k–₹3.5L
            b.post_vendor_payment(
                vendor=ven, date_iso=date_iso, gross_amount=gross,
                payment_mode=rng.choice(["neft", "rtgs"]),
                reference=f"VENDOR-UTR{rng.randint(100000, 999999)}",
                tds_section=tds_section, tds_rate=tds_rate,
            )

    # ----- Aerated-beverage sales: one invoice per quarter, settled promptly. Demonstrates
    # date-effective compensation cess — 12% before 2025-09-22, zero on/after. -----
    print("[pharma] adding aerated-beverage sales (compensation cess)…")
    for (year, month) in months:
        if month not in (4, 7, 10, 1):  # one per quarter
            continue
        adate = business_dates_in_month(rng, year, month, 1)[0]
        acust = rng.choice(b.customers)
        aqty = rng.randint(20, 120)
        ataxable = aqty * aerated.default_rate
        acess = round(ataxable * 0.12) if cess_active_on(adate) else 0
        ainv = b.post_invoice(customer=acust, date_iso=adate,
                              line_specs=[{"item": aerated, "quantity": aqty,
                                           "rate": aerated.default_rate, "cess": acess}])
        arow = b.cur.execute("SELECT invoice_number, total FROM invoices WHERE id = ?", (ainv,)).fetchone()
        b.post_customer_payment(customer=acust, date_iso=adate, amount=arow[1],
                                payment_mode="neft", reference=f"UTR{rng.randint(100000, 999999)}",
                                allocations=[(ainv, arow[0], arow[1])])

    # A handful of credit notes (pharmaceutical sales returns happen)
    print("[pharma] adding credit notes / debit notes / journals…")
    cn_dates = ["2024-08-15", "2024-12-10", "2025-03-22", "2025-07-08", "2025-11-19", "2026-02-14"]
    for d in cn_dates:
        # Use a random small amount as a sales return
        amt = rng.randint(50000, 250000)
        cust = rng.choice(b.customers)
        cn_num = b.next_cn_number(d)
        # Find a recent invoice for the customer
        inv_row = b.cur.execute(
            "SELECT id, invoice_number FROM invoices WHERE customer_id = ? ORDER BY id LIMIT 1",
            (cust.id,)
        ).fetchone()
        if not inv_row:
            continue
        b.cur.execute(
            "INSERT INTO credit_notes (cn_number, cn_date, original_invoice_id, original_invoice_number, customer_id, reason, place_of_supply, place_of_supply_name, subtotal, cgst, sgst, igst, total, status, company_snapshot, customer_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cn_num, d, inv_row[0], inv_row[1], cust.id, "sales-return", cust.state,
             STATE_BY_ISO[cust.state][2], amt, 0, 0, 0, amt, "posted",
             b._company_snapshot_json(), b._customer_snapshot_json(cust), b._now())
        )
        cn_id = b.cur.lastrowid
        b.cur.execute(
            "INSERT INTO credit_note_lines (cn_id, line_no, description, hsn_sac, hsn_description, quantity, rate, taxable, tax_rate, rate_id, cgst, sgst, igst, total) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cn_id, 1, "Sales return — short shipment", "3004", "Medicaments, packaged for retail sale",
             1, amt, amt, 0, "gst-0", 0, 0, 0, amt)
        )
        # Ledger: Dr Sales / Cr Sundry Debtors
        b.post_entry(
            voucher_type="credit-note", voucher_ref=cn_num,
            narration=f"Credit note {cn_num} against {inv_row[1]} for {cust.name}",
            posted_at=d,
            lines=[
                {"accountId": b.account_id_by_name["Sales"], "debit": amt, "credit": 0},
                {"accountId": b.account_id_by_name["Sundry Debtors"], "debit": 0, "credit": amt},
            ],
        )

    # A few journal vouchers — depreciation, prepaid rent, accruals
    print("[pharma] adding journal vouchers…")
    jv_dates = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-09-30", "2025-12-31", "2026-03-31"]
    for d in jv_dates:
        amt = rng.randint(15000000, 40000000)
        # Depreciation: Dr Indirect Expenses / Cr Fixed Assets
        b.post_journal(
            date_iso=d, narration="Quarterly depreciation provision",
            lines=[
                {"accountId": b.account_id_by_name["Indirect Expenses"], "debit": amt, "credit": 0},
                {"accountId": b.account_id_by_name["Fixed Assets"], "debit": 0, "credit": amt},
            ],
        )

    # An advance receipt
    print("[pharma] adding advance receipts…")
    adv_cust = b.customers[0]
    adv_date = "2024-07-15"
    adv_amount = 1000000
    adv_taxable = round(adv_amount / 1.12)
    adv_tax = adv_amount - adv_taxable
    adv_num = b.next_advance_number(adv_date)
    company_intra = adv_cust.state == b.company["state"]
    if company_intra:
        cgst = adv_tax // 2
        sgst = adv_tax - cgst
        igst = 0
    else:
        cgst = sgst = 0
        igst = adv_tax
    b.cur.execute(
        "INSERT INTO advances (advance_number, advance_date, customer_id, bank_account_id, amount, taxable, tax_rate, rate_id, cgst, sgst, igst, place_of_supply, place_of_supply_name, nature_of_supply, payment_mode, reference, adjusted_amount, remaining_balance, status, customer_snapshot, bank_account_snapshot, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (adv_num, adv_date, adv_cust.id, b.account_id_by_name["HDFC Current A/c"],
         adv_amount, adv_taxable, 0.12, "gst-12", cgst, sgst, igst,
         adv_cust.state, STATE_BY_ISO[adv_cust.state][2], "goods", "neft",
         "ADVUTR123456", 0, adv_amount, "open",
         b._customer_snapshot_json(adv_cust), "HDFC Current A/c", b._now())
    )
    adv_id = b.cur.lastrowid
    # Post the advance: Dr Bank / Cr Customer Advances Received / Cr GST output
    posting_lines = [
        {"accountId": b.account_id_by_name["HDFC Current A/c"], "debit": adv_amount, "credit": 0},
        {"accountId": b.account_id_by_name["Customer Advances Received"], "debit": 0, "credit": adv_taxable},
    ]
    if cgst > 0:
        posting_lines.append({"accountId": b.get_or_create_rate_account("CGST Output", 6), "debit": 0, "credit": cgst})
    if sgst > 0:
        posting_lines.append({"accountId": b.get_or_create_rate_account("SGST Output", 6), "debit": 0, "credit": sgst})
    if igst > 0:
        posting_lines.append({"accountId": b.get_or_create_rate_account("IGST Output", 12), "debit": 0, "credit": igst})
    entry_id = b.post_entry(
        voucher_type="receipt", voucher_ref=adv_num,
        narration=f"Advance {adv_num} from {adv_cust.name}",
        posted_at=adv_date, lines=posting_lines,
    )
    b.cur.execute("UPDATE advances SET ledger_entry_id = ? WHERE id = ?", (entry_id, adv_id))

    print("[pharma] done generating.")
    return b


def gen_manufacturing() -> KhataBuilder:
    print("[mfg] starting…")
    company = {
        "name": "Shree Krishna Steel Industries Ltd",
        "trade_name": None,
        "company_type": "public-limited",
        "gstin": "24AAACS5678B1Z3",
        "pan": "AAACS5678B",
        "tan": "AHMS67890B",
        "state": "GJ",
        "stateName": "Gujarat",
        "gstinStateCode": "24",
        "address": "Plot 12, GIDC Phase II, Vatva, Ahmedabad 382445",
        "fy_start": "2021-04-01",
        "composition": {"enabled": False},
    }
    b = KhataBuilder(company=company, ui_tier="goods", fy_start="2021-04-01",
                     seed=43, clock_start=datetime(2021, 4, 1, 9, 0, 0, tzinfo=timezone.utc))
    rng = b.rng

    b.create_db()
    b.seed_invoice_series()
    b.seed_default_godown()
    b.seed_coa()
    b.append_audit(actor="owner", action="file.create", ref="manufacturing.khata",
                   payload={"companyName": company["name"], "gstin": company["gstin"],
                            "stateIso": company["state"], "schemaVersion": SCHEMA_VERSION,
                            "formatVersion": KHATA_FORMAT_VERSION})
    b.append_audit(actor="owner", action="session.start", ref=None,
                   payload={"origin": GENERATOR_ORIGIN})

    for name, state in MFG_CUSTOMERS:
        st = STATE_BY_ISO[state]
        gstin = f"{st[1]}{rng_gstin_pan(rng)}1Z{rng.choice('123456789')}"
        b.add_customer(name=name, gstin=gstin, state=state,
                       email=f"accounts@{name.split()[0].lower()}.example.com",
                       phone=f"+91 9{rng.randint(100000000, 999999999)}",
                       address=f"{rng.choice(INDIAN_CITY_BY_STATE.get(state, [st[2]]))}, {st[2]}")

    for name, state, vtype in MFG_VENDORS:
        st = STATE_BY_ISO[state]
        gstin = f"{st[1]}{rng_gstin_pan(rng)}1Z{rng.choice('123456789')}"
        tds = "194C" if vtype in ("logistics", "labour") else ("194J" if vtype == "service" else None)
        b.add_vendor(name=name, gstin=gstin, state=state, email=None, phone=None,
                     address=f"{rng.choice(INDIAN_CITY_BY_STATE.get(state, [st[2]]))}, {st[2]}",
                     rcm_applicable=0, tds_section=tds)

    for name, hsn, rate, unit, paise in MFG_ITEMS:
        b.add_item(name=name, hsn_sac=hsn, is_service=0, unit=unit,
                   default_rate=paise, default_tax_rate=rate,
                   enable_inventory=1, valuation_method="wac")
    # Raw items used as inventory inputs
    for name, hsn, rate, unit, paise in MFG_RAW_ITEMS:
        b.add_item(name=name, hsn_sac=hsn, is_service=0, unit=unit,
                   default_rate=paise, default_tax_rate=rate,
                   enable_inventory=1, valuation_method="wac")

    finished_items = [it for it in b.items if "raw" not in it.name.lower() and not any(k in it.name for k in ["Iron ore", "Coking coal", "Manganese", "scrap", "Ferro"])]
    raw_items = [it for it in b.items if it not in finished_items]

    # Opening stock: heavy initial purchase
    print("[mfg] seeding opening stock…")
    seed_vendor = b.vendors[0]
    seed_date = "2021-04-02"
    for it in finished_items:
        cost = round(it.default_rate * 0.85)
        b.post_purchase(vendor=seed_vendor, bill_number=f"OPEN-{it.id:03d}",
                        date_iso=seed_date,
                        line_specs=[{"item": it, "quantity": rng.randint(20, 100), "rate": cost}])

    months = []
    for fy in (2021, 2022, 2023, 2024, 2025):
        for m in range(4, 13):
            months.append((fy, m))
        for m in range(1, 4):
            months.append((fy + 1, m))

    outstanding: List[Tuple[int, str, int]] = []
    print(f"[mfg] generating {len(months)} months…")
    for (year, month) in months:
        # 15 invoices/month, high value
        for date_iso in business_dates_in_month(rng, year, month, 15):
            cust = rng.choice(b.customers)
            n_lines = rng.randint(1, 3)
            line_specs = []
            for _ in range(n_lines):
                it = rng.choice(finished_items)
                qty = rng.randint(2, 20)
                rate = round(it.default_rate * rng.uniform(0.96, 1.06))
                line_specs.append({"item": it, "quantity": qty, "rate": rate})
            inv_id = b.post_invoice(customer=cust, date_iso=date_iso, line_specs=line_specs)
            row = b.cur.execute("SELECT invoice_number, total FROM invoices WHERE id = ?", (inv_id,)).fetchone()
            outstanding.append((inv_id, row[0], row[1]))

        # 12 purchases/month — mix of raw + finished restocking
        for date_iso in business_dates_in_month(rng, year, month, 12):
            ven = rng.choice(b.vendors)
            it = rng.choice(finished_items + raw_items)
            qty = rng.randint(15, 70)
            cost = round(it.default_rate * 0.78 * rng.uniform(0.97, 1.05))
            spec = {"item": it, "quantity": qty, "rate": cost}
            # Coking coal (HSN 2701) carried ₹400/tonne specific compensation cess until 2025-09-22.
            if it.hsn_sac == "2701" and cess_active_on(date_iso):
                spec["cess"] = qty * 40000
            b.post_purchase(vendor=ven, bill_number=f"BILL-{ven.id:02d}-{date_iso.replace('-','')}",
                            date_iso=date_iso, line_specs=[spec])

        # 12 receipts/month
        for date_iso in business_dates_in_month(rng, year, month, 12):
            if not outstanding:
                continue
            target = outstanding[0]
            inv_id, num, bal = target
            cust = customer_for_id(b, inv_id)
            b.post_customer_payment(
                customer=cust, date_iso=date_iso, amount=bal,
                payment_mode=rng.choice(["neft", "rtgs"]),
                reference=f"UTR{rng.randint(100000, 999999)}",
                allocations=[(inv_id, num, bal)],
            )
            outstanding.pop(0)

        # 8 vendor payments/month
        for date_iso in business_dates_in_month(rng, year, month, 8):
            ven = rng.choice(b.vendors)
            tds_rate = None
            if ven.tds_section == "194C":
                tds_rate = 0.02
            elif ven.tds_section == "194J":
                tds_rate = 0.10
            b.post_vendor_payment(
                vendor=ven, date_iso=date_iso,
                gross_amount=rng.randint(20000000, 200000000),
                payment_mode="rtgs",
                reference=f"VENDOR-UTR{rng.randint(100000, 999999)}",
                tds_section=ven.tds_section, tds_rate=tds_rate,
            )

    print("[mfg] done generating.")
    return b


def gen_consulting() -> KhataBuilder:
    print("[consulting] starting…")
    company = {
        "name": "Arjun Rao Advisory LLP",
        "trade_name": None,
        "company_type": "llp",
        "gstin": "29AAEFA9012C1Z7",
        "pan": "AAEFA9012C",
        "tan": "BLRA90123C",
        "state": "KA",
        "stateName": "Karnataka",
        "gstinStateCode": "29",
        "address": "3rd Floor, Prestige Atlanta, 80 Feet Road, Indiranagar, Bangalore 560038",
        "fy_start": "2021-04-01",
        "composition": {"enabled": False},
    }
    b = KhataBuilder(company=company, ui_tier="service", fy_start="2021-04-01",
                     seed=44, clock_start=datetime(2021, 4, 1, 9, 0, 0, tzinfo=timezone.utc))
    rng = b.rng

    b.create_db()
    b.seed_invoice_series()
    b.seed_default_godown()
    b.seed_coa()
    b.append_audit(actor="owner", action="file.create", ref="consulting.khata",
                   payload={"companyName": company["name"], "gstin": company["gstin"],
                            "stateIso": company["state"], "schemaVersion": SCHEMA_VERSION,
                            "formatVersion": KHATA_FORMAT_VERSION})
    b.append_audit(actor="owner", action="session.start", ref=None,
                   payload={"origin": GENERATOR_ORIGIN})

    for name, state, ctype in CONSULTING_CLIENTS:
        st = STATE_BY_ISO[state]
        gstin = None
        if ctype not in ("individual",):
            gstin = f"{st[1]}{rng_gstin_pan(rng)}1Z{rng.choice('123456789')}"
        b.add_customer(name=name, gstin=gstin, state=state,
                       email=f"contact@{name.split()[0].lower().replace('.','')}.example.com",
                       phone=f"+91 9{rng.randint(100000000, 999999999)}",
                       address=f"{rng.choice(INDIAN_CITY_BY_STATE.get(state, [st[2]]))}, {st[2]}")

    for name, state, tds in CONSULTING_VENDORS:
        st = STATE_BY_ISO[state]
        gstin = f"{st[1]}{rng_gstin_pan(rng)}1Z{rng.choice('123456789')}"
        b.add_vendor(name=name, gstin=gstin, state=state, email=None, phone=None,
                     address=f"{rng.choice(INDIAN_CITY_BY_STATE.get(state, [st[2]]))}, {st[2]}",
                     rcm_applicable=0, tds_section=tds)

    for name, sac, rate, unit, paise in CONSULTING_ITEMS:
        b.add_item(name=name, hsn_sac=sac, is_service=1, unit=unit,
                   default_rate=paise, default_tax_rate=rate, enable_inventory=0)

    months = []
    for fy in (2021, 2022, 2023, 2024, 2025):
        for m in range(4, 13):
            months.append((fy, m))
        for m in range(1, 4):
            months.append((fy + 1, m))

    outstanding: List[Tuple[int, str, int]] = []
    print(f"[consulting] generating {len(months)} months…")
    for (year, month) in months:
        for date_iso in business_dates_in_month(rng, year, month, 8):
            cust = rng.choice(b.customers)
            n_lines = rng.randint(1, 2)
            line_specs = []
            for _ in range(n_lines):
                it = rng.choice(b.items)
                rate = round(it.default_rate * rng.uniform(0.95, 1.10))
                line_specs.append({"item": it, "quantity": 1, "rate": rate})
            inv_id = b.post_invoice(customer=cust, date_iso=date_iso, line_specs=line_specs)
            row = b.cur.execute("SELECT invoice_number, total FROM invoices WHERE id = ?", (inv_id,)).fetchone()
            outstanding.append((inv_id, row[0], row[1]))

        for date_iso in business_dates_in_month(rng, year, month, 5):
            if not outstanding:
                continue
            inv_id, num, bal = outstanding[0]
            cust = customer_for_id(b, inv_id)
            b.post_customer_payment(
                customer=cust, date_iso=date_iso, amount=bal,
                payment_mode=rng.choice(["neft", "upi", "rtgs"]),
                reference=f"UTR{rng.randint(100000, 999999)}",
                allocations=[(inv_id, num, bal)],
            )
            outstanding.pop(0)

        for date_iso in business_dates_in_month(rng, year, month, 3):
            ven = rng.choice(b.vendors)
            tds_rate = 0.10 if ven.tds_section == "194J" else None
            b.post_vendor_payment(
                vendor=ven, date_iso=date_iso,
                gross_amount=rng.randint(2500000, 18000000),
                payment_mode="neft",
                reference=f"VENDOR-UTR{rng.randint(100000, 999999)}",
                tds_section=ven.tds_section, tds_rate=tds_rate,
            )

    print("[consulting] done generating.")
    return b


# === Helpers used during generation ===

def rng_gstin_pan(rng: random.Random) -> str:
    """Generate the 10-char PAN-shape part of a GSTIN: 5 letters + 4 digits + 1 letter."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    p = "".join(rng.choice(letters) for _ in range(5))
    p += "".join(rng.choice(digits) for _ in range(4))
    p += rng.choice(letters)
    return p


def customer_for_id(b: KhataBuilder, invoice_id: int) -> Customer:
    row = b.cur.execute("SELECT customer_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    cid = row[0]
    for c in b.customers:
        if c.id == cid:
            return c
    raise KeyError(f"customer {cid} not found")


# === Validation ===

def validate(b: KhataBuilder, label: str) -> Dict[str, Any]:
    print(f"[{label}] validating…")
    results: Dict[str, Any] = {}
    # PRAGMA integrity_check
    row = b.cur.execute("PRAGMA integrity_check").fetchone()
    results["integrity_check"] = row[0]
    # Trial balance tie
    dr, cr, diff = b.trial_balance_check()
    results["sum_debit"] = dr
    results["sum_credit"] = cr
    results["balance_diff"] = diff
    # Audit chain walk
    rows = b.cur.execute("SELECT id, ts, actor, action, ref, origin, payload, prev_hash, hash, signature, hash_version FROM audit_log ORDER BY id ASC").fetchall()
    prev = GENESIS_PREV
    bad = 0
    for r in rows:
        _id, ts, actor, action, ref, origin, payload, prev_hash, hash_v, sig, hv = r
        if prev_hash != prev:
            bad += 1
            print(f"  audit chain break at id={_id}: prev={prev[:12]} expected, got {prev_hash[:12]}")
        # Recompute with the row's hash version (v2 = all fields; legacy = origin+payload only).
        if hv == 2:
            computed = sha256_hex(audit_preimage_v2(prev_hash, ts, actor, action, ref, origin, payload or ""))
        else:
            computed = sha256_hex(prev + (origin or "") + (payload or ""))
        if computed != hash_v:
            bad += 1
            print(f"  audit hash mismatch at id={_id}")
        prev = hash_v
    results["audit_chain_count"] = len(rows)
    results["audit_chain_bad"] = bad
    results["audit_chain_head"] = rows[-1][8] if rows else None

    # Verify final signature with the public key
    if rows:
        last_hash = rows[-1][8]
        last_sig = rows[-1][9]
        try:
            from cryptography.exceptions import InvalidSignature
            import base64 as _b64
            sig_raw = _b64.b64decode(last_sig)
            r_int = int.from_bytes(sig_raw[:32], "big")
            s_int = int.from_bytes(sig_raw[32:], "big")
            der = asym_utils.encode_dss_signature(r_int, s_int)
            b.pub_key.verify(der, hex_to_bytes(last_hash), ec.ECDSA(hashes.SHA256()))
            results["signature_verify"] = "ok"
        except Exception as e:
            results["signature_verify"] = f"FAIL: {e}"

    # Per-account-type tally for the trial balance summary
    type_tally = b.cur.execute(
        """
        SELECT a.type, COALESCE(SUM(l.debit),0) AS dr, COALESCE(SUM(l.credit),0) AS cr
        FROM entry_lines l JOIN accounts a ON a.id = l.account_id
        GROUP BY a.type
        """
    ).fetchall()
    results["by_type"] = [{"type": t[0], "debit": t[1], "credit": t[2]} for t in type_tally]
    return results


# === Main ===

def main():
    OUT_DIR.mkdir(exist_ok=True)
    print(f"Output dir: {OUT_DIR}")

    builds = []
    for fn, name, label in [
        (gen_pharma, "pharma.khata", "pharma"),
        (gen_manufacturing, "manufacturing.khata", "mfg"),
        (gen_consulting, "consulting.khata", "consulting"),
    ]:
        b = fn()
        out_path = OUT_DIR / name
        manifest = b.write_khata(out_path)
        validation = validate(b, label)
        builds.append({
            "name": name,
            "company": b.company,
            "ui_tier": b.ui_tier,
            "row_counts": b.row_counts,
            "manifest": manifest,
            "validation": validation,
            "size_bytes": out_path.stat().st_size,
        })
        print(f"[{label}] wrote {out_path} ({out_path.stat().st_size:,} bytes)")
        print(f"[{label}] row counts: {b.row_counts}")
        print(f"[{label}] validation: integrity={validation['integrity_check']}, "
              f"diff={validation['balance_diff']}, audit_chain={validation['audit_chain_count']} "
              f"(bad={validation['audit_chain_bad']}), signature={validation['signature_verify']}")
        b.conn.close()

    # Write the report
    write_report(builds)
    print(f"\nAll done. Wrote 3 .khata files + GENERATION-REPORT.md to {OUT_DIR}")


def write_report(builds: List[Dict[str, Any]]) -> None:
    lines = ["# Bahi Sample Data — Generation Report\n"]
    lines.append(f"Generated by `generator.py` on a deterministic seed.\n")
    lines.append(f"Schema version: **{SCHEMA_VERSION}** · Format version: **{KHATA_FORMAT_VERSION}**\n")
    lines.append("All audit log entries carry `origin = 'local-file://generator.py'` so they're easy to spot as synthetic.\n")
    lines.append("\n---\n")

    for b in builds:
        lines.append(f"\n## {b['name']}\n")
        lines.append(f"- **Legal name**: {b['company']['name']}")
        if b['company'].get('trade_name'):
            lines.append(f"- **Trade name**: {b['company']['trade_name']}")
        lines.append(f"- **GSTIN**: `{b['company']['gstin']}`  ·  **PAN**: `{b['company']['pan']}`  ·  **TAN**: `{b['company'].get('tan')}`")
        lines.append(f"- **State**: {b['company']['stateName']} ({b['company']['state']}, GST code {b['company']['gstinStateCode']})")
        lines.append(f"- **UI tier**: `{b['ui_tier']}`  ·  **FY start**: {b['company']['fy_start']}")
        lines.append(f"- **File size**: {b['size_bytes']:,} bytes")
        lines.append("")
        lines.append("### Row counts")
        lines.append("")
        lines.append("| Table | Count |")
        lines.append("| --- | --- |")
        for k, v in b["row_counts"].items():
            lines.append(f"| {k} | {v:,} |")
        lines.append("")

        lines.append("### Trial balance")
        lines.append("")
        v = b["validation"]
        lines.append(f"- **Sum of debits**: ₹{v['sum_debit']/100:,.2f}")
        lines.append(f"- **Sum of credits**: ₹{v['sum_credit']/100:,.2f}")
        lines.append(f"- **Difference**: {v['balance_diff']} paise → {'TIES' if v['balance_diff'] == 0 else 'OUT OF BALANCE'}")
        lines.append("")
        lines.append("By account type:")
        lines.append("")
        lines.append("| Type | Debit | Credit | Net |")
        lines.append("| --- | ---: | ---: | ---: |")
        for row in v["by_type"]:
            net = row["debit"] - row["credit"]
            lines.append(f"| {row['type']} | ₹{row['debit']/100:,.2f} | ₹{row['credit']/100:,.2f} | ₹{net/100:,.2f} |")
        lines.append("")

        lines.append("### Audit chain")
        lines.append("")
        lines.append(f"- **Length**: {v['audit_chain_count']:,} entries")
        lines.append(f"- **Bad rows**: {v['audit_chain_bad']}")
        lines.append(f"- **Final hash**: `{v['audit_chain_head']}`")
        lines.append(f"- **Final signature verify**: {v['signature_verify']}")
        lines.append("")

        lines.append("### Validation")
        lines.append("")
        lines.append(f"- **PRAGMA integrity_check**: `{v['integrity_check']}`")
        lines.append(f"- **Manifest workspaceId**: `{b['manifest']['workspaceId']}`")
        lines.append(f"- **Manifest auditHead**: `{b['manifest']['integrity']['auditHead']}`")
        lines.append(f"- **Manifest booksHash**: `{b['manifest']['integrity']['booksHash']}`")
        lines.append("")
        lines.append("---")

    lines.append("\n## How to open in Bahi")
    lines.append("")
    lines.append("Open Bahi (e.g. http://localhost:8101/), pick **Workspace → Open existing**, and select each `.khata` file. "
                 "Bahi will run `verifyAuditChain` on open and surface any chain breakage in its identity banner.")
    lines.append("")
    lines.append("## Reproducing")
    lines.append("")
    lines.append("```")
    lines.append("python3 generator.py")
    lines.append("```")
    lines.append("")
    lines.append("Re-running with the same Python+cryptography versions produces byte-identical files (deterministic seeds, fixed clock).")

    (OUT_DIR / "GENERATION-REPORT.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
