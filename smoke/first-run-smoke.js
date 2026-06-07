// Bahi — first-run smoke test
// =============================
// Exercises the picker-gated "create your first book" + reopen flows that otherwise can't be
// driven headlessly (native File System Access dialogs). It exists because the new-company
// wizard silently failed for the WHOLE v1.0 lifetime (see plan/2026-06-07-create-bug-audit.md
// / PR #17) and no automated check covered the UI handler + picker layer.
//
// HOW TO RUN (before a deploy, or in CI via the Chrome harness):
//   1. Open the app in a Chromium tab on a LOCAL / throwaway instance, open the console.
//   2. Paste this file, then run:   await runFirstRunSmoke()
//   3. Expect:   { pass: true, ... }   — any false is a regression in create/open.
//
// It restores the patched pickers and removes the test companies it created from this
// browser's IndexedDB workspace in a finally block. Still: run it on a throwaway instance,
// not your live books.
//
// What it asserts:
//   1. wizardResolves — promptNewCompany() RESOLVES when Create is clicked (the exact PR #17
//      bug was a TypeError after closeModal() that left the promise forever-pending).
//   2. createFile     — createNewKhataFile() writes a valid, hash-consistent .khata + sets STATE.
//   3. reopen         — openExistingKhataFile() reads it back and loads it.

async function runFirstRunSmoke() {
  const results = {};
  const created = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // In-memory fake filesystem + handle. Methods live on the PROTOTYPE (not own props) so the
  // handle survives IndexedDB structured-clone in addWorkspaceEntry (own props name/kind clone;
  // methods are simply dropped — a real FileSystemFileHandle is a cloneable platform object).
  const FS = new Map();
  class FakeFileHandle {
    constructor(name) { this.name = name; this.kind = 'file'; }
    async createWritable() { const n = this.name; return { async write(b) { FS.set(n, b); }, async truncate() {}, async close() {} }; }
    async getFile() { return new File([FS.get(this.name) || new Blob([])], this.name); }
    async queryPermission() { return 'granted'; }
    async requestPermission() { return 'granted'; }
    async isSameEntry(o) { return !!o && o.name === this.name; }
  }

  const origSave = window.showSaveFilePicker;
  const origOpen = window.showOpenFilePicker;
  let lastSaveName = null;
  let openName = null;
  window.showSaveFilePicker = async (opts) => { lastSaveName = (opts && opts.suggestedName) || 'smoke.khata'; return new FakeFileHandle(lastSaveName); };
  window.showOpenFilePicker = async () => [new FakeFileHandle(openName || lastSaveName || 'smoke.khata')];

  try {
    // 1) The wizard must resolve on Create (regression guard for PR #17).
    try {
      const p = promptNewCompany();
      await sleep(80); // let the modal render (it finishes setup in a setTimeout)
      if (!document.getElementById('nc-name')) throw new Error('wizard did not open (nc-name missing)');
      document.getElementById('nc-name').value = 'Smoke Wizard Co';
      document.getElementById('nc-state').value = 'Maharashtra';
      document.getElementById('nc-type').value = 'proprietorship';
      const btn = [...document.querySelectorAll('#modal button')].find((b) => b.textContent.trim() === 'Create');
      if (!btn) throw new Error('Create button not found in modal');
      btn.click();
      const data = await Promise.race([p, sleep(2500).then(() => 'TIMEOUT')]);
      const ok = data !== 'TIMEOUT' && !!data && data.companyName === 'Smoke Wizard Co';
      results.wizardResolves = { pass: ok, detail: data === 'TIMEOUT' ? 'HUNG — promise never resolved (the PR #17 failure)' : ('resolved: ' + (data && data.companyName)) };
    } catch (e) { results.wizardResolves = { pass: false, error: String((e && e.message) || e) }; }

    // 2) createNewKhataFile writes a valid, hash-consistent .khata and loads STATE.
    try {
      const wsId = await createNewKhataFile({ companyName: 'Smoke Create Co', stateIso: 'MH', ui_tier: 'everything' });
      if (wsId) created.push(wsId);
      const blob = FS.get(lastSaveName);
      let hashOk = false, blobKB = 0;
      if (blob) {
        blobKB = Math.round(blob.size / 1024);
        const parsed = await readKhata(blob);
        const h = await sha256Bytes(parsed.dbBytes);
        hashOk = !!(parsed.manifest && parsed.manifest.integrity) && h === parsed.manifest.integrity.booksHash;
      }
      results.createFile = { pass: !!wsId && !!STATE.db && !!blob && hashOk, wsId: !!wsId, stateDb: !!STATE.db, blobKB, hashOk };
    } catch (e) { results.createFile = { pass: false, error: String((e && e.message) || e) }; }

    // 3) Reopen the just-created file through the open picker.
    try {
      openName = lastSaveName;
      const wsId = await openExistingKhataFile();
      if (wsId) created.push(wsId);
      results.reopen = { pass: !!wsId && !!STATE.db, wsId: !!wsId, stateDb: !!STATE.db };
    } catch (e) { results.reopen = { pass: false, error: String((e && e.message) || e) }; }
  } finally {
    window.showSaveFilePicker = origSave;
    window.showOpenFilePicker = origOpen;
    for (const id of created) { try { await removeWorkspaceEntry(id); } catch (_) {} }
    try { if (typeof closeCurrentFile === 'function') closeCurrentFile(); } catch (_) {}
  }

  const pass = Object.values(results).every((r) => r.pass);
  return { pass, results };
}

if (typeof window !== 'undefined') window.runFirstRunSmoke = runFirstRunSmoke;
