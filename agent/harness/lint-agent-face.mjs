// Bahi agent-face lint
// ====================
// The command bus, defined mechanically. Parses the app's script with acorn and holds two rules:
//
//   A. Every function that writes — runs SQL that changes the books, appends to the audit log,
//      posts an entry, or saves the file — is owned: reachable from a tool's handler or prepare
//      step, from a person-only act's declared functions, or from declared infrastructure.
//   B. No screen writes on its own. A screen function (render*, open*, show*, build*) may reach a
//      write only through bahiUi, a person-only act's functions, or declared infrastructure —
//      never by calling an engine write function or writing directly.
//
// Rule A finds a write nobody declared. Rule B finds a form that bypasses the tools: the two
// doors drifting apart is a screen that posts by its own path.
//
//   node lint-agent-face.mjs                 # lint index.html
//   node lint-agent-face.mjs --report        # also print every writer and who owns it
//
// Exported for the self-test, which plants faults and requires each to be caught.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as acorn from 'acorn';
import * as walk from 'acorn-walk';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HERE, '..', '..', 'index.html');

// Infrastructure that writes on no one's behalf: the file format, the schema, the save path,
// session bookkeeping. Each entry says why it is not a tool. Anything reachable from these is
// owned by them.
export const INFRA = {
  newDb: 'creates the empty schema for a new book',
  runSchemaMigrations: 'brings an older .khata up to this build\'s schema on open',
  seedDefaultGodown: 'schema seed run by migrations and file creation',
  seedInventoryAccounts: 'schema seed run by migrations and file creation',
  persistKhata: 'the save path every write ends in',
  appendAuditEntry: 'the audit log itself',
  postEntry: 'the double-entry engine every voucher posts through',
  getOrCreateRateAccount: 'creates a GST rate ledger the first time a rate is posted',
  getOrCreateCessAccount: 'creates a cess ledger the first time cess is posted',
  getOrCreateWacBatch: 'creates the synthetic WAC batch stock posting needs',
  getOrCreateTdsPayableAccount: 'creates a TDS payable ledger on first use',
  getOrCreateTcsPayableAccount: 'creates a TCS payable ledger on first use',
  clockDriftCheck: 'records a clock-drift warning in the audit log on open',
  openHandle: 'opening a file records session.start in the audit log',
  showCorruptionRecovery: 'records what recovery did to a damaged file',
  checkMasterEditResilience: 'the snapshot-pattern self-check run from the Debug Console',
  replayAuditEntry: 'replays an imported branch\'s log during a merge',
  bahiUi: 'the person\'s door: runs a tool at once for the person, then saves',
  agentApply: 'applies a proposal the person approved, then saves',
};

const WRITE_SQL = /^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b/i;
const WRITE_CALLS = new Set(['appendAuditEntry', 'postEntry', 'persistKhata']);
const SCREEN = /^(render|open|show|build)[A-Z]/;
// The screen layer: screens, and the router that reaches every screen. Ownership and engine
// reach stop here, or the router would make every function reachable from everything.
const isUi = (name) => SCREEN.test(name) || name === 'render' || name === 'nav';

function scriptOf(html) {
  const a = html.indexOf('<script>');
  const b = html.lastIndexOf('</script>');
  return { src: html.slice(a + 8, b), offsetLine: html.slice(0, a + 8).split('\n').length - 1 };
}

function literalText(node) {
  if (!node) return null;
  if (node.type === 'Literal' && typeof node.value === 'string') return node.value;
  if (node.type === 'TemplateLiteral') return node.quasis.map((q) => q.value.cooked).join('');
  return null;
}

// Every top-level function, and every function-valued property of the two tool tables, becomes a
// unit. Code nested inside a unit (form handlers, callbacks) is attributed to it.
export function analyse(html) {
  const { src, offsetLine } = scriptOf(html);
  const ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType: 'script', locations: true });
  const units = new Map();   // name → { node, line }
  const add = (name, node) => units.set(name, { node, line: node.loc.start.line + offsetLine });
  for (const stmt of ast.body) {
    if (stmt.type === 'FunctionDeclaration' && stmt.id) add(stmt.id.name, stmt);
    if (stmt.type === 'VariableDeclaration') {
      for (const d of stmt.declarations) {
        if (!d.init || d.id.type !== 'Identifier') continue;
        if (d.init.type === 'ArrowFunctionExpression' || d.init.type === 'FunctionExpression') add(d.id.name, d.init);
        if (d.init.type === 'ObjectExpression' && /^BAHI_AGENT_(HANDLERS|PREPARE)$/.test(d.id.name)) {
          for (const p of d.init.properties) {
            const key = p.key && (p.key.name || p.key.value);
            if (key && p.value && /Function/.test(p.value.type)) add(`${d.id.name}.${key}`, p.value);
          }
        }
      }
    }
  }
  const names = new Set([...units.keys()].filter((n) => !n.includes('.')));
  const info = new Map();
  for (const [name, { node, line }] of units) {
    const refs = new Set();
    const writes = [];
    walk.full(node, (n) => {
      if (n.type === 'Identifier' && names.has(n.name) && n.name !== name) refs.add(n.name);
      if (n.type === 'CallExpression') {
        const c = n.callee;
        if (c.type === 'Identifier' && WRITE_CALLS.has(c.name)) writes.push(c.name);
        if (c.type === 'MemberExpression' && !c.computed && c.property.name === 'run') writes.push('.run');
        if (c.type === 'MemberExpression' && !c.computed && c.property.name === 'exec') {
          const sql = literalText(n.arguments[0]);
          if (sql && WRITE_SQL.test(sql)) writes.push('.exec write');
        }
      }
    });
    info.set(name, { line, refs, writes });
  }
  return { info, units };
}

// Functions reachable from `roots`. A root may itself be a screen; the walk does not step into
// the screen layer from anywhere else.
function reach(info, roots) {
  const seen = new Set();
  const stack = [...roots].filter((r) => info.has(r));
  while (stack.length) {
    const n = stack.pop();
    if (seen.has(n)) continue;
    seen.add(n);
    for (const r of info.get(n).refs) if (!seen.has(r) && !isUi(r)) stack.push(r);
  }
  return seen;
}

// personOnly: the manifest's person-only entries, each with the functions (`ui`) that carry it out.
export function lint(html, personOnly, infra = INFRA) {
  const { info } = analyse(html);
  const problems = [];
  const toolRoots = [...info.keys()].filter((n) => /^BAHI_AGENT_(HANDLERS|PREPARE)\./.test(n));
  const personRoots = new Map();
  for (const p of personOnly) {
    for (const fn of p.ui || []) {
      if (!info.has(fn)) problems.push(`person-only ${p.name} names ${fn}, which does not exist`);
      else personRoots.set(fn, p.name);
    }
  }
  for (const fn of Object.keys(infra)) if (!info.has(fn)) problems.push(`infrastructure names ${fn}, which does not exist`);

  const byTools = reach(info, toolRoots);
  const byPerson = reach(info, personRoots.keys());
  const byInfra = reach(info, Object.keys(infra));
  const writers = [...info.entries()].filter(([, i]) => i.writes.length).map(([n]) => n);

  // A: every writer is owned.
  for (const w of writers) {
    if (byTools.has(w) || byPerson.has(w) || byInfra.has(w)) continue;
    problems.push(`A: ${w} (line ${info.get(w).line}) writes [${[...new Set(info.get(w).writes)].join(', ')}] but no tool, person-only act or infrastructure reaches it`);
  }

  // B: no screen writes on its own, or calls a write outside the bus directly. A screen that is a
  // person-only act's own function is that act, and may.
  for (const [name, i] of info) {
    if (!SCREEN.test(name) || personRoots.has(name) || Object.hasOwn(infra, name)) continue;
    if (i.writes.length) problems.push(`B: screen ${name} (line ${i.line}) writes on its own [${[...new Set(i.writes)].join(', ')}]`);
    for (const r of i.refs) {
      if (isUi(r) || r === 'bahiUi' || personRoots.has(r)) continue;
      if (writesTransitively(info, r)) problems.push(`B: screen ${name} (line ${i.line}) reaches a write through ${r} instead of bahiUi`);
    }
  }
  return { problems, writers, byTools, byPerson, byInfra, info };
}

function writesTransitively(info, n) {
  for (const m of reach(info, [n])) if (info.get(m).writes.length) return true;
  return false;
}

// The person-only table, read from the app itself so the lint and the manifest cannot disagree.
export function personOnlyOf(html) {
  const { src } = scriptOf(html);
  const a = src.indexOf('const BAHI_AGENT_PERSON_ONLY = [');
  const b = src.indexOf('\n];', a);
  // eslint-disable-next-line no-new-func
  return new Function(`return ${src.slice(a + 'const BAHI_AGENT_PERSON_ONLY = '.length, b + 2)}`)();
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const html = fs.readFileSync(APP, 'utf8');
  const res = lint(html, personOnlyOf(html));
  if (process.argv.includes('--report')) {
    for (const w of res.writers.sort()) {
      const owner = res.byTools.has(w) ? 'tool' : res.byPerson.has(w) ? 'person' : res.byInfra.has(w) ? 'infra' : 'NONE';
      process.stdout.write(`${owner.padEnd(7)} ${w}\n`);
    }
    process.stdout.write('\n');
  }
  for (const p of res.problems) process.stdout.write(`${p}\n`);
  process.stdout.write(`\n${res.writers.length} writing functions; ${res.problems.length} problem${res.problems.length === 1 ? '' : 's'}\n`);
  process.exit(res.problems.length ? 1 : 0);
}
