// Proves each check in checks.mjs can FAIL.
// ========================================
// A check that stays green whether or not the defect is present is not a check.
// This script reintroduces each defect one at a time — editing index.html, running
// the suite, then restoring the file byte-for-byte — and records which checks went red.
//
//   node prove-red.mjs            # every defect
//   node prove-red.mjs C19        # one
//
// Output: a matrix of defect -> checks that went red. A defect whose target check
// stayed green is reported as UNPROVEN, which means the check needs rewriting.

import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HERE, '..', '..', 'index.html');
const MANIFEST = path.resolve(HERE, '..', 'manifest.json');

// Each defect: the target check it must turn red, and a single unambiguous
// find/replace against index.html that reintroduces the original bug.
const DEFECTS = [
  { id: 'C1', target: 'C1', also: ['C17'], note: 'rename a handler so the manifest declares a tool that cannot dispatch',
    find: "  list_routes: async () => Object.entries(ROUTE_INDEX)", replace: "  list_routes__BROKEN: async () => Object.entries(ROUTE_INDEX)" },
  { id: 'C2', note: 'change a tool description in code without regenerating manifest.json',
    find: "the UI routes not yet covered. Start here.'", replace: "the UI routes not yet covered. Start here (drifted).'" },
  { id: 'C3', note: 'drop the unknown-tool guard so an unknown name falls through to the spec lookup',
    find: "  if (typeof name !== 'string' || !Object.prototype.hasOwnProperty.call(BAHI_AGENT_TOOLS, name)) {",
    replace: "  if (false) {" },
  { id: 'C4', target: 'C4', also: ['C5'], note: 'remove the file-scope guard so file tools run with no book open',
    find: "  if (spec.scope === 'file' && !(STATE.db && STATE.manifest)) {", replace: "  if (false) {" },
  { id: 'C6', note: 'interpolate the q filter into SQL instead of binding it',
    find: "  if (a.q) { clauses.push('name LIKE ?'); params.push(`%${a.q}%`); }",
    replace: "  if (a.q) { clauses.push(`name LIKE '%${a.q}%'`); }" },
  { id: 'C7', note: 'validate dates by regex only, letting new Date() roll 2026-02-30 forward',
    find: "  const dt = new Date(Date.UTC(y, m - 1, d));\n  // Rejects 2026-02-30 and friends, which Date would otherwise roll forward.\n  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;",
    replace: "  return true;" },
  { id: 'C8', note: 'stop rejecting unknown parameters',
    find: "    if (!Object.prototype.hasOwnProperty.call(spec, key)) errs.push(`unknown parameter '${key}'`);",
    replace: "    if (false) errs.push(`unknown parameter '${key}'`);" },
  { id: 'C9', note: 'validate only the declared top-level params, never the nested lines[] objects',
    find: "      if (typeof v !== 'number' || !Number.isFinite(v) || !Number.isInteger(v)) {\n          throw new AgentBadArgs(`lines[${i}].${side} must be an integer number of paise, got ${JSON.stringify(v)}`);\n        }",
    replace: "      if (false) {\n          throw new AgentBadArgs('unreachable');\n        }" },
  { id: 'C11', note: 'let a read tool quietly write',
    find: "  get_file_info: async () => {\n    const m = STATE.manifest;",
    replace: "  get_file_info: async () => {\n    STATE.db.run(\"UPDATE meta SET value = value WHERE key = 'schemaVersion'\");\n    const m = STATE.manifest;" },
  { id: 'C12', note: 'let navigate accept any string as a route',
    find: "    if (!Object.prototype.hasOwnProperty.call(ROUTE_INDEX, a.route)) {\n      throw new AgentBadArgs(`unknown route '${a.route}' — call list_routes for the list`);\n    }",
    replace: "    if (false) { throw new AgentBadArgs('unreachable'); }" },
  { id: 'C13', target: 'C13', also: ['C22'], note: 'drop the agent attribution stamp so writes look like the owner did them',
    find: "  return (args && args.agentName) ? `agent:${args.agentName}` : 'agent';",
    replace: "  return 'owner';" },
  // Double entry is guarded twice: the prepare step refuses an unbalanced journal before it
  // can stage, and the engine asserts it again on posting. C10 holds while either guard
  // stands, so the defect removes both: the prepare check, and the engine's throw swallowed.
  { id: 'C10', note: 'drop the prepare-step balance check and swallow the engine assertion',
    find: "    if (dr !== cr) throw new AgentBadArgs(`lines do not balance: debits ${dr} paise, credits ${cr} paise`);",
    replace: "" },
  // C16 guards two distinct promises. Removing one net alone does not prove it, because the
  // other still converts the throw into a declared code — C16's claim holds, so C16 is right
  // to stay green. These reintroduce the defects C16 actually guards.
  { id: 'C16', note: 'remove BOTH error nets so a handler throw escapes as a rejected promise',
    find: "  const run = () => Promise.resolve().then(fn).catch((e) => agentFail('E_INTERNAL', String((e && e.message) || e)));",
    replace: "  const run = () => Promise.resolve().then(fn);" },
  { id: 'C16b', target: 'C16', note: 'emit an error code the manifest never declares',
    find: "  return (e && e.agentCode) || (e && e.name === 'VoucherError' ? 'E_BAD_ARGS' : 'E_ENGINE');",
    replace: "  return 'E_SOMETHING_ELSE';" },
  { id: 'C18', target: 'C18', note: 'let a handler log to the console instead of failing cleanly',
    find: "  get_file_info: async () => {\n    const m = STATE.manifest;",
    replace: "  get_file_info: async () => {\n    console.error('agent face: noisy handler');\n    const m = STATE.manifest;" },
  { id: 'C28', target: 'C28', note: 'form stops delegating — the engine call is replaced by its own path',
    find: "      const result = await createInvoice(STATE.db, {",
    replace: "      const result = await createInvoiceLegacyInlinePath(STATE.db, {" },
  { id: 'C29', target: 'C29', note: 'the two doors drift — the agent defaults a different invoice series',
    find: "      series: a.series || 'Domestic', placeOfSupply: a.placeOfSupply || null,",
    replace: "      series: a.series || 'Export', placeOfSupply: a.placeOfSupply || null," },
  { id: 'C32', target: 'C32', note: 're-home signedBy before banking the outgoing signer (the original ordering bug)',
    find: "      addTrustedKey(STATE.manifest.integrity, STATE.manifest.integrity.signedBy);\n      STATE.manifest.integrity.signedBy = STATE.publicJwk;",
    replace: "      STATE.manifest.integrity.signedBy = STATE.publicJwk;" },
  { id: 'C33', target: 'C33', note: 'payment form stops delegating',
    find: "      const result = await createPayment(STATE.db, {",
    replace: "      const result = await createPaymentLegacyInlinePath(STATE.db, {" },
  { id: 'C34', target: 'C34', note: 'credit note form stops delegating',
    find: "      const result = await createCreditNote(STATE.db, {",
    replace: "      const result = await createCreditNoteLegacyInlinePath(STATE.db, {" },
  { id: 'C35', target: 'C35', note: 'debit note form stops delegating',
    find: "      const result = await createDebitNote(STATE.db, {",
    replace: "      const result = await createDebitNoteLegacyInlinePath(STATE.db, {" },
  { id: 'C30', target: 'C30', note: 'purchase form stops delegating — the engine call is replaced by its own path',
    find: "      const result = await createPurchase(STATE.db, {",
    replace: "      const result = await createPurchaseLegacyInlinePath(STATE.db, {" },
  // First attempt used the itcEligible default, which is DEAD CODE: the validator fills a
  // declared default, so `a.itcEligible === undefined` is never true. Reverse charge is
  // reachable and changes both the header flag and the ledger legs.
  { id: 'C31', target: 'C31', note: 'the two doors drift — the agent flips reverse-charge treatment',
    find: "      notes: a.notes || null, reverseCharge: !!a.reverseCharge,",
    replace: "      notes: a.notes || null, reverseCharge: !a.reverseCharge," },
  { id: 'C23', target: 'C23', note: 'make the day-book range exclusive at the start, dropping each period\'s first day',
    find: "    FROM entries e\n    WHERE e.posted_at BETWEEN ? AND ?\n    ORDER BY e.posted_at, e.id",
    replace: "    FROM entries e\n    WHERE e.posted_at > ? AND e.posted_at <= ?\n    ORDER BY e.posted_at, e.id" },
  { id: 'C24', target: 'C24', note: 'shift the GSTR-3B outward total by one paise so it stops matching GSTR-1',
    find: "    FROM invoices WHERE status='posted' AND invoice_date BETWEEN ? AND ?\n  `, [periodStart, periodEnd]);\n  const [outTaxable, outCgst, outSgst, outIgst, outCess, invoiceCount] = invR[0].values[0];",
    replace: "    FROM invoices WHERE status='posted' AND invoice_date BETWEEN ? AND ?\n  `, [periodStart, periodEnd]);\n  const [outTaxable0, outCgst, outSgst, outIgst, outCess, invoiceCount] = invR[0].values[0];\n  const outTaxable = outTaxable0 + 1;" },
  { id: 'C25', target: 'C25', note: 'flip the liabilities sign in the balance-sheet roll-up',
    find: "      const bal = -row.balance; // liabilities are credit-balance",
    replace: "      const bal = row.balance; // liabilities are credit-balance" },
  { id: 'C26', target: 'C26', note: 'off-by-one OFFSET so paging silently skips a row per page',
    find: "  params.push(a.limit, a.offset);", replace: "  params.push(a.limit, a.offset + 1);" },
  { id: 'C27', target: 'C27', note: 'zero the account ledger\'s credit column so it stops matching the trial balance',
    find: "      l.debit, l.credit, COALESCE(l.account_name, a.name) AS account_name",
    replace: "      l.debit, 0, COALESCE(l.account_name, a.name) AS account_name" },
  { id: 'C22', target: 'C22', note: 'drop the agentName pattern so a colon can forge a misleading actor',
    find: "const AGENT_NAME_PARAM = { type: 'string', maxLength: 60, pattern: '^[A-Za-z0-9._-]{1,60}$', desc:",
    replace: "const AGENT_NAME_PARAM = { type: 'string', maxLength: 60, desc:" },
  // The apply step refuses a read-only file too, so this defect alone still ends in
  // E_READONLY — but only after a proposal was staged, which is what C21 forbids.
  { id: 'C21', target: 'C21', note: 'drop the call-time read-only guard so a write stages against a future-format book',
    find: "  if (spec.kind === 'write' && STATE.readOnly) {", replace: "  if (false) {" },
  { id: 'C19', note: 'remove the reversed-range guard (the defect the adversarial round found)',
    find: "    if (v.value[lo] && v.value[hi] && v.value[lo] > v.value[hi]) {", replace: "    if (false) {" },
  { id: 'C20', note: 'enumerate args with for..in so an own __proto__ key is never seen as unknown',
    find: "  for (const key of Object.keys(given)) {", replace: "  for (const key of []) {" },
  { id: 'C36', target: 'C36', note: 'let write tools run on the call instead of staging a proposal',
    find: "    if (spec.kind === 'write') return { ok: true, data: agentStage(name, BAHI_AGENT_PREPARE[name](v.value), ctx) };",
    replace: "    if (false) return null;" },
  { id: 'C37', target: 'C37', note: 'let approval ignore the proposal\'s status, so a rejected or withdrawn one applies',
    find: "      if (p && p.status === 'pending') await agentApply(p);", replace: "      if (p) await agentApply(p);" },
  { id: 'C38', target: 'C38', note: 'drop the person-only refusal, so those acts fall through as unknown names',
    find: "    if (held) return agentFail('E_PERSON_ONLY', `${held.title} is person-only: ${held.reason}`, { tool: name });",
    replace: "" },
  { id: 'C39', target: 'C39', note: 'stop stamping agentCall into audit payloads',
    find: "  return { ...payload, agentCall: AGENT_CALL_CONTEXT };", replace: "  return payload;" },
  { id: 'C40', target: 'C40', note: 'open the cross-tab channel on load, without the person',
    find: "  agentOpenChannel(agentChannelSetting());", replace: "  agentOpenChannel(true);" },
  { id: 'C41', target: 'C41', note: 'register only some tools on WebMCP — skip the write tools',
    find: "    const definition = {\n      name,\n      title: spec.title,",
    replace: "    if (spec.kind === 'write') continue;\n    const definition = {\n      name,\n      title: spec.title," },
];

// A defect may need further edits, applied in order, to stay syntactically valid or to
// remove every guard behind a claim.
const EXTRA = {
  C16: [{ find: "  } catch (e) {\n    const code = agentErrorCode(e);\n    return agentFail(code, String((e && e.message) || e), { tool: name, ...(e && e.field ? { problems: [`${e.field}: ${e.message}`] } : {}) });\n  }\n}",
          replace: "  } finally {}\n}" }],
  C10: [{ find: "    const res = await postEntry(STATE.db, {", replace: "    const res = await (async () => { try { return await postEntry(STATE.db, {" },
        { find: "    return { entryId: res.entryId, postedAt: a.postedAt, actor, lineCount: a.lines.length, amendment: !!periodLock, periodLock };",
          replace: "    } catch (_) { return { entryId: -1 }; } })();\n    return { entryId: res.entryId, postedAt: a.postedAt, actor, lineCount: a.lines.length, amendment: !!periodLock, periodLock };" }],
};

const sel = process.argv[2] ? process.argv[2].split(',') : null;
const wanted = sel ? DEFECTS.filter((d) => sel.includes(d.id)) : DEFECTS;
const original = fs.readFileSync(APP, 'utf8');
const originalManifest = fs.readFileSync(MANIFEST, 'utf8');

// This script deliberately writes a BROKEN index.html and then repairs it. If it dies
// between those two moments the app is left defected — which is exactly what happened on
// 2026-09-08 when the machine saturated and the run was killed. Restoring only at the end
// of an iteration is unsafe by construction, so restore on every way out.
let restored = false;
function restoreApp(reason) {
  if (restored) return;
  restored = true;
  try {
    fs.writeFileSync(APP, original);
    fs.writeFileSync(MANIFEST, originalManifest);
    if (reason) process.stderr.write(`\nprove-red: restored index.html and manifest.json after ${reason}\n`);
  } catch (e) {
    process.stderr.write(`\nprove-red: COULD NOT RESTORE index.html — ${e.message}\n  git checkout -- index.html agent/manifest.json\n`);
  }
}
process.on('exit', () => restoreApp(null));
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(sig, () => { restoreApp(sig); process.exit(130); });
}
process.on('uncaughtException', (e) => { restoreApp('an uncaught exception'); process.stderr.write(String(e && e.stack || e) + '\n'); process.exit(1); });
process.on('unhandledRejection', (e) => { restoreApp('an unhandled rejection'); process.stderr.write(String(e && e.stack || e) + '\n'); process.exit(1); });

// Run ONLY the checks this defect targets. Evaluating one check used to cost the whole
// suite — eight browser sessions — which is what made a full matrix unrunnable here.
function runSuite(targets) {
  const args = [path.join(HERE, 'checks.mjs')];
  if (targets && targets.length) args.push('--only', targets.join(','));
  try {
    return execFileSync('node', args, { encoding: 'utf8', cwd: HERE, timeout: 900000 });
  } catch (e) { return String(e.stdout || '') + String(e.stderr || ''); }
}

const rows = [];
for (const d of wanted) {
  if (!original.includes(d.find)) { rows.push({ id: d.id, status: 'PATCH-MISS', red: [] }); continue; }
  let mutated = original.replace(d.find, d.replace);
  let missed = false;
  for (const extra of EXTRA[d.id] || []) {
    if (!mutated.includes(extra.find)) { missed = true; break; }
    mutated = mutated.replace(extra.find, extra.replace);
  }
  if (missed) { rows.push({ id: d.id, status: 'PATCH-MISS', red: [] }); continue; }
  fs.writeFileSync(APP, mutated);
  const out = runSuite([d.target || d.id, ...(d.also || [])]);
  fs.writeFileSync(APP, original);
  fs.writeFileSync(MANIFEST, originalManifest);
  const red = [...out.matchAll(/^FAIL\s+(C\d+)/gm)].map((m) => m[1]);
  const crashed = /Error|error TS|SyntaxError/.test(out) && red.length === 0;
  const target = d.target || d.id;
  rows.push({ id: d.id, target, note: d.note, red, status: red.includes(target) ? 'PROVEN' : (crashed ? 'HARNESS-ERROR' : 'UNPROVEN') });
  process.stdout.write(`${rows.at(-1).status.padEnd(14)} ${d.id.padEnd(5)} ->${(d.target || d.id).padEnd(4)} red=[${red.join(',') || 'none'}]  ${d.note}\n`);
}

// C14 — proven by unbalancing a real ledger by one paise. The check must notice that the
// books no longer tie; a code defect cannot demonstrate that.
if (!sel || sel.includes('C14')) {
  fs.writeFileSync(APP, original);
  const { runCalls } = await import('./drive.mjs');
  const calls = [{ command: 'get_trial_balance', args: { asOf: '2026-03-31' } }];
  const clean = await runCalls({ book: 'pharma', calls });
  const bent = await runCalls({ book: 'pharma', calls, tamper: 'UPDATE entry_lines SET debit = debit + 1 WHERE id = (SELECT MIN(id) FROM entry_lines WHERE debit > 0)' });
  const cd = clean.results[0].result.data, bd = bent.results[0].result.data;
  const proven = cd.balanced === true && bd.balanced === false && bd.differencePaise === 1;
  rows.push({ id: 'C14', target: 'C14', note: 'unbalance a real ledger by one paise', red: proven ? ['C14'] : [], status: proven ? 'PROVEN' : 'UNPROVEN' });
  process.stdout.write(`${(proven ? 'PROVEN' : 'UNPROVEN').padEnd(14)} C14   ->C14  control balanced=${cd.balanced} diff=${cd.differencePaise} | tampered balanced=${bd.balanced} diff=${bd.differencePaise}\n`);
}

// C15 — proven by corrupting a real audit chain rather than by a code defect. A defect in
// the reporting layer would only show the check reads the right field; this shows it detects
// actual tampering. The clean control runs alongside it.
if (!sel || sel.includes('C15')) {
  fs.writeFileSync(APP, original);
  const { runCalls } = await import('./drive.mjs');
  const calls = [{ command: 'verify_integrity' }];
  const clean = await runCalls({ book: 'pharma', calls });
  const tampered = await runCalls({ book: 'pharma', calls, tamper: "UPDATE audit_log SET hash = 'deadbeef' WHERE id = (SELECT MIN(id) FROM audit_log)" });
  const cd = clean.results[0].result.data, td = tampered.results[0].result.data;
  const proven = cd.chainOk === true && td.chainOk === false && td.chainBreaks > 0;
  rows.push({ id: 'C15', target: 'C15', note: 'corrupt one audit-log hash on a real book', red: proven ? ['C15'] : [], status: proven ? 'PROVEN' : 'UNPROVEN' });
  process.stdout.write(`${(proven ? 'PROVEN' : 'UNPROVEN').padEnd(14)} C15   ->C15  control chainOk=${cd.chainOk} breaks=${cd.chainBreaks} | tampered chainOk=${td.chainOk} breaks=${td.chainBreaks}\n`);
}

// Restore, then confirm the untouched file is green again.
fs.writeFileSync(APP, original);
fs.writeFileSync(MANIFEST, originalManifest);
const clean = runSuite(null);
const cleanRed = [...clean.matchAll(/^FAIL\s+(C\d+)/gm)].map((m) => m[1]);
process.stdout.write(`\nRESTORED: ${cleanRed.length ? 'STILL RED ' + cleanRed.join(',') : 'all green'}\n`);
const unproven = rows.filter((r) => r.status !== 'PROVEN');
process.stdout.write(`${rows.length - unproven.length}/${rows.length} checks proven able to fail\n`);
if (unproven.length) process.stdout.write('UNPROVEN: ' + unproven.map((u) => `${u.id}(${u.status})`).join(', ') + '\n');
process.exit(unproven.length || cleanRed.length ? 1 : 0);
