// Self-test for the agent-face lint: a lint never seen to fail is not a lint.
// =========================================================================
// Plants six faults in a copy of index.html (and in the tables the lint reads) and requires the
// lint to report each one, then requires the untouched app to lint clean.
//
//   node test-lint-agent-face.mjs

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { lint, personOnlyOf, INFRA } from './lint-agent-face.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HERE, '..', '..', 'index.html');

function plant(html, find, insert) {
  if (!html.includes(find)) throw new Error(`self-test anchor missing: ${find}`);
  return html.replace(find, insert + find);
}

export function selfTest(html = fs.readFileSync(APP, 'utf8')) {
  const personOnly = personOnlyOf(html);
  const results = [];
  const expect = (label, res, pattern) => {
    const hit = res.problems.some((p) => pattern.test(p));
    results.push({ label, pass: hit, detail: hit ? 'caught' : `missed; problems: ${res.problems.slice(0, 3).join(' | ') || 'none'}` });
  };
  const GODOWNS = "  const r = queryList(STATE.db, 'godowns');";

  const clean = lint(html, personOnly);
  results.push({ label: 'the app lints clean', pass: clean.problems.length === 0, detail: clean.problems.slice(0, 3).join(' | ') || 'clean' });

  expect('a screen that runs SQL on its own',
    lint(plant(html, GODOWNS, "  STATE.db.run('UPDATE godowns SET name = name');\n"), personOnly), /^B: screen renderGodowns .*writes on its own/);
  expect('a screen that writes through db.exec',
    lint(plant(html, GODOWNS, "  STATE.db.exec(\"INSERT INTO godowns (name) VALUES ('x')\");\n"), personOnly), /^B: screen renderGodowns .*writes on its own \[\.exec write\]/);
  expect('a screen that calls an engine write instead of bahiUi',
    lint(plant(html, GODOWNS, "  if (false) saveGodown(STATE.db, {});\n"), personOnly), /^B: screen renderGodowns .*through saveGodown/);
  expect('a write that nothing owns',
    lint(plant(html, '\nfunction renderGodowns(', "\nfunction strayWriter() { STATE.db.run('UPDATE items SET name = name'); }\n"), personOnly), /^A: strayWriter /);
  expect('a person-only act naming a function that does not exist',
    lint(html, [...personOnly, { name: 'ghost', ui: ['noSuchFunction'] }]), /names noSuchFunction, which does not exist/);
  expect('infrastructure naming a function that does not exist',
    lint(html, personOnly, { ...INFRA, noSuchInfra: 'planted' }), /infrastructure names noSuchInfra/);
  return results;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const results = selfTest();
  for (const r of results) process.stdout.write(`${r.pass ? 'PASS' : 'FAIL'}  ${r.label}\n      ${r.detail}\n`);
  const red = results.filter((r) => !r.pass).length;
  process.stdout.write(`\n${results.length - red}/${results.length} self-test cases\n`);
  process.exit(red ? 1 : 0);
}
