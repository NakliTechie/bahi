# Changelog

All notable changes to Bahi. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/). The `.khata` file format and the database schema carry their own versions (format 1.0, schema 12).

## [Unreleased]

Tax reference data caught up with the law, and is now generated from khata-standard instead of hand-kept.

### Fixed

- **TDS used the Income-tax Act 1961 after it was replaced.** From 2026-04-01 the Income-tax Act 2025 numbers sections 392–393 with 4-digit return codes. A vendor saved with `194C` now pays under `1023` (individual or HUF) or `1024` (other payee), resolved by payment date and PAN; the quarter reports on Form 140, the certificate is Form 131.
- **TDS ignored the payee and the PAN.** 194C took 1% from companies (the law says 2%), and a payee without a PAN was not charged the higher rate. Rates now follow the PAN's fourth letter, and no PAN takes the no-PAN rate (20% for most sections).
- **Old-Act rates were stale.** 194H fell from 5% to 2% on 2024-10-01; thresholds for 194A, 194H, 194I and 194J rose on 2025-04-01, and rent's became monthly. Each period now has its own row.
- **TCS offered 206C(1H) after it ended** (2025-03-31) and defaulted to it. TCS sections follow the collection date: 206C up to 2026-03-31, section 394 at the Finance Act 2026 rates after.
- **GST 2.0 was missing.** The 40% band applies from 2025-09-22, 28% ends on 2026-01-31, and 12% stays for bricks and tiles. Medicines moved from 12% to 5%, larger cars and aerated drinks to 40%, pan masala and tobacco to 40% on 2026-02-01, when their compensation cess ended.
- **A picked item kept its saved rate across a rate change.** A picked item takes the HSN's rate on the document's date, and changing the date redraws the rate list. HSN codes match their heading (30049099 takes 3004's rate).
- **The invoice line's Amount cell read ₹0.00** while the totals were right; it now follows typing. Purchase bills and stock transfers had the same fault.
- **The TDS certificate was labelled Form 27D**, the TCS certificate. It is Form 16A (Form 131 from FY 2026-27).
- **A reference-data update broke TDS and TCS.** The update took the dataset's wrapper object instead of its rows, and a second update within five minutes failed on a cache hit.
- The vendor form offered `194I`, which the engine refused; it now lists the sections in force.

### Added

- A PAN field on customers and vendors, checked against the PAN inside the GSTIN.
- Agent read tools `list_tax_sections` and `lookup_gst_rate` (85 tools).
- `tools/bundle-reference.mjs` writes the bundled TDS, TCS and GST tables from khata-standard's published files.
- Checks C56–C59: tax sections by date and PAN, GST 2.0 by date, the Amount cell, the reference-update path.

## [0.1.0] — 2026-10-04

The first tagged release. Bahi has been live at <https://bahi.naklitechie.com> through its alpha; the features that shipped before this tag are listed in [docs/FEATURES.md](docs/FEATURES.md). This release gives the app an agent face and puts every write behind one command bus.

### Added

- **Agent face v2** ([agent/AGENT.md](agent/AGENT.md)): 83 tools declared once with JSON Schema inputs, published through WebMCP (`document.modelContext` / `navigator.modelContext`), `window.bahi`, and a cross-tab `BroadcastChannel('bahi-agent')` that stays closed until you open it in Settings → Agent access.
- **Writes wait for you.** An agent's write becomes a proposal under the agent button in the header; nothing posts until you approve it. Approved writes save the file and record `agentCall {door, caller, proposalId, approvedBy}` in the audit log.
- **20 person-only acts**, declared with reasons: opening books, closing the year, locking periods, CA sign-off and adjustments, merges, the Debug Console, reference-data updates, imports and exports, backups, snapshot restores, undo, the mode switch, AI setup, and approving or rejecting proposals.
- **Read tools for every screen**: document lists, both registers, P&L, the dashboard, stock, CMP-08, Form 27EQ and 27D, challan data sheets, bank reconciliation, annotations. Each reads through the same function as its screen.
- **Write tools for every form**: masters (customers, vendors, items, bank accounts, series, godowns, company details) and every voucher (invoice, purchase, receipt, credit and debit note, journal, advance, vendor payment with TDS, TCS, delivery challan, e-way bill, stock transfer), bank reconciliation and snapshots.
- **One command bus.** Every form that changes the books submits through `bahiUi` to its tool, through the same queue agent approvals use. `agent/harness/lint-agent-face.mjs` proves it: every writing function is owned by a tool, a person-only act or declared infrastructure, and no screen writes outside the bus.
- The app's own social card (`/social.png` and `og:` / `twitter:` tags), and a repo social preview.

### Changed

- The README follows the house shape (343 → 80 lines); the full feature list and design notes moved to [docs/FEATURES.md](docs/FEATURES.md).
- Master edits, delivery challans, e-way bills and stock transfers now write audit entries; edits and these vouchers wrote none.
- A master's checks (GSTIN against state, TDS section, duplicate bank account) run when an agent calls, so a bad input never reaches you as a proposal.
- The agent API is 2.0.0: tool names are `verb_noun` (`create_invoice`, not `invoice.create`). The 1.0 names are gone.

### Fixed

- **TDS and TCS rates read the wrong column of their tables.** Choosing 194C on a vendor payment showed "TDS @ 3000000.00%" and withheld ₹30 crore on ₹10,000; TCS sections showed "(NaN%)". The rates are now 1% for 194C and the table's rate for each TCS section.
- **Tax quarters ran a day early in IST.** Form 26Q, 27EQ, 27D and CMP-08 used 31 March – 29 June for Q1, so TDS deducted on 30 June fell in Q2 and 31 March's in the next financial year.
- **Entries stamped with a time vanished on a range's last day.** Undo entries and opening stock posted on, say, 30 June were missing from the June day book, ledger, trial balance and stock views.
- The `.khata` format test suite found no sample books after the repository moved; it runs from its own folder again.

### Verified

`node checks.mjs`: 55/55 · `node prove-red.mjs`: every check seen to fail under its defect · `node lint-agent-face.mjs`: 0 problems, self-test 6/6 · `python3 -m unittest discover` in `sample-data/`: 53/53 · first-run smoke: pass.

[0.1.0]: https://github.com/NakliTechie/bahi/releases/tag/v0.1.0
