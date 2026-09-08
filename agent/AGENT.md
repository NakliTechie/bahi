# Bahi — agent surface

Bahi has two doors into one core. The first is the UI. The second is `window.bahi`,
a JSON-in / JSON-out command API over the same engine, so an agent can read the books
and post to them without scraping the DOM.

- Machine-readable contract: [`manifest.json`](manifest.json) — also live at `bahi.call('agent.manifest')`.
- Every command is declared there. Nothing dispatchable is undeclared, and nothing declared is undispatchable.
  `bahi.call('agent.selftest')` proves it and fails loudly if the two ever drift.

## The whole interface

```js
await window.bahi.call(command, args)   // → {ok:true, data} | {ok:false, error:{code, message}}
window.bahi.manifest()                  // the full contract, synchronously
window.bahi.commands()                  // just the names
window.bahi.version                     // '1.0.0'
```

`call()` **never throws and never rejects.** A machine interface that requires `try/catch`
around every call will eventually be called without one. Branch on `result.ok`.

## Four rules

1. **Money is integer paise.** 100 paise = ₹1. Never a float, never a formatted string.
   Amounts above 2,147,483,647 paise (₹2,14,74,836.47) per line are refused rather than
   silently truncated — several engine paths coerce with `| 0`, and the boundary is named
   here instead of corrupting a ledger quietly.
2. **Dates are `YYYY-MM-DD`,** real calendar dates. `2026-02-30` is rejected, not rolled forward.
   A command with a `range` pair rejects a start later than its end. A backwards range is a
   caller mistake, not an empty period — a reversed GST period must never come back as a nil filing.
3. **Mutating commands are flagged** `mutating: true` in the manifest. Everything else is a pure read.
4. **Every mutation is attributable.** Agent writes land in the append-only audit log with
   `actor` = `agent`, or `agent:<agentName>` when you pass one. Pass `agentName`. A future
   reader of these books deserves to know which machine posted what.
   `agentName` must match `[A-Za-z0-9._-]{1,60}`. The audit log's actor column already carries
   `owner`, `ca`, `ai` and `system` as real principals, and `:` is that field's own separator —
   an unconstrained name could be shaped into an actor string a reader mistakes for a person.

For an **optional** parameter, `null` and `undefined` both mean "not supplied" and the declared
default applies. A **required** parameter is never satisfied by `null`.

## Errors

Branch on `error.code`, never on the message text.

| Code | Meaning |
|---|---|
| `E_UNKNOWN_COMMAND` | No such command. Call `agent.commands`. |
| `E_BAD_ARGS` | Arguments failed the declared parameter spec. `error.problems` lists each one. |
| `E_NO_FILE` | No `.khata` is open. File-scoped commands need one. |
| `E_READONLY` | File opened read-only (newer `.khata` format than this build). Mutations refused. |
| `E_ENGINE` | The accounting engine refused the operation. Its own message is passed through. |
| `E_INTERNAL` | A bug in the dispatcher. Report it. |

## Commands

24 commands. `agent.*` and `ui.*` work with no file open; everything else needs one.

| Command | | What it does |
|---|---|---|
| `agent.manifest` `agent.commands` `agent.health` `agent.selftest` | | Discovery, and the parity check that guards this surface. |
| `file.info` `file.verifyIntegrity` `file.auditTail` | | Company identity and versions; audit-chain + signature verification; the tail of the append-only log, so you can read your own writes back and confirm attribution. |
| `file.save` | **M** | Persist the books to disk. |
| `masters.customers` `masters.vendors` `masters.items` `masters.accounts` | | Paged master lists. `q` filters by name, `includeArchived` defaults false — matching what the UI shows. |
| `report.trialBalance` `report.balanceSheet` `report.dayBook` `report.accountLedger` `report.receivablesAging` `report.stockOnHand` `report.valuationSummary` | | Reports, as of a date or over a range. |
| `gst.gstr1` `gst.gstr3b` `tds.form26q` | | Return data for a period or quarter. |
| `journal.post` | **M** | Post a balanced double-entry voucher. |
| `ui.routes` `ui.navigate` | | The first door's route index, and navigation to a known route. |

### `journal.post`

```js
await bahi.call('journal.post', {
  lines: [                                  // ≥2, ≤500; Dr total must equal Cr total
    { accountId: 12, debit: 150000 },       // ₹1,500.00 in paise
    { accountId: 34, credit: 150000 },
  ],
  narration: 'Rent for April',
  postedAt: '2026-04-30',                   // defaults to today
  agentName: 'my-agent',                    // → audit actor 'agent:my-agent'
});
```

Posting into a **filed (locked) period** is allowed and flagged, exactly as the UI does it —
the entry is marked an amendment rather than refused. The response tells you:
`{ amendment: true, periodLock: { return_type, period_start, period_end } }`. A second door
that is stricter than the first is still a divergence.

## What is deliberately not here

`manifest.gaps` lists all 49 uncovered UI routes with a reason each, and `agent.selftest`
asserts that every route in the app is either covered by a command or named there. A new
screen cannot quietly appear without someone deciding whether agents get it.

Four of those are refusals, not backlog:

- **No raw SQL.** The Debug Console covers a human at a keyboard. The agent face does not get one.
- **No filesystem access.** No path ever reaches this API.
- **FY rollover, CA sign-off, and branch reconciliation stay human.** Irreversible or a judgement call.
- **Period locks are read-only here.** Marking a return filed is a compliance act.

## Security note

This API grants no privilege that page script did not already have — anything on this origin
can already reach the database. What it changes is the blast radius of a **prompt injection**:
an agent that reads a malicious bill, PDF, or web result and then drives this API is the
realistic attack. That is why writes are flagged, attributable in a hash-chained audit log,
and reversible by counter-entry, and why there is no SQL and no filesystem door here.

Keep it that way when you extend it.

## Testing it

[`harness/drive.mjs`](harness/) boots `index.html` in headless Chromium, swaps the native file
pickers for an in-memory filesystem, opens a scratch copy of a sample book, and runs a batch of
calls:

```bash
cd agent/harness && npm install
echo '[{"command":"agent.selftest"}]' | node drive.mjs --book pharma --calls -
```

`--book` takes `fresh` (a new empty book), `none` (nothing open, for the `E_NO_FILE` paths), or
a sample name from `sample-data/`. Samples are copied to a temp dir first; the repo's books are
never written to.

`node checks.mjs` runs the full assertion suite (22 checks). Set `BAHI_FUTURE_KHATA` to a
`.khata` whose `khataFormatVersion` is ahead of this build to exercise the read-only path.

`node prove-red.mjs` reintroduces each defect those checks guard, one at a time, and confirms the
matching check goes **red** — then restores the file and confirms green. A check never seen to fail
is not a check, so the suite is only worth what this script says it is.
