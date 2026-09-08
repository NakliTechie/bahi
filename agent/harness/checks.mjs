// Bahi agent-surface checks
// =========================
// The assertion suite that guards window.bahi. Every check here has been proven able
// to FAIL — each one was run once with its defect deliberately reintroduced, and each
// one went red. A check that stays green either way is not a check.
//
//   node checks.mjs            # all checks
//   node checks.mjs --only C6  # one check
//
// Exit code 0 = all green, 1 = at least one red.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { runCalls } from './drive.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const DECLARED_CODES = ['E_UNKNOWN_COMMAND', 'E_BAD_ARGS', 'E_NO_FILE', 'E_READONLY', 'E_ENGINE', 'E_INTERNAL'];

const only = (() => { const i = process.argv.indexOf('--only'); return i > -1 ? process.argv[i + 1] : null; })();

const results = [];
function record(id, title, pass, detail) { results.push({ id, title, pass, detail }); }

const ok = (r) => r.result && r.result.ok === true;
const err = (r) => (r.result && r.result.error) || {};
const data = (r) => (r.result && r.result.data) || {};

// --- batch 1: no file open -------------------------------------------------
async function batchNoFile() {
  const run = await runCalls({ book: 'none', calls: [
    { command: 'agent.selftest' },
    { command: 'agent.manifest' },
    { command: '__nope__' },
    { command: 'report.trialBalance', args: { asOf: '2026-03-31' } },
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 1 }, { accountId: 2, credit: 1 }] } },
  ] });
  const [selftest, manifest, unknown, tb, post] = run.results;

  // C1 — the two doors name the same commands, and every UI route is covered or
  // declared a gap. Reintroduce by deleting a handler or adding an undeclared one.
  record('C1', 'manifest/dispatcher/route parity (agent.selftest)',
    ok(selftest) && data(selftest).pass === true,
    ok(selftest) ? `failures: ${JSON.stringify(data(selftest).failures)}` : JSON.stringify(err(selftest)));

  // C2 — the published agent/manifest.json is the live manifest, not a stale copy.
  // Reintroduce by editing a command's summary in the code and not regenerating.
  let drift = 'manifest.json missing';
  if (ok(manifest)) {
    const published = JSON.parse(fs.readFileSync(path.join(REPO, 'agent', 'manifest.json'), 'utf8'));
    const a = JSON.stringify(published), b = JSON.stringify(data(manifest));
    drift = a === b ? 'identical' : `published ${a.length}B vs live ${b.length}B`;
  }
  record('C2', 'published manifest.json matches the live manifest', drift === 'identical', drift);

  // C3 — unknown commands are refused with the declared code.
  record('C3', 'unknown command -> E_UNKNOWN_COMMAND',
    !ok(unknown) && err(unknown).code === 'E_UNKNOWN_COMMAND', JSON.stringify(err(unknown)));

  // C4 — file-scoped commands refuse cleanly with no file open, rather than
  // dereferencing a null STATE.db. Reintroduce by removing the scope guard.
  record('C4', 'file-scoped read with no file -> E_NO_FILE',
    !ok(tb) && err(tb).code === 'E_NO_FILE', JSON.stringify(err(tb)));
  record('C5', 'file-scoped mutation with no file -> E_NO_FILE',
    !ok(post) && err(post).code === 'E_NO_FILE', JSON.stringify(err(post)));

  return run;
}

// --- batch 2: a real book --------------------------------------------------
async function batchSample() {
  const POST = (lines, extra = {}) => ({ command: 'journal.post', args: { lines, agentName: 'checks', postedAt: '2025-06-15', ...extra } });
  const run = await runCalls({ book: 'pharma', calls: [
    { command: 'file.info' },                                                   // 0  baseline
    { command: 'report.trialBalance', args: { asOf: '2026-03-31' } },           // 1
    { command: 'masters.customers', args: { limit: 5 } },                       // 2
    { command: 'masters.customers', args: { q: "' OR 1=1 --", limit: 5 } },     // 3  injection
    { command: 'masters.customers', args: { q: "'; DROP TABLE customers; --" } }, // 4 injection
    { command: 'masters.customers', args: { limit: 5 } },                       // 5  table survived?
    { command: 'file.info' },                                                   // 6  reads pure?
    { command: 'report.dayBook', args: { from: '2026-13-01', to: '2026-03-31' } }, // 7  bad month
    { command: 'report.dayBook', args: { from: '2026-02-30', to: '2026-03-31' } }, // 8  bad day
    { command: 'report.trialBalance', args: { asOf: 1 } },                      // 9  wrong type
    { command: 'masters.customers', args: { limit: 0 } },                       // 10 below min
    { command: 'masters.customers', args: { limit: 99999 } },                   // 11 above max
    { command: 'masters.customers', args: { nope: 1 } },                        // 12 unknown param
    { command: 'masters.customers', args: [] },                                 // 13 args not an object
    POST([{ accountId: 1, debit: 100 }, { accountId: 2, credit: 99 }]),         // 14 unbalanced
    POST([{ accountId: 1, debit: 100 }]),                                       // 15 one line
    POST([{ accountId: 1, debit: 2147483648 }, { accountId: 2, credit: 2147483648 }]), // 16 over ceiling
    POST([{ accountId: 1, debit: 1.5 }, { accountId: 2, credit: 1.5 }]),        // 17 float paise
    POST([{ accountId: 1, debit: -100 }, { accountId: 2, credit: -100 }]),      // 18 negative
    POST([{ accountId: 'x', debit: 100 }, { accountId: 2, credit: 100 }]),      // 19 bad accountId
    POST(['not-an-object', { accountId: 2, credit: 100 }]),                     // 20 line not object
    { command: 'ui.navigate', args: { route: 'javascript:alert(1)' } },         // 21 bogus route
    { command: 'report.dayBook', args: { from: '2026-03-31', to: '2025-04-01' } }, // 22 reversed range
    { command: 'file.auditTail', args: { limit: 3 } },                          // 23 pre-post tail
    POST([{ accountId: 1, debit: 12345 }, { accountId: 2, credit: 12345 }], { narration: 'checks attribution probe' }), // 24 the one good post
    { command: 'file.auditTail', args: { limit: 3 } },                          // 25 post-post tail
    { command: 'file.verifyIntegrity' },                                        // 26 chain intact
    { command: 'agent.selftest' },                                              // 27 surface intact
    { command: 'gst.gstr1', args: { periodStart: '2025-04-30', periodEnd: '2025-04-01' } },   // 28 reversed period
    { command: 'report.dayBook', args: { from: '2026-03-31', to: '2025-04-01' } },            // 29 reversed range
    { command: 'report.accountLedger', args: { accountId: 1, from: '2026-03-31', to: '2025-04-01' } }, // 30
    // Delivered as literal JSON text so `__proto__` arrives as an OWN property, the
    // way it would over a real wire. Structured clone drops it and tests nothing.
    { command: 'masters.customers', argsJson: '{"__proto__":{"polluted":"yes"},"limit":2}' },  // 31
    { command: 'agent.health', argsJson: '{"__proto__":{"limit":1}}' },                        // 32
    { command: 'journal.post', argsJson: '{"lines":[{"accountId":1,"debit":1000,"__proto__":{"credit":1000}},{"accountId":2,"credit":1000}],"agentName":"proto"}' }, // 33
    { command: 'agent.health' },                                                               // 34 pollution visible?
    // Attribution forgery: ':' is the actor field's own separator and the audit log
    // already carries 'owner' / 'ca' / 'ai' / 'system' as real principals.
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'ca:verified' } },  // 35
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'owner:ca:ai' } },  // 36
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'a b' } },          // 37
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: '' } },             // 38
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'checks-ok_1.2' } },// 39 must succeed
    { command: 'file.auditTail', args: { limit: 5 } },                                                                                     // 40
  ] });
  const R = run.results;

  // C6 — the `q` filter is a bound parameter, not string interpolation. Reintroduce
  // by building the WHERE clause with `name LIKE '%${a.q}%'`.
  const injectedRows = ok(R[3]) ? data(R[3]).rows.length : -1;
  const baselineRows = ok(R[2]) ? data(R[2]).rows.length : -1;
  const survived = ok(R[5]) && data(R[5]).rows.length === baselineRows;
  record('C6', 'q filter is bound, not interpolated (SQL injection)',
    injectedRows === 0 && ok(R[4]) && survived,
    `injected-rows=${injectedRows} baseline=${baselineRows} table-survived=${survived}`);

  // C7 — impossible calendar dates are refused, not coerced by new Date().
  // Reintroduce by validating with /^\d{4}-\d{2}-\d{2}$/ alone.
  record('C7', 'impossible calendar dates -> E_BAD_ARGS',
    !ok(R[7]) && err(R[7]).code === 'E_BAD_ARGS' && !ok(R[8]) && err(R[8]).code === 'E_BAD_ARGS',
    `2026-13-01:${err(R[7]).code} 2026-02-30:${err(R[8]).code}`);

  // C8 — the declared param spec is actually enforced.
  const c8 = [9, 10, 11, 12, 13].map((i) => !ok(R[i]) && err(R[i]).code === 'E_BAD_ARGS');
  record('C8', 'param spec enforced (type, min, max, unknown key, non-object args)',
    c8.every(Boolean), `wrongType/min/max/unknownKey/nonObject = ${c8.join('/')}`);

  // C9 — nested lines[] are validated too, not just the declared top-level params.
  // This is the check that catches a validator which stops at the array boundary.
  const c9 = [16, 17, 18, 19, 20].map((i) => !ok(R[i]) && err(R[i]).code === 'E_BAD_ARGS');
  record('C9', 'nested journal lines[] validated (ceiling, float, negative, bad id, non-object)',
    c9.every(Boolean), `overCeiling/float/negative/badId/nonObject = ${c9.join('/')}`);

  // C10 — the engine's double-entry assertion is reachable and typed.
  record('C10', 'unbalanced and single-line postings refused',
    !ok(R[14]) && !ok(R[15]) && DECLARED_CODES.includes(err(R[14]).code) && DECLARED_CODES.includes(err(R[15]).code),
    `unbalanced:${err(R[14]).code} oneLine:${err(R[15]).code}`);

  // C11 — reads do not mutate. booksHash and auditHead must be untouched across the
  // read-only prefix. Reintroduce by having any read call db.run().
  const before = ok(R[0]) ? data(R[0]) : {};
  const after = ok(R[6]) ? data(R[6]) : {};
  record('C11', 'reads are pure (booksHash + auditHead unchanged)',
    !!before.booksHash && before.booksHash === after.booksHash && before.auditHead === after.auditHead,
    `booksHash ${String(before.booksHash).slice(0, 12)} -> ${String(after.booksHash).slice(0, 12)}`);

  // C12 — ui.navigate only accepts routes the app actually has.
  record('C12', 'ui.navigate refuses a route outside the route index',
    !ok(R[21]) && err(R[21]).code === 'E_BAD_ARGS', JSON.stringify(err(R[21])));

  // C13 — an agent write is attributable in the append-only audit log.
  // Reintroduce by dropping the actor stamp in journal.post.
  const tailBefore = ok(R[23]) ? data(R[23]).entries : [];
  const tailAfter = ok(R[25]) ? data(R[25]).entries : [];
  const newest = tailAfter[0] || {};
  record('C13', 'agent write is attributable (actor agent:<name> in the audit log)',
    ok(R[24]) && newest.actor === 'agent:checks' && newest.action === 'entry.post' && tailAfter.length > 0 && newest.id > (tailBefore[0] || {}).id,
    `newest actor=${newest.actor} action=${newest.action} id=${newest.id} was=${(tailBefore[0] || {}).id}`);

  // C14 — the trial balance ties on a real book, verified INDEPENDENTLY. Asserting the
  // surface's own `balanced` flag proved to be no check at all: a defect deriving totalCr
  // from the debit column keeps that flag true. So sum the returned rows here and require
  // the surface's reported totals to match this suite's arithmetic, not its own.
  const tb = ok(R[1]) ? data(R[1]) : null;
  const ownDr = tb ? tb.rows.reduce((s2, r) => s2 + r.debit, 0) : -1;
  const ownCr = tb ? tb.rows.reduce((s2, r) => s2 + r.credit, 0) : -2;
  record('C14', 'trial balance ties, verified independently of the surface\'s own totals',
    !!tb && tb.rows.length > 0 && ownDr === ownCr && tb.totalDr === ownDr && tb.totalCr === ownCr && tb.balanced === true,
    tb ? `rows=${tb.rows.length} suiteDr=${ownDr} suiteCr=${ownCr} surfaceDr=${tb.totalDr} surfaceCr=${tb.totalCr} flag=${tb.balanced}` : 'call failed');

  // C15 — the audit hash chain is intact after everything above.
  record('C15', 'audit chain intact after the whole batch',
    ok(R[26]) && data(R[26]).chainOk === true && data(R[26]).chainBreaks === 0,
    JSON.stringify(ok(R[26]) ? data(R[26]) : err(R[26])));

  // C16 — call() never throws or rejects, and never emits an undeclared code.
  const threw = run.results.filter((r) => r.threw);
  const badCodes = run.results.filter((r) => r.result && r.result.ok === false && !DECLARED_CODES.includes(r.result.error.code));
  record('C16', 'call() never throws; only declared error codes emitted',
    threw.length === 0 && badCodes.length === 0,
    `threw=${threw.length} undeclaredCodes=${badCodes.map((b) => b.result.error.code).join(',') || 'none'}`);

  // C17 — the surface still passes its own parity test at the end of the batch.
  record('C17', 'surface parity still holds after the batch',
    ok(R[27]) && data(R[27]).pass === true, JSON.stringify(ok(R[27]) ? data(R[27]).failures : err(R[27])));

  // C18 — nothing was logged to the console. A silent throw inside a handler shows here.
  record('C18', 'no console errors and no page errors during the batch',
    run.consoleErrors.length === 0 && run.pageErrors.length === 0,
    `console=${run.consoleErrors.length} page=${run.pageErrors.length} ${run.consoleErrors.slice(0, 2).join(' | ')}`);

  // C19 — a reversed range is a caller mistake, not an empty period. Found by the
  // adversarial round: gst.gstr1 with periodStart > periodEnd returned ok with every
  // section empty and gt:0, which reads as an authoritative nil filing. Reintroduce by
  // deleting the `range` guard in agentDispatch.
  const rev = [28, 29, 30].map((i) => !ok(R[i]) && err(R[i]).code === 'E_BAD_ARGS');
  record('C19', 'reversed date range refused (gstr1 / dayBook / accountLedger)',
    rev.every(Boolean), `gstr1/dayBook/accountLedger = ${rev.join('/')} (${err(R[28]).code || 'ok:true'})`);

  // C20 — an own `__proto__` key arriving as real JSON must be rejected as an unknown
  // parameter, and must not pollute Object.prototype. Reintroduce by validating with
  // `for (const k in given)` or by skipping the unknown-key loop.
  const protoRejected = !ok(R[31]) && err(R[31]).code === 'E_BAD_ARGS' && !ok(R[32]) && err(R[32]).code === 'E_BAD_ARGS';
  const polluted = ok(R[34]) && Object.prototype.hasOwnProperty.call(data(R[34]), 'polluted');
  const lineProto = R[33] && R[33].result;
  record('C20', "own __proto__ key rejected as unknown param; no prototype pollution",
    protoRejected && !polluted,
    `topLevel=${err(R[31]).code}/${err(R[32]).code} nestedLine=${lineProto && lineProto.ok ? 'posted' : (lineProto && lineProto.error.code)} polluted=${polluted}`);


  // C22 — agentName cannot be shaped into a misleading actor string. Found by both
  // round-2 agents: 'ca:verified' produced actor 'agent:ca:verified', which a reader
  // splitting on ':' reads as the principal 'ca'. Reintroduce by dropping the pattern.
  const forged = [35, 36, 37, 38].map((i) => !ok(R[i]) && err(R[i]).code === 'E_BAD_ARGS');
  const legit = ok(R[39]) && data(R[39]).actor === 'agent:checks-ok_1.2';
  const tail = ok(R[40]) ? data(R[40]).entries : [];
  const noForgedActor = !tail.some((e) => String(e.actor).split(':').length > 2);
  record('C22', 'agentName cannot forge a misleading audit actor',
    forged.every(Boolean) && legit && noForgedActor,
    `colon/multicolon/space/empty = ${forged.join('/')} legitActor=${legit ? data(R[39]).actor : 'FAILED'} tailActors=${tail.map((e) => e.actor).join(',')}`);
  return run;
}

// --- batch 3: a future-format book, which Bahi opens READ-ONLY ---------------
// E_READONLY is a declared error code. A declared code nothing can reach is a claim,
// not a contract — this batch makes it reachable. The book is pharma.khata with its
// manifest's khataFormatVersion bumped past this build; books.sqlite and its hash are
// untouched, so the file is genuine, just from a newer Bahi.
async function batchReadOnly() {
  const future = process.env.BAHI_FUTURE_KHATA;
  if (!future || !fs.existsSync(future)) {
    record('C21', 'read-only file refuses mutations (E_READONLY)', false, 'BAHI_FUTURE_KHATA not set or missing — check skipped');
    return null;
  }
  const run = await runCalls({ book: 'future', bookFile: future, calls: [
    { command: 'agent.health' },
    { command: 'report.trialBalance', args: { asOf: '2026-03-31' } },
    { command: 'journal.post', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'ro' } },
    { command: 'file.save' },
  ] });
  const [health, tb, post, save] = run.results;
  record('C21', 'read-only file: reads work, mutations refused with E_READONLY',
    ok(health) && data(health).readOnly === true && ok(tb) &&
    !ok(post) && err(post).code === 'E_READONLY' && !ok(save) && err(save).code === 'E_READONLY',
    `readOnly=${ok(health) ? data(health).readOnly : '?'} read=${ok(tb)} post=${err(post).code} save=${err(save).code}`);
  return run;
}


// --- batch 4: cross-command reconciliation ---------------------------------
// The checks above ask whether the surface OBEYS ITS CONTRACT. These ask whether it
// TELLS THE TRUTH: each one takes two or three independent computations of the same
// quantity and requires them to agree. They are the ones most likely to catch a future
// engine regression, because no single wrong answer can satisfy both sides.
// Pure reads, on their own session, so nothing this suite posts can perturb them.
async function batchReconcile() {
  const FY_START = '2025-04-01', FY_END = '2026-03-31';
  const Q = [['2025-04-01', '2025-06-30'], ['2025-07-01', '2025-09-30'], ['2025-10-01', '2025-12-31'], ['2026-01-01', '2026-03-31']];
  const M = [];
  for (let i = 0; i < 12; i++) {
    const y = i < 9 ? 2025 : 2026;
    const mo = ((i + 3) % 12) + 1;
    const last = new Date(Date.UTC(mo === 12 ? y + 1 : y, mo === 12 ? 0 : mo, 0)).getUTCDate();
    const mm = String(mo).padStart(2, '0');
    M.push([`${y}-${mm}-01`, `${y}-${mm}-${String(last).padStart(2, '0')}`]);
  }
  const GST_M = ['2025-07-01', '2025-07-31'];
  const PAGE = 7;

  const calls = [
    { command: 'report.dayBook', args: { from: FY_START, to: FY_END } },                    // 0
    ...Q.map(([from, to]) => ({ command: 'report.dayBook', args: { from, to } })),           // 1..4
    ...M.map(([from, to]) => ({ command: 'report.dayBook', args: { from, to } })),           // 5..16
    { command: 'gst.gstr1', args: { periodStart: GST_M[0], periodEnd: GST_M[1] } },          // 17
    { command: 'gst.gstr3b', args: { periodStart: GST_M[0], periodEnd: GST_M[1] } },         // 18
    { command: 'report.trialBalance', args: { asOf: FY_END } },                              // 19
    { command: 'report.balanceSheet', args: { asOf: FY_END } },                              // 20
    { command: 'masters.customers', args: { limit: 1000 } },                                 // 21
  ];
  const PAGE_BASE = calls.length;
  for (let off = 0; off < 8; off++) calls.push({ command: 'masters.customers', args: { limit: PAGE, offset: off * PAGE } });

  const run = await runCalls({ book: 'pharma', calls });
  const R = run.results;
  const rupeesToPaise = (v) => Math.round(Number(v) * 100);

  // C23 — the day book is a PARTITION of its sub-periods. Comparing counts alone would
  // miss a boundary entry counted twice and another dropped; comparing the id sets
  // catches both. Reintroduce by making the range exclusive at one end.
  const idsOf = (i) => (ok(R[i]) ? data(R[i]).entries.map((e) => e.id) : null);
  const year = idsOf(0);
  const gather = (from, count) => {
    const all = [];
    for (let i = from; i < from + count; i++) { const ids = idsOf(i); if (!ids) return null; all.push(...ids); }
    return all;
  };
  const qIds = gather(1, 4), mIds = gather(5, 12);
  const setEq = (a, b) => a && b && a.length === b.length && new Set(a).size === a.length && [...new Set(a)].sort().join() === [...new Set(b)].sort().join();
  const qDup = qIds ? qIds.length - new Set(qIds).size : -1;
  const mDup = mIds ? mIds.length - new Set(mIds).size : -1;
  record('C23', 'day book partitions exactly into quarters and months (no boundary skip or double-count)',
    !!year && setEq(year, qIds) && setEq(year, mIds) && qDup === 0 && mDup === 0,
    `year=${year ? year.length : 'ERR'} quarters=${qIds ? qIds.length : 'ERR'} (dup ${qDup}) months=${mIds ? mIds.length : 'ERR'} (dup ${mDup})`);

  // C24 — three independent aggregations of one month's outward supplies must agree to
  // the paise: GSTR-1's per-party sections, GSTR-1's HSN summary, and GSTR-3B's invoice
  // roll-up. Reintroduce by shifting the GSTR-3B outward total by a single paise.
  let g1Sections = null, g1Hsn = null, g3b = null;
  if (ok(R[17]) && ok(R[18])) {
    const g1 = data(R[17]);
    let sec = 0;
    for (const key of ['b2b', 'b2cl']) {
      for (const party of g1[key] || []) {
        for (const inv of party.inv || []) {
          for (const it of inv.itms || []) sec += rupeesToPaise(it.itm_det.txval);
        }
      }
    }
    for (const row of g1.b2cs || []) sec += rupeesToPaise(row.txval);
    g1Sections = sec;
    g1Hsn = (g1.hsn && g1.hsn.data ? g1.hsn.data : []).reduce((t, r) => t + rupeesToPaise(r.txval), 0);
    g3b = data(R[18]).outward.taxable;
  }
  record('C24', 'GSTR-1 sections, GSTR-1 HSN summary and GSTR-3B agree on outward taxable',
    g1Sections !== null && g1Sections === g3b && g1Hsn === g3b,
    `sections=${g1Sections} hsn=${g1Hsn} gstr3b=${g3b} (July 2025, paise)`);

  // C25 — the balance sheet is a roll-up of the trial balance, so the accounting identity
  // must hold and each section's rows must sum to its own stated total. A sign flip in the
  // roll-up leaves the trial balance tied while the balance sheet stops balancing.
  let bsOk = false, bsDetail = 'call failed';
  if (ok(R[20])) {
    const bs = data(R[20]);
    const sum = (a) => a.reduce((t, r) => t + r.balance, 0);
    const secOk = sum(bs.assets) === bs.totalAssets && sum(bs.liabilities) === bs.totalLiabilities && sum(bs.equity) === bs.totalEquity;
    const identity = bs.totalAssets === bs.totalLiabilities + bs.totalEquity;
    bsOk = secOk && identity;
    bsDetail = `assets=${bs.totalAssets} liab+equity=${bs.totalLiabilities + bs.totalEquity} sectionsSumToTotals=${secOk}`;
  }
  record('C25', 'balance sheet: assets = liabilities + equity, and every section sums to its total', bsOk, bsDetail);

  // C26 — paging is a partition of the full list. Reintroduce with an off-by-one offset:
  // counts alone would still look plausible, the id sequence would not.
  let pageOk = false, pageDetail = 'call failed';
  if (ok(R[21])) {
    const full = data(R[21]);
    const walked = [];
    for (let i = PAGE_BASE; i < calls.length; i++) if (ok(R[i])) walked.push(...data(R[i]).rows.map((r) => r.id));
    const fullIds = full.rows.map((r) => r.id);
    const dup = walked.length - new Set(walked).size;
    pageOk = full.total === fullIds.length && dup === 0 && walked.join() === fullIds.join();
    pageDetail = `total=${full.total} full=${fullIds.length} walked=${walked.length} dup=${dup} orderIdentical=${walked.join() === fullIds.join()}`;
  }
  record('C26', `paging at limit ${PAGE} reproduces the full list exactly, in order, with no gap or repeat`, pageOk, pageDetail);

  // C27 — an account's ledger and its trial-balance row are two different queries over the
  // same lines and must total identically. The accounts are chosen at RUNTIME as the five
  // busiest the trial balance reports: a fixed id passed this check vacuously by comparing
  // two empty sets, which is the failure mode these checks exist to catch. Reintroduce by
  // zeroing the ledger's credit column — the trial balance still shows the credits.
  let ledOk = false, ledDetail = 'trial balance unavailable';
  if (ok(R[19])) {
    const busiest = [...data(R[19]).rows]
      .sort((a, b) => (b.debit + b.credit) - (a.debit + a.credit))
      .slice(0, 5);
    if (!busiest.length) {
      ledDetail = 'no accounts with activity in the sample book — check is vacuous, treat as red';
    } else {
      // One session, so the trial balance and every ledger below are read from the same book.
      const run2 = await runCalls({ book: 'pharma', calls: [
        { command: 'report.trialBalance', args: { asOf: FY_END } },
        ...busiest.map((a) => ({ command: 'report.accountLedger', args: { accountId: a.id, from: '2000-01-01', to: FY_END } })),
      ] });
      const tb2 = ok(run2.results[0]) ? data(run2.results[0]).rows : [];
      const parts = [];
      let allOk = busiest.length > 0;
      for (let i = 0; i < busiest.length; i++) {
        const res = run2.results[i + 1];
        const row = tb2.find((r) => r.id === busiest[i].id);
        if (!ok(res) || !row) { allOk = false; parts.push(`acct ${busiest[i].id}: MISSING`); continue; }
        const lines = data(res).lines;
        const ldr = lines.reduce((t, l) => t + (l.debit || 0), 0);
        const lcr = lines.reduce((t, l) => t + (l.credit || 0), 0);
        // A vacuous comparison is a failure, not a pass: the account was picked BECAUSE
        // the trial balance says it has movement, so an empty ledger is a real mismatch.
        const nonEmpty = lines.length > 0;
        const match = ldr === row.debit && lcr === row.credit && nonEmpty;
        if (!match) allOk = false;
        parts.push(`acct ${row.id} ${match ? 'ok' : `MISMATCH ledger ${ldr}/${lcr} vs tb ${row.debit}/${row.credit}`} (${lines.length} lines)`);
      }
      ledOk = allOk;
      ledDetail = parts.join('; ');
    }
  }
  record('C27', 'account ledger totals equal the trial-balance row, for the 5 busiest accounts', ledOk, ledDetail);

  return run;
}


// --- batch 5: two doors, one core -------------------------------------------
// The reason the voucher engine exists. C28 asserts the form no longer carries its own
// posting path; C29 drives BOTH doors with identical input and requires identical rows.
// A structural check alone would pass a form that calls the engine and then also does
// something extra; a behavioural check alone would pass a form that quietly re-inlined
// the logic and happens to still agree today. Both, or neither is worth much.
async function batchTwoDoors() {
  const src = fs.readFileSync(path.join(REPO, 'index.html'), 'utf8');

  // C28 — the invoice form must delegate. Reintroduce by inlining a posting path back
  // into renderInvoiceForm.
  const formStart = src.indexOf('function renderInvoiceForm(main) {');
  const formEnd = src.indexOf('\nfunction renderInvoices(main) {', formStart);
  const formSrc = formStart > -1 && formEnd > -1 ? src.slice(formStart, formEnd) : '';
  const banned = ['INSERT INTO invoices', 'postInvoiceToLedger(', 'postInvoiceStockEffects(', "db.run('BEGIN')", "STATE.db.run('BEGIN')"];
  const found = banned.filter((b) => formSrc.includes(b));
  record('C28', 'the invoice form delegates: no posting path of its own',
    formSrc.length > 0 && found.length === 0 && formSrc.includes('createInvoice(STATE.db'),
    formSrc.length === 0 ? 'could not locate renderInvoiceForm' : `formBytes=${formSrc.length} callsEngine=${formSrc.includes('createInvoice(STATE.db')} banned=${found.join(',') || 'none'}`);

  // C29 — post the same invoice through the UI form and through window.bahi, then compare
  // the stored rows. Reintroduce by changing anything the agent path does differently.
  const setValSrc = `
    const setVal = (el, v) => {
      const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    };
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));`;

  const UI_POST = `${setValSrc}
    nav('#/invoice/new');
    await sleep(400);
    setVal(document.getElementById('iv-customer'), '1');
    await sleep(150);
    setVal(document.getElementById('iv-date'), '2026-02-11');
    let row = null;
    for (const tr of document.querySelectorAll('table tbody tr')) { if (tr.querySelector('td:nth-child(4) input')) { row = tr; break; } }
    if (!row) return { error: 'no line row found' };
    setVal(row.querySelector('td:nth-child(1) input'), 'Parity probe line');
    setVal(row.querySelector('td:nth-child(2) input'), '3004');
    setVal(row.querySelector('td:nth-child(3) input'), '10');
    setVal(row.querySelector('td:nth-child(4) input'), '150.00');
    const taxSel = row.querySelector('td:nth-child(5) select');
    if (taxSel) setVal(taxSel, '0.12');
    await sleep(250);
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Post invoice & save');
    if (!btn) return { error: 'post button not found' };
    if (btn.disabled) return { error: 'post button disabled — the preview did not compute a total' };
    btn.click();
    await sleep(1800);
    return { route: location.hash };`;

  const READ = (door) => `
    const r = STATE.db.exec('SELECT id, invoice_number, series, customer_id, invoice_date, place_of_supply, place_of_supply_name, subtotal, cgst, sgst, igst, cess, total, notes, status, company_snapshot, customer_snapshot, ledger_entry_id FROM invoices ORDER BY id DESC LIMIT 1');
    if (!r.length) return { door: '${door}', error: 'no invoice rows' };
    const inv = Object.fromEntries(r[0].columns.map((c, i) => [c, r[0].values[0][i]]));
    const lr = STATE.db.exec('SELECT line_no, item_id, description, hsn_sac, hsn_description, quantity, unit, rate, discount, taxable, tax_rate, rate_id, cgst, sgst, igst, cess, total FROM invoice_lines WHERE invoice_id = ? ORDER BY line_no', [inv.id]);
    const lines = lr.length ? lr[0].values.map(v => Object.fromEntries(lr[0].columns.map((c, i) => [c, v[i]]))) : [];
    const er = STATE.db.exec('SELECT account_id, account_name, debit, credit FROM entry_lines WHERE entry_id = ? ORDER BY id', [inv.ledger_entry_id]);
    const entry = er.length ? er[0].values.map(v => Object.fromEntries(er[0].columns.map((c, i) => [c, v[i]]))) : [];
    const ar = STATE.db.exec('SELECT actor FROM audit_log ORDER BY id DESC LIMIT 1');
    return { door: '${door}', inv, lines, entry, actor: ar.length ? ar[0].values[0][0] : null };`;

  const run = await runCalls({ book: 'pharma', calls: [
    { evalJs: UI_POST, label: 'ui-post' },
    { evalJs: READ('ui'), label: 'ui-read' },
    { command: 'invoice.create', args: { customerId: 1, invoiceDate: '2026-02-11', agentName: 'parity',
        lines: [{ description: 'Parity probe line', hsnSac: '3004', quantity: 10, rate: 15000, taxRate: 0.12 }] } },
    { evalJs: READ('agent'), label: 'agent-read' },
  ] });

  const uiPost = run.results[0].value || {};
  const ui = run.results[1].value || {};
  const agentCall = run.results[2];
  const ag = run.results[3].value || {};

  // id, number and ledger_entry_id must differ — they are two different invoices.
  const VOLATILE = new Set(['id', 'invoice_number', 'ledger_entry_id']);
  const diffs = [];
  if (ui.inv && ag.inv) {
    for (const k of Object.keys(ui.inv)) if (!VOLATILE.has(k) && ui.inv[k] !== ag.inv[k]) diffs.push(`inv.${k}: ${JSON.stringify(ui.inv[k])} vs ${JSON.stringify(ag.inv[k])}`);
    if (ui.lines.length !== ag.lines.length) diffs.push(`lineCount ${ui.lines.length} vs ${ag.lines.length}`);
    else ui.lines.forEach((l, i) => { for (const k of Object.keys(l)) if (l[k] !== ag.lines[i][k]) diffs.push(`line[${i}].${k}: ${JSON.stringify(l[k])} vs ${JSON.stringify(ag.lines[i][k])}`); });
    if (ui.entry.length !== ag.entry.length) diffs.push(`ledgerLegs ${ui.entry.length} vs ${ag.entry.length}`);
    else ui.entry.forEach((e, i) => { for (const k of Object.keys(e)) if (e[k] !== ag.entry[i][k]) diffs.push(`entry[${i}].${k}: ${JSON.stringify(e[k])} vs ${JSON.stringify(ag.entry[i][k])}`); });
  }

  const bothPosted = !uiPost.error && !!ui.inv && ok(agentCall) && !!ag.inv;
  // The books must match; the ATTRIBUTION must not. A form post is the owner's, an agent
  // post is the agent's — identical rows, different hands, and the log has to say so.
  const attribution = ui.actor === 'owner' && ag.actor === 'agent:parity';
  const nonTrivial = !!ui.inv && ui.inv.total > 0 && ui.lines.length > 0 && ui.entry.length >= 3;

  record('C29', 'the form and window.bahi produce identical invoices, with different audit actors',
    bothPosted && diffs.length === 0 && attribution && nonTrivial,
    bothPosted
      ? `total=${ui.inv.total} lines=${ui.lines.length} legs=${ui.entry.length} diffs=${diffs.length ? diffs.join(' | ') : 'none'} actors=${ui.actor}/${ag.actor}`
      : `ui=${uiPost.error || (ui.error || 'ok')} agent=${ok(agentCall) ? 'ok' : JSON.stringify(err(agentCall))}`);

  return run;
}

const r1 = await batchNoFile();
const r2 = await batchSample();
const r3 = await batchReadOnly();
const r4 = await batchReconcile();
const r5 = await batchTwoDoors();

const shown = only ? results.filter((r) => r.id === only) : results;
let red = 0;
for (const r of shown) {
  if (!r.pass) red++;
  process.stdout.write(`${r.pass ? 'PASS' : 'FAIL'}  ${r.id.padEnd(4)} ${r.title}\n`);
  // Print the evidence for green checks too, not just red ones. A suite that shows only
  // the word PASS asks to be trusted; one that shows the numbers it compared can be read.
  if (r.detail) process.stdout.write(`             ${r.detail}\n`);
}
process.stdout.write(`\n${shown.length - red}/${shown.length} green${red ? `, ${red} RED` : ''}\n`);
process.exit(red ? 1 : 0);
