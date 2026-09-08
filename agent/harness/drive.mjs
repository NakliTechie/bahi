// Bahi agent-surface driver
// =========================
// Boots index.html in headless Chromium, optionally opens a scratch .khata, then
// runs a list of `window.bahi.call()` commands and prints the results as JSON.
//
// This is the ONLY way the agent surface is exercised end to end. It exists because
// Bahi is a browser app gated behind the File System Access API: the native pickers
// cannot be driven headlessly, so the harness swaps in an in-memory file handle —
// the same seam smoke/first-run-smoke.js uses, for the same reason.
//
//   node drive.mjs --book pharma --calls calls.json
//   node drive.mjs --book none   --calls calls.json     # nothing open (E_NO_FILE paths)
//   node drive.mjs --book fresh  --calls calls.json     # a newly created empty book
//   echo '[{"command":"agent.health"}]' | node drive.mjs --book fresh --calls -
//
// calls.json is [{ "command": "...", "args": {...} }, ...] and the output is
// { ok, book, results: [{ command, args, result }], consoleErrors, pageErrors }.
//
// Scratch tenant: --book pharma copies sample-data/pharma.khata into a temp dir and
// opens the COPY. Nothing under sample-data/ or a real book is ever written to.

import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json',
  '.khata': 'application/octet-stream', '.css': 'text/css', '.wasm': 'application/wasm',
};

function serve(root) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const url = decodeURIComponent(req.url.split('?')[0]);
      const file = path.join(root, url === '/' ? 'index.html' : url);
      // Path-traversal guard: the harness serves the repo, nothing above it.
      if (!file.startsWith(root)) { res.writeHead(403).end('no'); return; }
      fs.readFile(file, (err, buf) => {
        if (err) { res.writeHead(404).end('not found'); return; }
        res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream' });
        res.end(buf);
      });
    });
    // 127.0.0.1 + an ephemeral port: never binds a public interface.
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

function arg(name, dflt) {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : dflt;
}

async function readCalls(spec) {
  if (spec === '-') {
    const chunks = [];
    for await (const c of process.stdin) chunks.push(c);
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  }
  return JSON.parse(fs.readFileSync(spec, 'utf8'));
}

// Installed before any app script runs. Replaces the two native pickers with an
// in-memory filesystem so create/open work headlessly. Methods live on the
// prototype so the handle survives the structured clone into IndexedDB — the same
// constraint first-run-smoke.js documents.
const INSTALL_FAKE_PICKERS = () => {
  const FS = new Map();
  class FakeFileHandle {
    constructor(name) { this.name = name; this.kind = 'file'; }
    async createWritable() { const n = this.name; return { async write(b) { FS.set(n, b); }, async truncate() {}, async close() {} }; }
    async getFile() { return new File([FS.get(this.name) || new Blob([])], this.name); }
    async queryPermission() { return 'granted'; }
    async requestPermission() { return 'granted'; }
    async isSameEntry(o) { return !!o && o.name === this.name; }
  }
  window.__harness = {
    FS, FakeFileHandle,
    lastSaveName: null,
    openName: null,
    seed(name, bytes) { FS.set(name, new Blob([new Uint8Array(bytes)])); this.openName = name; },
  };
  window.showSaveFilePicker = async (opts) => {
    const n = (opts && opts.suggestedName) || 'harness.khata';
    window.__harness.lastSaveName = n;
    return new FakeFileHandle(n);
  };
  window.showOpenFilePicker = async () => [new FakeFileHandle(window.__harness.openName || window.__harness.lastSaveName || 'harness.khata')];
};

// Runs `calls` against one live session and returns the full result record.
// Exported so checks.mjs drives the surface exactly the way the CLI does — one
// code path, so a check can never pass against a harness the CLI doesn't use.
// `tamper` is DEFECT INJECTION for the check-prover: raw SQL run against the open
// book before the calls, used only to prove a check can go red (e.g. corrupting an
// audit hash to confirm the integrity check actually detects it). It is a harness
// capability and reaches nothing in the product surface.
export async function runCalls({ book = 'fresh', bookFile = null, calls = [], tamper = null } = {}) {
  const { server, port } = await serve(REPO);
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => pageErrors.push(String(e && e.message || e)));

  await page.addInitScript(INSTALL_FAKE_PICKERS);
  await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.bahi === 'object' && typeof window.bahi.call === 'function', null, { timeout: 30000 });

  let opened = null;
  if (book === 'fresh') {
    opened = await page.evaluate(async () => {
      const id = await createNewKhataFile({ companyName: 'Harness Scratch Co', stateIso: 'MH', ui_tier: 'everything' });
      return { kind: 'fresh', workspaceId: id || null };
    });
  } else if (book !== 'none') {
    // Copy the sample into a temp file and serve THAT — the repo sample is never touched.
    // bookFile takes an absolute path instead, for books the harness builds itself
    // (e.g. a future-format file, to reach the read-only path).
    const src = bookFile || path.join(REPO, 'sample-data', `${book}.khata`);
    if (!fs.existsSync(src)) throw new Error(`no such sample book: ${src}`);
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'bahi-harness-'));
    const dst = path.join(tmp, `scratch-${book}.khata`);
    fs.copyFileSync(src, dst);
    const bytes = Array.from(fs.readFileSync(dst));
    opened = await page.evaluate(async ({ name, bytes }) => {
      window.__harness.seed(name, bytes);
      const id = await openExistingKhataFile();
      return { kind: 'sample', name, workspaceId: id || null, fileOpen: !!(window.STATE_DEBUG || true) };
    }, { name: path.basename(dst), bytes });
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  if (tamper) await page.evaluate((sql) => { STATE.db.run(sql); }, tamper);

  const results = [];
  for (const c of calls) {
    const r = await page.evaluate(
      async ({ command, args, argsJson }) => {
        const a = argsJson === null ? args : JSON.parse(argsJson);
        const started = performance.now();
        // Deliberately NOT wrapped in try/catch: the contract is that call()
        // never throws. If it does, the harness must see the throw, not hide it.
        const out = await window.bahi.call(command, a);
        return { out, ms: Math.round(performance.now() - started) };
      },
      { command: c.command, args: c.args === undefined ? null : c.args, argsJson: c.argsJson ?? null }
    ).then((v) => ({ command: c.command, args: c.args ?? null, ms: v.ms, result: v.out }))
     .catch((e) => ({ command: c.command, args: c.args ?? null, threw: String((e && e.message) || e) }));
    results.push(r);
  }

  await browser.close();
  server.close();

  return { ok: true, book, opened, results, consoleErrors, pageErrors };
}

// CLI mode only when invoked directly, so `import`ing this file starts nothing.
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const book = arg('book', 'fresh');
  const bookFile = arg('bookfile', null);
  const calls = await readCalls(arg('calls', '-'));
  runCalls({ book, bookFile, calls })
    .then((out) => process.stdout.write(JSON.stringify(out, null, 2) + '\n'))
    .catch((e) => {
      process.stdout.write(JSON.stringify({ ok: false, error: String((e && e.stack) || e) }, null, 2) + '\n');
      process.exit(1);
    });
}
