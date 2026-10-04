# Changelog

All notable changes to Bahi. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/). The `.khata` file format and the database schema carry their own versions (format 1.0, schema 12).

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
