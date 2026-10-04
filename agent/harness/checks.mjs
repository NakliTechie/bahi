// Bahi agent-surface checks
// =========================
// The assertion suite that guards Bahi's agent face. Every check here has been proven able
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
const DECLARED_CODES = ['E_UNKNOWN_TOOL', 'E_PERSON_ONLY', 'E_BAD_ARGS', 'E_NO_FILE', 'E_READONLY', 'E_NOT_FOUND', 'E_LIMIT', 'E_ENGINE', 'E_INTERNAL'];

const only = (() => { const i = process.argv.indexOf('--only'); return i > -1 ? process.argv[i + 1].split(',') : null; })();

// Which checks a batch covers, so a targeted run launches only the browsers it needs.
// The defect-prover runs one defect at a time; before this it paid for all eight browser
// sessions to evaluate a single check, which is what saturated the machine.
const BATCH_CHECKS = {
  noFile:     ['C1', 'C2', 'C3', 'C4', 'C5'],
  sample:     ['C6', 'C7', 'C8', 'C9', 'C10', 'C11', 'C12', 'C13', 'C14', 'C15', 'C16', 'C17', 'C18', 'C19', 'C20', 'C22', 'C42'],
  readOnly:   ['C21'],
  reconcile:  ['C23', 'C24', 'C25', 'C26', 'C27'],
  structural: ['C28', 'C30', 'C33', 'C34', 'C35', 'C43'],
  parity:     ['C29', 'C31'],
  signing:    ['C32'],
  doors:      ['C36', 'C37', 'C38', 'C39', 'C40', 'C41'],
};
const wants = (batch) => !only || BATCH_CHECKS[batch].some((c) => only.includes(c));

const results = [];
function record(id, title, pass, detail) { results.push({ id, title, pass, detail }); }

const ok = (r) => r.result && r.result.ok === true;
const err = (r) => (r.result && r.result.error) || {};
const data = (r) => (r.result && r.result.data) || {};

// --- batch 1: no file open -------------------------------------------------
async function batchNoFile() {
  const run = await runCalls({ book: 'none', calls: [
    { command: 'run_selftest' },
    { command: 'describe_tools' },
    { command: '__nope__' },
    { command: 'get_trial_balance', args: { asOf: '2026-03-31' } },
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 1 }, { accountId: 2, credit: 1 }] } },
  ] });
  const [selftest, manifest, unknown, tb, post] = run.results;

  // C1 — the two doors name the same commands, and every UI route is covered or
  // declared a gap. Reintroduce by deleting a handler or adding an undeclared one.
  record('C1', 'manifest/dispatcher/route parity (run_selftest)',
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
  record('C3', 'unknown command -> E_UNKNOWN_TOOL',
    !ok(unknown) && err(unknown).code === 'E_UNKNOWN_TOOL', JSON.stringify(err(unknown)));

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
  const POST = (lines, extra = {}) => ({ command: 'post_journal', args: { lines, agentName: 'checks', postedAt: '2025-06-15', ...extra } });
  const run = await runCalls({ book: 'pharma', calls: [
    { command: 'get_file_info' },                                                   // 0  baseline
    { command: 'get_trial_balance', args: { asOf: '2026-03-31' } },           // 1
    { command: 'list_customers', args: { limit: 5 } },                       // 2
    { command: 'list_customers', args: { q: "' OR 1=1 --", limit: 5 } },     // 3  injection
    { command: 'list_customers', args: { q: "'; DROP TABLE customers; --" } }, // 4 injection
    { command: 'list_customers', args: { limit: 5 } },                       // 5  table survived?
    { command: 'get_file_info' },                                                   // 6  reads pure?
    { command: 'get_day_book', args: { from: '2026-13-01', to: '2026-03-31' } }, // 7  bad month
    { command: 'get_day_book', args: { from: '2026-02-30', to: '2026-03-31' } }, // 8  bad day
    { command: 'get_trial_balance', args: { asOf: 1 } },                      // 9  wrong type
    { command: 'list_customers', args: { limit: 0 } },                       // 10 below min
    { command: 'list_customers', args: { limit: 99999 } },                   // 11 above max
    { command: 'list_customers', args: { nope: 1 } },                        // 12 unknown param
    { command: 'list_customers', args: [] },                                 // 13 args not an object
    POST([{ accountId: 1, debit: 100 }, { accountId: 2, credit: 99 }]),         // 14 unbalanced
    POST([{ accountId: 1, debit: 100 }]),                                       // 15 one line
    POST([{ accountId: 1, debit: 2147483648 }, { accountId: 2, credit: 2147483648 }]), // 16 over ceiling
    POST([{ accountId: 1, debit: 1.5 }, { accountId: 2, credit: 1.5 }]),        // 17 float paise
    POST([{ accountId: 1, debit: -100 }, { accountId: 2, credit: -100 }]),      // 18 negative
    POST([{ accountId: 'x', debit: 100 }, { accountId: 2, credit: 100 }]),      // 19 bad accountId
    POST(['not-an-object', { accountId: 2, credit: 100 }]),                     // 20 line not object
    { command: 'navigate', args: { route: 'javascript:alert(1)' } },         // 21 bogus route
    { command: 'get_day_book', args: { from: '2026-03-31', to: '2025-04-01' } }, // 22 reversed range
    { command: 'list_audit_entries', args: { limit: 3 } },                          // 23 pre-post tail
    POST([{ accountId: 1, debit: 12345 }, { accountId: 2, credit: 12345 }], { narration: 'checks attribution probe' }), // 24 the one good post
    { command: 'list_audit_entries', args: { limit: 3 } },                          // 25 post-post tail
    { command: 'verify_integrity' },                                        // 26 chain intact
    { command: 'run_selftest' },                                              // 27 surface intact
    { command: 'get_gstr1', args: { periodStart: '2025-04-30', periodEnd: '2025-04-01' } },   // 28 reversed period
    { command: 'get_day_book', args: { from: '2026-03-31', to: '2025-04-01' } },            // 29 reversed range
    { command: 'get_account_ledger', args: { accountId: 1, from: '2026-03-31', to: '2025-04-01' } }, // 30
    // Delivered as literal JSON text so `__proto__` arrives as an OWN property, the
    // way it would over a real wire. Structured clone drops it and tests nothing.
    { command: 'list_customers', argsJson: '{"__proto__":{"polluted":"yes"},"limit":2}' },  // 31
    { command: 'get_status', argsJson: '{"__proto__":{"limit":1}}' },                        // 32
    { command: 'post_journal', argsJson: '{"lines":[{"accountId":1,"debit":1000,"__proto__":{"credit":1000}},{"accountId":2,"credit":1000}],"agentName":"proto"}' }, // 33
    { command: 'get_status' },                                                               // 34 pollution visible?
    // Attribution forgery: ':' is the actor field's own separator and the audit log
    // already carries 'owner' / 'ca' / 'ai' / 'system' as real principals.
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'ca:verified' } },  // 35
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'owner:ca:ai' } },  // 36
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'a b' } },          // 37
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: '' } },             // 38
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'checks-ok_1.2' } },// 39 must succeed
    { command: 'list_audit_entries', args: { limit: 5 } },                                                                                     // 40
    ...[1, 2, 3, 4].map((quarter) => ({ command: 'get_form26q', args: { fyStartYear: 2025, quarter } })),                                   // 41..44
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

  // C12 — navigate only accepts routes the app actually has.
  record('C12', 'navigate refuses a route outside the route index',
    !ok(R[21]) && err(R[21]).code === 'E_BAD_ARGS', JSON.stringify(err(R[21])));

  // C13 — an agent write is attributable in the append-only audit log.
  // Reintroduce by dropping the actor stamp in post_journal.
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
  // adversarial round: get_gstr1 with periodStart > periodEnd returned ok with every
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

  // C42 — a TDS quarter is the statutory calendar quarter, in IST. fyQuarterRange built each
  // bound as a local-midnight Date and converted it with toISOString(), which in IST lands on
  // the previous day: Q1 ran 31 Mar – 29 Jun, so 30 June's TDS went into Q2 and 31 March's
  // into the next financial year. Reintroduce by restoring the toISOString() construction.
  const WANT = [['2025-04-01', '2025-06-30'], ['2025-07-01', '2025-09-30'], ['2025-10-01', '2025-12-31'], ['2026-01-01', '2026-03-31']];
  const got = [41, 42, 43, 44].map((i) => (ok(R[i]) && data(R[i]).range ? [data(R[i]).range.start, data(R[i]).range.end] : null));
  record('C42', 'TDS quarters are the calendar quarters Apr–Jun … Jan–Mar, evaluated in IST',
    got.every((g, i) => g && g[0] === WANT[i][0] && g[1] === WANT[i][1]),
    got.map((g, i) => `Q${i + 1} ${g ? g.join('..') : 'ERR'}`).join(' '));
  return run;
}

// --- batch 3: a future-format book, which Bahi opens READ-ONLY ---------------
// E_READONLY is a declared error code. A declared code nothing can reach is a claim,
// not a contract — this batch makes it reachable. The book is pharma.khata with its
// manifest's khataFormatVersion bumped past this build; books.sqlite and its hash are
// untouched, so the file is genuine, just from a newer Bahi.
async function batchReadOnly() {
  // The book is pharma.khata with its manifest's khataFormatVersion bumped past this
  // build, rewritten in-page. books.sqlite and its signed hash are untouched, so the file
  // is genuine — just from a newer Bahi. E_READONLY is a declared error code, and a
  // declared code nothing can reach is a claim, not a contract.
  const run = await runCalls({ book: 'pharma', futureFormat: true, calls: [
    { command: 'get_status' },
    { command: 'get_trial_balance', args: { asOf: '2026-03-31' } },
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 100 }, { accountId: 2, credit: 100 }], agentName: 'ro' } },
    { command: 'save_file' },
  ] });
  const [health, tb, post, save] = run.results;
  // Refused at the CALL, not after approval: the person must never be asked to approve a
  // write the open file cannot take. A write that stages here has already failed this check.
  record('C21', 'read-only file: reads work, writes refused with E_READONLY before any proposal',
    ok(health) && data(health).readOnly === true && ok(tb) &&
    !ok(post) && err(post).code === 'E_READONLY' && !post.staged &&
    !ok(save) && err(save).code === 'E_READONLY' && !save.staged,
    `readOnly=${ok(health) ? data(health).readOnly : '?'} read=${ok(tb)} post=${err(post).code}${post.staged ? ' (staged first)' : ''} save=${err(save).code}${save.staged ? ' (staged first)' : ''}`);
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
    { command: 'get_day_book', args: { from: FY_START, to: FY_END } },                    // 0
    ...Q.map(([from, to]) => ({ command: 'get_day_book', args: { from, to } })),           // 1..4
    ...M.map(([from, to]) => ({ command: 'get_day_book', args: { from, to } })),           // 5..16
    { command: 'get_gstr1', args: { periodStart: GST_M[0], periodEnd: GST_M[1] } },          // 17
    { command: 'get_gstr3b', args: { periodStart: GST_M[0], periodEnd: GST_M[1] } },         // 18
    { command: 'get_trial_balance', args: { asOf: FY_END } },                              // 19
    { command: 'get_balance_sheet', args: { asOf: FY_END } },                              // 20
    { command: 'list_customers', args: { limit: 1000 } },                                 // 21
  ];
  const PAGE_BASE = calls.length;
  for (let off = 0; off < 8; off++) calls.push({ command: 'list_customers', args: { limit: PAGE, offset: off * PAGE } });

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
        { command: 'get_trial_balance', args: { asOf: FY_END } },
        ...busiest.map((a) => ({ command: 'get_account_ledger', args: { accountId: a.id, from: '2000-01-01', to: FY_END } })),
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
// The reason the voucher engine exists. For each voucher type: a structural check that
// the form carries no posting path of its own, and a behavioural check that posts the
// SAME voucher through the form and through window.bahi and compares the stored rows.
//
// Either check alone is weak. Structural alone would pass a form that calls the engine
// and then also does something extra. Behavioural alone would pass a form that quietly
// re-inlined the logic and happens to still agree today. Together they hold.

const SET_VAL = `
  // Fire BOTH events, the way a real user does. Some fields bind on 'input' (they read
  // the element back at submit time) and some on 'change' (they update the form's own
  // state object). Firing only one silently skipped place-of-supply and made the parity
  // check compare two different inputs — a harness bug that looked exactly like a product bug.
  const setVal = (el, v) => {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const fillLine = (cells) => {
    let row = null;
    for (const tr of document.querySelectorAll('table tbody tr')) { if (tr.querySelector('td:nth-child(4) input')) { row = tr; break; } }
    if (!row) return 'no line row found';
    setVal(row.querySelector('td:nth-child(1) input'), cells.description);
    setVal(row.querySelector('td:nth-child(2) input'), cells.hsn);
    setVal(row.querySelector('td:nth-child(3) input'), cells.qty);
    setVal(row.querySelector('td:nth-child(4) input'), cells.rate);
    const taxSel = row.querySelector('td:nth-child(5) select');
    if (taxSel) setVal(taxSel, cells.tax);
    return null;
  };`;

// One voucher type's parity spec: how to drive its form, how to read the row back, and
// what the agent call is that should match.
const VOUCHERS = [
  {
    id: 'invoice', checkStructural: 'C28', checkParity: 'C29',
    formFn: 'renderInvoiceForm',
    engineCall: 'createInvoice(STATE.db',
    banned: ['INSERT INTO invoices', 'postInvoiceToLedger(', 'postInvoiceStockEffects(', "STATE.db.run('BEGIN')"],
    uiScript: `${SET_VAL}
      nav('#/invoice/new'); await sleep(400);
      setVal(document.getElementById('iv-customer'), '1'); await sleep(150);
      setVal(document.getElementById('iv-date'), '2026-02-11');
      const e = fillLine({ description: 'Parity probe line', hsn: '3004', qty: '10', rate: '150.00', tax: '0.12' });
      if (e) return { error: e };
      await sleep(250);
      const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Post invoice & save');
      if (!btn) return { error: 'post button not found' };
      if (btn.disabled) return { error: 'post button disabled — the preview computed no total' };
      btn.click(); await sleep(1800);
      return { route: location.hash };`,
    readSql: {
      head: "SELECT id, invoice_number, series, customer_id, invoice_date, place_of_supply, place_of_supply_name, subtotal, cgst, sgst, igst, cess, total, notes, status, company_snapshot, customer_snapshot, ledger_entry_id FROM invoices ORDER BY id DESC LIMIT 1",
      lines: "SELECT line_no, item_id, description, hsn_sac, hsn_description, quantity, unit, rate, discount, taxable, tax_rate, rate_id, cgst, sgst, igst, cess, total FROM invoice_lines WHERE invoice_id = ? ORDER BY line_no",
      volatile: ['id', 'invoice_number', 'ledger_entry_id'],
    },
    agentCall: { command: 'create_invoice', args: { customerId: 1, invoiceDate: '2026-02-11', agentName: 'parity',
      lines: [{ description: 'Parity probe line', hsnSac: '3004', quantity: 10, rate: 15000, taxRate: 0.12 }] } },
  },
  {
    id: 'purchase', checkStructural: 'C30', checkParity: 'C31',
    formFn: 'renderPurchaseForm',
    engineCall: 'createPurchase(STATE.db',
    banned: ['INSERT INTO purchases', 'postPurchaseToLedger(', 'postPurchaseStockEffects(', "STATE.db.run('BEGIN')"],
    uiScript: `${SET_VAL}
      nav('#/purchase/new'); await sleep(400);
      setVal(document.getElementById('pu-vendor'), '1'); await sleep(150);
      setVal(document.getElementById('pu-bill'), 'VB-PARITY-UI');
      setVal(document.getElementById('pu-date'), '2026-02-12');
      setVal(document.getElementById('pu-pos'), 'MH');
      await sleep(150);
      const e = fillLine({ description: 'API bulk drum', hsn: '2941', qty: '5', rate: '2500.00', tax: '0.18' });
      if (e) return { error: e };
      await sleep(250);
      const btn = [...document.querySelectorAll('button')].find(b => /Post purchase/i.test(b.textContent.trim()));
      if (!btn) return { error: 'post button not found: ' + [...document.querySelectorAll('button')].map(b => b.textContent.trim()).join('|') };
      if (btn.disabled) return { error: 'post button disabled — the preview computed no total' };
      btn.click(); await sleep(1800);
      return { route: location.hash };`,
    readSql: {
      head: "SELECT id, bill_number, internal_ref, vendor_id, bill_date, place_of_supply, place_of_supply_name, reverse_charge, itc_eligible, subtotal, cgst, sgst, igst, cess, total, notes, status, company_snapshot, vendor_snapshot, ledger_entry_id FROM purchases ORDER BY id DESC LIMIT 1",
      lines: "SELECT line_no, item_id, description, hsn_sac, quantity, rate, taxable, tax_rate, rate_id, cgst, sgst, igst, cess, itc_eligible, total FROM purchase_lines WHERE purchase_id = ? ORDER BY line_no",
      // bill_number is the vendor's own number and differs per document, as does the
      // generated internal_ref — two different purchases, deliberately.
      volatile: ['id', 'bill_number', 'internal_ref', 'ledger_entry_id'],
    },
    agentCall: { command: 'create_purchase', args: { vendorId: 1, billNumber: 'VB-PARITY-API', billDate: '2026-02-12',
      placeOfSupply: 'MH', agentName: 'parity',
      lines: [{ description: 'API bulk drum', hsnSac: '2941', quantity: 5, rate: 250000, taxRate: 0.18 }] } },
  },
];

// Forms that delegate but carry no behavioural parity check. Each behavioural check costs
// two browser sessions in every suite run and every defect-prover iteration, so parity is
// proven on the two vouchers with the most computation (invoice, purchase) and the rest are
// held structurally. That is a trade-off, not an oversight — see the run record.
const STRUCTURAL_ONLY = [
  { id: 'payment', check: 'C33', formFn: 'renderPaymentForm', engineCall: 'createPayment(STATE.db',
    banned: ['INSERT INTO payments', 'postPaymentToLedger(', "STATE.db.run('BEGIN')"] },
  { id: 'credit note', check: 'C34', formFn: 'renderCreditNoteForm', engineCall: 'createCreditNote(STATE.db',
    banned: ['INSERT INTO credit_notes', 'postCreditNoteToLedger(', 'postCreditNoteStockEffects(', "STATE.db.run('BEGIN')"] },
  { id: 'debit note', check: 'C35', formFn: 'renderDebitNoteForm', engineCall: 'createDebitNote(STATE.db',
    banned: ['INSERT INTO debit_notes', 'postDebitNoteToLedger(', 'postDebitNoteStockEffects(', "STATE.db.run('BEGIN')"] },
];

// Structural half — reads index.html and nothing else. No browser, no book, no server.
// Separated from the behavioural half so proving a structural check costs milliseconds.
async function batchStructural() {
  const src = fs.readFileSync(path.join(REPO, 'index.html'), 'utf8');

  const formSourceOf = (formFn) => {
    const a = src.indexOf(`function ${formFn}(`);
    if (a < 0) return '';
    const m = src.slice(a + 10).match(/\nfunction [A-Za-z0-9_]+\(/);
    return m ? src.slice(a, a + 10 + m.index) : '';
  };

  for (const v of STRUCTURAL_ONLY) {
    const formSrc = formSourceOf(v.formFn);
    const found = v.banned.filter((t) => formSrc.includes(t));
    record(v.check, `the ${v.id} form delegates: no posting path of its own`,
      formSrc.length > 0 && found.length === 0 && formSrc.includes(v.engineCall),
      formSrc.length === 0 ? `could not locate ${v.formFn}` : `formBytes=${formSrc.length} callsEngine=${formSrc.includes(v.engineCall)} banned=${found.join(',') || 'none'}`);
  }

  // C43 — CMP-08 takes its quarter from fyQuarterRange, the one function C42 holds to the
  // calendar. Its own copy of the date arithmetic had the same IST shift.
  const cmp = formSourceOf('renderCmp08');
  record('C43', 'CMP-08 derives its quarter from fyQuarterRange, with no date arithmetic of its own',
    cmp.length > 0 && cmp.includes('fyQuarterRange(') && !cmp.includes('toISOString()'),
    cmp.length === 0 ? 'could not locate renderCmp08' : `usesShared=${cmp.includes('fyQuarterRange(')} ownToISOString=${cmp.includes('toISOString()')}`);

  for (const v of VOUCHERS) {
    // Structural: the form delegates and carries no posting path of its own.
    const a = src.indexOf(`function ${v.formFn}(`);
    const rest = a > -1 ? src.slice(a + 10) : '';
    const m = rest.match(/\nfunction [A-Za-z0-9_]+\(/);
    const formSrc = (a > -1 && m) ? src.slice(a, a + 10 + m.index) : '';
    const found = v.banned.filter((t) => formSrc.includes(t));
    record(v.checkStructural, `the ${v.id} form delegates: no posting path of its own`,
      formSrc.length > 0 && found.length === 0 && formSrc.includes(v.engineCall),
      formSrc.length === 0 ? `could not locate ${v.formFn}` : `formBytes=${formSrc.length} callsEngine=${formSrc.includes(v.engineCall)} banned=${found.join(',') || 'none'}`);
  }
  return null;
}

// Behavioural half — drives both doors in a real browser. One session per voucher.
async function batchParity() {
  for (const v of VOUCHERS) {
    // Behavioural: same voucher, both doors, compare every stored field.
    const READ = (door) => `
      const r = STATE.db.exec(${JSON.stringify(v.readSql.head)});
      if (!r.length) return { door: '${door}', error: 'no rows' };
      const head = Object.fromEntries(r[0].columns.map((c, i) => [c, r[0].values[0][i]]));
      const lr = STATE.db.exec(${JSON.stringify(v.readSql.lines)}, [head.id]);
      const lines = lr.length ? lr[0].values.map(x => Object.fromEntries(lr[0].columns.map((c, i) => [c, x[i]]))) : [];
      const er = STATE.db.exec('SELECT account_id, account_name, debit, credit FROM entry_lines WHERE entry_id = ? ORDER BY id', [head.ledger_entry_id]);
      const entry = er.length ? er[0].values.map(x => Object.fromEntries(er[0].columns.map((c, i) => [c, x[i]]))) : [];
      const ar = STATE.db.exec('SELECT actor FROM audit_log ORDER BY id DESC LIMIT 1');
      return { door: '${door}', head, lines, entry, actor: ar.length ? ar[0].values[0][0] : null };`;

    const run = await runCalls({ book: 'pharma', calls: [
      { evalJs: v.uiScript, label: 'ui-post' },
      { evalJs: READ('ui'), label: 'ui-read' },
      v.agentCall,
      { evalJs: READ('agent'), label: 'agent-read' },
    ] });

    const uiPost = run.results[0].value || {};
    const ui = run.results[1].value || {};
    const agentCall = run.results[2];
    const ag = run.results[3].value || {};
    const VOLATILE = new Set(v.readSql.volatile);
    const diffs = [];
    if (ui.head && ag.head) {
      for (const k of Object.keys(ui.head)) if (!VOLATILE.has(k) && ui.head[k] !== ag.head[k]) diffs.push(`${k}: ${JSON.stringify(ui.head[k])} vs ${JSON.stringify(ag.head[k])}`);
      if (ui.lines.length !== ag.lines.length) diffs.push(`lineCount ${ui.lines.length} vs ${ag.lines.length}`);
      else ui.lines.forEach((l, i) => { for (const k of Object.keys(l)) if (l[k] !== ag.lines[i][k]) diffs.push(`line[${i}].${k}: ${JSON.stringify(l[k])} vs ${JSON.stringify(ag.lines[i][k])}`); });
      if (ui.entry.length !== ag.entry.length) diffs.push(`ledgerLegs ${ui.entry.length} vs ${ag.entry.length}`);
      else ui.entry.forEach((e, i) => { for (const k of Object.keys(e)) if (e[k] !== ag.entry[i][k]) diffs.push(`entry[${i}].${k}: ${JSON.stringify(e[k])} vs ${JSON.stringify(ag.entry[i][k])}`); });
    }
    const bothPosted = !uiPost.error && !!ui.head && ok(agentCall) && !!ag.head;
    // Identical books, different hands — and the log must say which.
    const attribution = ui.actor === 'owner' && ag.actor === 'agent:parity';
    const nonTrivial = !!ui.head && ui.head.total > 0 && ui.lines.length > 0 && ui.entry.length >= 3;

    record(v.checkParity, `the ${v.id} form and window.bahi produce identical rows, with different audit actors`,
      bothPosted && diffs.length === 0 && attribution && nonTrivial,
      bothPosted
        ? `total=${ui.head.total} lines=${ui.lines.length} legs=${ui.entry.length} diffs=${diffs.length ? diffs.join(' | ') : 'none'} actors=${ui.actor}/${ag.actor}`
        : `ui=${uiPost.error || ui.error || 'ok'} agent=${ok(agentCall) ? 'ok' : JSON.stringify(err(agentCall))}`);
  }
  return null;
}


// --- batch 6: signing keys survive a save -----------------------------------
// Found while exercising the voucher engine: opening a file on a new browser and saving
// it dropped the ORIGINAL signer from the trusted-key set, so every historical audit
// entry failed signature verification from that moment on. The audit log's per-entry
// signatures are the tamper evidence; losing them silently is the worst kind of failure.
async function batchSigningKeys() {
  const run = await runCalls({ book: 'pharma', calls: [
    { command: 'verify_integrity' },
    { command: 'post_journal', args: { lines: [{ accountId: 1, debit: 500 }, { accountId: 2, credit: 500 }], agentName: 'keys' } },
    { command: 'save_file' },
    { command: 'verify_integrity' },
  ] });
  const [before, , save, after] = run.results;

  // C32 — after a save on a browser the file has not seen before, EVERY entry still
  // verifies: the historical ones against the original signer, the new ones against this
  // browser's key. Reintroduce by re-homing integrity.signedBy before banking the outgoing
  // signer, which is the ordering the bug had.
  const b = ok(before) ? data(before) : null;
  const a = ok(after) ? data(after) : null;
  record('C32', 'a save keeps every historical signature verifiable (outgoing signer stays trusted)',
    !!a && ok(save) && a.chainOk === true && a.signaturesBad === 0 && a.signaturesOk === a.entries && a.entries > 1000,
    b && a ? `before ${b.signaturesOk}/${b.entries} ok (${b.signaturesBad} bad) -> after ${a.signaturesOk}/${a.entries} ok (${a.signaturesBad} bad)` : 'call failed');

  return run;
}

// --- batch 7: the doors and the approval gate --------------------------------
// v2 of the agent face. A write call stages a proposal and touches nothing until the person
// approves it; person-only acts are refused on every door; an applied write records its
// door, caller, proposal and approver; the cross-tab channel is closed until the person
// opens it; WebMCP carries exactly the tools describe_tools lists. One session, with a fake
// WebMCP host installed before the app loads. Each step drives the page directly, because
// approving is the person's act and has no tool.
const JOURNAL = (amount, agentName, postedAt) => JSON.stringify({ lines: [{ accountId: 1, debit: amount }, { accountId: 2, credit: amount }], agentName, postedAt });
const COUNTS = `
  const count = () => STATE.db.exec('SELECT COUNT(*) FROM entries')[0].values[0][0];
  const auditMax = () => STATE.db.exec('SELECT MAX(id) FROM audit_log')[0].values[0][0];`;

async function batchDoors() {
  const run = await runCalls({ book: 'pharma', fakeModelContext: true, calls: [
    { label: 'stage', evalJs: `${COUNTS}
      const e0 = count(), a0 = auditMax();
      const staged = await bahi.call('post_journal', ${JOURNAL(777, 'stage', '2025-06-16')});
      const e1 = count(), a1 = auditMax();
      const pid = staged.ok && staged.data ? staged.data.proposalId : null;
      const pend = pid ? await bahi.call('get_proposal', { proposalId: pid }) : null;
      const listed = await bahi.call('list_proposals', { status: 'pending' });
      if (pid) await approveAgentProposal(pid);
      const after = pid ? await bahi.call('get_proposal', { proposalId: pid }) : null;
      return { staged, e0, e1, e2: count(), a0, a1, pend, listed: listed.ok ? listed.data.proposals.length : -1, after };` },
    { label: 'decide', evalJs: `${COUNTS}
      const e0 = count();
      const r1 = await bahi.call('post_journal', ${JOURNAL(111, 'rejected', '2025-06-17')});
      const id1 = r1.ok && r1.data ? r1.data.proposalId : null;
      rejectAgentProposal(id1);
      await approveAgentProposal(id1);              // approving a rejected proposal must do nothing
      const v1 = await bahi.call('get_proposal', { proposalId: id1 });
      const r2 = await bahi.call('post_journal', ${JOURNAL(222, 'withdrawn', '2025-06-17')});
      const id2 = r2.ok && r2.data ? r2.data.proposalId : null;
      const w = await bahi.call('withdraw_proposal', { proposalId: id2 });
      await approveAgentProposal(id2);              // nor approving a withdrawn one
      const v2 = await bahi.call('get_proposal', { proposalId: id2 });
      const w2 = await bahi.call('withdraw_proposal', { proposalId: id2 });
      const nf = await bahi.call('get_proposal', { proposalId: 'prop_nope' });
      return { e0, e1: count(), v1, w, v2, w2, nf };` },
    { label: 'person-only', evalJs: `
      const tries = [await bahi.call('approve_proposal', {}), await bahi.call('run_sql', { sql: 'DELETE FROM entries' }), await bahi.call('set_agent_channel', {})];
      const m = await bahi.call('describe_tools');
      const names = m.data.tools.map((t) => t.name);
      const person = m.data.personOnly.map((p) => p.name);
      const exposed = person.filter((n) => names.includes(n) || Object.keys(bahi.tools).includes(n) || (window.__mcTools || []).some((d) => d.name === n));
      return { codes: tries.map((r) => (r.ok ? 'ok' : r.error.code)), exposed, person: person.length };` },
    { label: 'attribution', evalJs: `
      const r = await bahi.call('post_journal', ${JOURNAL(4242, 'attrib', '2025-06-18')}, { caller: 'checks-caller' });
      const id = r.ok && r.data ? r.data.proposalId : null;
      await approveAgentProposal(id);
      const tail = await bahi.call('list_audit_entries', { limit: 1, includePayload: true });
      const e = tail.ok ? tail.data.entries[0] : {};
      const chain = await bahi.call('verify_integrity');
      return { id, actor: e.actor, action: e.action, agentCall: (e.payload && e.payload.agentCall) || null, chainOk: chain.ok && chain.data.chainOk, breaks: chain.ok ? chain.data.chainBreaks : -1 };` },
    { label: 'channel', evalJs: `
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const peer = new BroadcastChannel('bahi-agent');
      const inbox = [];
      peer.onmessage = (ev) => inbox.push(ev.data);
      peer.postMessage({ type: 'bahi:discover', id: 'd1' });
      await sleep(300);
      const closedReplies = inbox.filter((m) => m.id === 'd1').length;
      setAgentChannel(true);
      peer.postMessage({ type: 'bahi:discover', id: 'd2' });
      await sleep(300);
      const here = inbox.find((m) => m.type === 'bahi:here' && m.id === 'd2');
      const tab = here ? here.tab : null;
      peer.postMessage({ type: 'bahi:call', id: 'c1', target: tab, tool: 'get_status', args: {}, caller: 'peer-tab' });
      peer.postMessage({ type: 'bahi:call', id: 'c2', target: tab, tool: 'post_journal', args: ${JOURNAL(333, 'peer', '2025-06-19')}, caller: 'peer-tab' });
      peer.postMessage({ type: 'bahi:call', id: 'c3', target: 'tab_someone_else', tool: 'get_status', args: {} });
      await sleep(1000);
      const res = (id) => inbox.find((m) => m.type === 'bahi:result' && m.id === id);
      const c1 = res('c1'), c2 = res('c2'), c3 = res('c3');
      const pid = c2 && c2.result.ok ? c2.result.data.proposalId : null;
      const prop = pid ? BAHI_AGENT.proposals.get(pid) : null;
      setAgentChannel(false);
      peer.close();
      return { closedReplies, tab, ownTab: BAHI_AGENT.tab, c1ok: !!(c1 && c1.result.ok), c2status: c2 && c2.result.ok ? c2.result.data.status : null, c3answered: !!c3, door: prop ? prop.door : null, caller: prop ? prop.caller : null };` },
    { label: 'webmcp', evalJs: `
      const regs = window.__mcTools || [];
      const m = await bahi.call('describe_tools');
      const byName = Object.fromEntries(m.data.tools.map((t) => [t.name, t]));
      const toolNames = Object.keys(byName).sort().join();
      const regNames = regs.map((d) => d.name).sort().join();
      const hintsOk = regs.every((d) => byName[d.name] && d.annotations.readOnlyHint === (byName[d.name].kind === 'read'));
      const schemasOk = regs.every((d) => byName[d.name] && JSON.stringify(d.inputSchema) === JSON.stringify(byName[d.name].inputSchema));
      const st = regs.find((d) => d.name === 'get_status');
      const pj = regs.find((d) => d.name === 'post_journal');
      const status = st ? await st.execute({}) : { ok: false };
      const post = pj ? await pj.execute(${JOURNAL(555, 'webmcp', '2025-06-20')}) : { ok: false };
      const pid = post.ok ? post.data.proposalId : null;
      const prop = pid ? BAHI_AGENT.proposals.get(pid) : null;
      const self = await bahi.call('run_selftest');
      return { same: toolNames === regNames, regCount: regs.length, toolCount: m.data.tools.length, hintsOk, schemasOk,
        statusOk: status.ok === true, mcDoor: status.ok ? status.data.doors.modelContext : null,
        postStatus: post.ok ? post.data.status : null, door: prop ? prop.door : null,
        selftest: self.ok && self.data.pass, failures: self.ok ? self.data.failures : null };` },
  ] });
  const V = run.results.map((r) => r.value || { threw: r.threw });
  const [stage, decide, person, attrib, chan, mcp] = V;

  // C36 — a write stages and touches nothing until the person approves; approval posts it
  // and saves. Reintroduce by letting write tools run on the call.
  const s = stage;
  record('C36', 'a write call stages a proposal; the books change only after approval, which saves',
    !!s.staged && s.staged.ok && s.staged.data.status === 'pending_approval' && s.e1 === s.e0 && s.a1 === s.a0 &&
    s.pend && s.pend.data.status === 'pending' && s.listed >= 1 &&
    s.after && s.after.data.status === 'applied' && s.after.data.result.entryId > 0 && s.after.data.result.saved === true && s.e2 === s.e0 + 1,
    s.threw || `staged=${s.staged && s.staged.data && s.staged.data.status} entries ${s.e0}->${s.e1} (staged) ->${s.e2} (approved) audit ${s.a0}->${s.a1} after=${s.after && s.after.data.status} saved=${s.after && s.after.data.result && s.after.data.result.saved}`);

  // C37 — rejected and withdrawn proposals never apply, even if approval is attempted later.
  // Reintroduce by letting approval ignore the proposal's status.
  const d = decide;
  record('C37', 'rejected and withdrawn proposals never apply; unknown ids are E_NOT_FOUND',
    !d.threw && d.e1 === d.e0 && d.v1.data.status === 'rejected' && d.w.ok && d.v2.data.status === 'withdrawn' &&
    !d.w2.ok && d.w2.error.code === 'E_BAD_ARGS' && !d.nf.ok && d.nf.error.code === 'E_NOT_FOUND',
    d.threw || `entries ${d.e0}->${d.e1} rejected=${d.v1.data && d.v1.data.status} withdrawn=${d.v2.data && d.v2.data.status} rewithdraw=${d.w2.ok ? 'ok' : d.w2.error.code} unknown=${d.nf.ok ? 'ok' : d.nf.error.code}`);

  // C38 — person-only acts are declared but no door reaches them. Reintroduce by dropping
  // the person-only refusal, so they fall through to E_UNKNOWN_TOOL like a typo.
  record('C38', 'person-only acts refused with E_PERSON_ONLY and absent from every door',
    !person.threw && person.codes.every((c) => c === 'E_PERSON_ONLY') && person.exposed.length === 0 && person.person >= 10,
    person.threw || `codes=${person.codes.join(',')} exposed=${person.exposed.join(',') || 'none'} personOnly=${person.person}`);

  // C39 — an applied write records which door, which caller, which proposal and who approved.
  // Reintroduce by dropping the agentCall stamp from audit payloads.
  const ac = attrib.agentCall || {};
  record('C39', 'an applied write records door, caller, proposal and approver in the audit payload',
    !attrib.threw && attrib.actor === 'agent:attrib' && attrib.action === 'entry.post' && ac.door === 'window' &&
    ac.caller === 'checks-caller' && ac.proposalId === attrib.id && ac.approvedBy === 'owner' && attrib.chainOk === true && attrib.breaks === 0,
    attrib.threw || `actor=${attrib.actor} agentCall=${JSON.stringify(attrib.agentCall)} chainOk=${attrib.chainOk}`);

  // C40 — the cross-tab door is closed until the person opens it, then answers only calls
  // addressed to this tab, and stages writes as door 'channel'. Reintroduce by opening it on load.
  record('C40', 'cross-tab channel closed by default; once opened it answers its own tab and stages writes',
    !chan.threw && chan.closedReplies === 0 && chan.tab === chan.ownTab && chan.c1ok && chan.c2status === 'pending_approval' &&
    !chan.c3answered && chan.door === 'channel' && chan.caller === 'peer-tab',
    chan.threw || `closedReplies=${chan.closedReplies} tab=${chan.tab === chan.ownTab ? 'own' : chan.tab} read=${chan.c1ok} write=${chan.c2status} otherTab=${chan.c3answered} door=${chan.door}`);

  // C41 — WebMCP carries exactly the callable tools, with the same schemas, read-only hints
  // that match each kind, and the same staging. Reintroduce by not registering write tools.
  record('C41', 'WebMCP registers exactly the callable tools, same schemas and hints, and stages writes',
    !mcp.threw && mcp.same && mcp.regCount === mcp.toolCount && mcp.hintsOk && mcp.schemasOk && mcp.statusOk &&
    /^registered/.test(mcp.mcDoor || '') && mcp.postStatus === 'pending_approval' && mcp.door === 'modelContext' && mcp.selftest === true,
    mcp.threw || `registered=${mcp.regCount}/${mcp.toolCount} same=${mcp.same} hints=${mcp.hintsOk} schemas=${mcp.schemasOk} door=${mcp.mcDoor} write=${mcp.postStatus} via=${mcp.door} selftest=${mcp.selftest} ${mcp.failures && mcp.failures.length ? JSON.stringify(mcp.failures) : ''}`);

  // C18 for this batch: the doors must not log errors either.
  if (run.consoleErrors.length || run.pageErrors.length) {
    process.stdout.write(`  doors batch console errors: ${[...run.consoleErrors, ...run.pageErrors].slice(0, 3).join(' | ')}\n`);
  }
  return run;
}

// Batches run only when the selection needs them. A full run does all eight.
if (wants('noFile'))     await batchNoFile();
if (wants('sample'))     await batchSample();
if (wants('readOnly'))   await batchReadOnly();
if (wants('reconcile'))  await batchReconcile();
if (wants('structural')) await batchStructural();
if (wants('parity'))     await batchParity();
if (wants('signing'))    await batchSigningKeys();
if (wants('doors'))      await batchDoors();

const shown = only ? results.filter((r) => only.includes(r.id)) : results;
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
