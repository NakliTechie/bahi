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

const r1 = await batchNoFile();
const r2 = await batchSample();
const r3 = await batchReadOnly();

const shown = only ? results.filter((r) => r.id === only) : results;
let red = 0;
for (const r of shown) {
  if (!r.pass) red++;
  process.stdout.write(`${r.pass ? 'PASS' : 'FAIL'}  ${r.id.padEnd(4)} ${r.title}\n`);
  if (!r.pass) process.stdout.write(`             ${r.detail}\n`);
}
process.stdout.write(`\n${shown.length - red}/${shown.length} green${red ? `, ${red} RED` : ''}\n`);
process.exit(red ? 1 : 0);
