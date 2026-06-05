// corpus/build.mjs
// ---------------------------------------------------------------------------
// Build the Bahi CA-lookup corpus artifact (Phase 0 spine).
//
//   read   plan/corpus-bakeoff/merged-tds.json  (23 TDS/TCS entries, the seed)
//   compose  searchText per entry (title + body + section[both Acts] + rate +
//            threshold + tags + key terms)
//   embed   each searchText with bge-small-en-v1.5 (mean-pool + L2-norm) via
//            the shared embed.mjs contract — the SAME path the browser query
//            embedder must reproduce
//   quantize  each vector to int8 (per-vector min/max)
//   write   corpus/ca-corpus.v0.json = { model, dim, builtFrom, entries:[...] }
//
// Run:  node build.mjs   (from inside corpus/)
// ---------------------------------------------------------------------------

import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import {
  embedPassage,
  DIM,
  activeModelName,
  usingFallback,
} from './embed.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..');

// v1: ingest the TDS/TCS bake-off file + all reconciled category slices.
const BAKEOFF_DIR = join(REPO_ROOT, 'plan/corpus-bakeoff');
const SLICES_DIR = join(BAKEOFF_DIR, 'slices');
const OUT_PATH = join(__dirname, 'ca-corpus.v1.json');

// merged-tds.json + slices/*.json (excluding intermediate *.draft.json).
function collectSources() {
  const sources = [
    { rel: 'plan/corpus-bakeoff/merged-tds.json', path: join(BAKEOFF_DIR, 'merged-tds.json') },
  ];
  for (const f of readdirSync(SLICES_DIR).sort()) {
    if (!f.endsWith('.json') || f.endsWith('.draft.json')) continue;
    sources.push({ rel: `plan/corpus-bakeoff/slices/${f}`, path: join(SLICES_DIR, f) });
  }
  return sources;
}

// --- section-alias derivation ----------------------------------------------

/**
 * Parse the 2025-Act section number out of the free-text `actNew2025` field,
 * e.g. "Sec 393(1) — non-salary TDS. ..." -> "393(1)".
 * Returns null if none found (e.g. REPEALED entries).
 */
function parse2025Section(actNew2025) {
  if (!actNew2025) return null;
  const m = actNew2025.match(/Sec\s+(\d+[A-Z]*(?:\([0-9A-Za-z]+\))?)/);
  return m ? m[1] : null;
}

/**
 * Build the section alias list: 2025-Act section first (primary, the law in
 * force), then the 1961 section as alias (what every user/CA still types).
 * De-duplicated, order preserved. See schema.md §3b for the decision.
 */
function deriveSectionAliases(entry) {
  const aliases = [];
  const s2025 = parse2025Section(entry.actNew2025);
  if (s2025) aliases.push(s2025);
  if (entry.section) aliases.push(entry.section);
  return [...new Set(aliases)];
}

/**
 * Precision codes for the lexical channel: income-tax section aliases PLUS any
 * HSN/SAC/chapter code that appears with an explicit cue (so we never pick up
 * years like 2025 or rupee amounts). Normalized uppercase, no spaces/hyphens.
 */
function deriveCodes(entry, aliases) {
  const codes = new Set(aliases.map((a) => String(a).toUpperCase().replace(/[\s-]/g, '')));
  const hay = [entry.section, entry.title, entry.subtopic, entry.body, entry.rate, ...(entry.tags || [])]
    .filter(Boolean)
    .join(' ');
  // Cued HSN/SAC/chapter/heading codes only: "HSN 2202", "SAC 9963", "Chapter 87".
  const cueRe = /\b(?:HSN|SAC|chapter|heading|tariff(?:\s*item)?)\s*:?\s*(\d{2,8})/gi;
  let m;
  while ((m = cueRe.exec(hay)) !== null) codes.add(m[1]);
  // Bare income-tax section handles found in section/title (e.g. 194J, 206C(1H)).
  const secRe = /\b(\d{3}[A-Z]{0,3}(?:\([0-9A-Za-z]+\))?)\b/g;
  const secHay = [entry.section, entry.title].filter(Boolean).join(' ');
  while ((m = secRe.exec(secHay)) !== null) {
    const norm = m[1].toUpperCase().replace(/[\s-]/g, '');
    if (/[A-Z]/.test(norm) || /\(/.test(norm)) codes.add(norm);
  }
  return [...codes];
}

// --- searchText composition ------------------------------------------------

/**
 * A small curated synonym/key-term map so common user phrasings land
 * semantically AND lexically. Keyed by section (1961). Kept tiny + readable;
 * this is a spine, not a thesaurus.
 */
const KEY_TERMS = {
  '192': ['salary', 'employee', 'payroll', 'employer'],
  '192A': ['epf', 'provident fund', 'pf withdrawal'],
  '193': ['interest on securities', 'debentures', 'bonds'],
  '194': ['dividend', 'shareholder'],
  '194A': ['fixed deposit', 'fd interest', 'bank interest', 'loan interest'],
  '194C': ['contractor', 'subcontractor', 'works contract', 'labour supply'],
  '194D': ['insurance commission', 'insurance agent'],
  '194DA': ['life insurance payout', 'maturity proceeds', 'policy'],
  '194H': ['commission', 'brokerage', 'broker'],
  '194I': ['rent', 'lease', 'landlord', 'office rent', 'machinery rent'],
  '194IA': ['property purchase', 'immovable property', 'buying property', '26QB'],
  '194IB': ['rent by individual', 'tenant', 'house rent', '26QC'],
  '194J': [
    'professional fees', 'professional services', 'technical services',
    'consultant', 'freelancer', 'royalty', 'fts', 'fees for professional',
  ],
  '194K': ['mutual fund', 'mf units', 'unit holder'],
  '194N': ['cash withdrawal', 'cash from bank', 'large cash', 'atm withdrawal'],
  '194O': ['e-commerce', 'online seller', 'marketplace', 'platform sales'],
  '194Q': ['purchase of goods', 'buyer tds', 'goods purchase'],
  '194R': ['benefit', 'perquisite', 'freebie', 'incentive in kind', 'sample'],
  '194S': ['crypto', 'virtual digital asset', 'vda', 'nft'],
  '194T': [
    'partner remuneration', 'partner salary', 'partner interest',
    'partnership firm', 'llp', 'remuneration to partner',
  ],
  '195': ['non-resident', 'foreign payment', 'cross-border', 'nri payment'],
  '206C(1)': ['tcs', 'scrap', 'alcohol', 'minerals', 'forest produce', 'timber'],
  '206C(1H)': ['tcs sale of goods', 'abolished tcs', 'seller tcs'],
};

/**
 * Compose the searchable text for an entry. Order/intent documented in
 * schema.md §3a. Falsy parts are dropped.
 */
function composeSearchText(entry, aliases) {
  const keyTerms = KEY_TERMS[entry.section] ?? [];
  const sectionLine = entry.section ? `Section ${entry.section}.` : '';
  const aliasLine =
    aliases.length > 1 ? `Also Section ${aliases[0]} (Income-tax Act 2025).` : '';
  const tags = Array.isArray(entry.tags) ? entry.tags : [];

  const parts = [
    entry.title,
    entry.body,
    sectionLine,
    aliasLine,
    entry.subtopic ? `Subtopic: ${entry.subtopic}.` : '',
    entry.rate ? `Rate: ${entry.rate}` : '',
    entry.threshold ? `Threshold: ${entry.threshold}` : '',
    entry.payer ? `Payer: ${entry.payer}.` : '',
    entry.payee ? `Payee: ${entry.payee}.` : '',
    tags.join(' '),
    keyTerms.join(' '),
  ];

  return parts
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// --- int8 quantization (per-vector min/max) --------------------------------

/**
 * Quantize a float vector to int8 [-128,127] using its own min/max.
 * Returns { vec:int8[], vmin, vmax }. Dequant formula lives in retrieve.mjs
 * and schema.md §4 (they must stay in sync).
 */
function quantizeInt8(floatVec) {
  let vmin = Infinity;
  let vmax = -Infinity;
  for (const v of floatVec) {
    if (v < vmin) vmin = v;
    if (v > vmax) vmax = v;
  }
  const range = vmax - vmin || 1; // guard against constant vector
  const q = new Array(floatVec.length);
  for (let i = 0; i < floatVec.length; i++) {
    const scaled = Math.round(((floatVec[i] - vmin) / range) * 255) - 128;
    // clamp for safety against float rounding at the edges
    q[i] = Math.max(-128, Math.min(127, scaled));
  }
  return { vec: q, vmin, vmax };
}

// --- main -------------------------------------------------------------------

async function main() {
  const sources = collectSources();
  const loaded = [];
  for (const s of sources) {
    const arr = JSON.parse(readFileSync(s.path, 'utf8'));
    if (!Array.isArray(arr) || arr.length === 0) {
      throw new Error(`Source ${s.rel} is empty or not an array.`);
    }
    for (const e of arr) loaded.push({ src: e, from: s.rel });
  }
  process.stdout.write(`[build] ${sources.length} sources, ${loaded.length} entries total\n`);

  const seenIds = new Set();
  const entries = [];
  for (let i = 0; i < loaded.length; i++) {
    const { src, from } = loaded[i];

    // ensure globally-unique ids across slices
    let id = src.id;
    if (seenIds.has(id)) {
      let n = 2;
      while (seenIds.has(`${id}-${n}`)) n++;
      id = `${id}-${n}`;
    }
    seenIds.add(id);

    const sectionAliases = deriveSectionAliases(src);
    const codes = deriveCodes(src, sectionAliases);
    const searchText = composeSearchText(src, sectionAliases);

    const floatVec = await embedPassage(searchText);
    if (floatVec.length !== DIM) {
      throw new Error(`Embedding dim mismatch for ${id}: got ${floatVec.length}, expected ${DIM}`);
    }
    const { vec, vmin, vmax } = quantizeInt8(floatVec);

    entries.push({
      ...src,            // carry ALL authoring fields through untouched
      id,                // de-duplicated
      sourceFile: from,  // provenance
      sectionAliases,    // build-time
      codes,             // build-time: lexical precision keys (sections + HSN/SAC)
      searchText,        // build-time
      vec,               // int8 quantized embedding
      vmin,
      vmax,
    });

    if ((i + 1) % 20 === 0 || i === loaded.length - 1) {
      process.stdout.write(`[build] embedded ${i + 1}/${loaded.length}\n`);
    }
  }

  const byTopic = {};
  for (const e of entries) byTopic[e.topic] = (byTopic[e.topic] || 0) + 1;

  const artifact = {
    model: activeModelName(),
    dim: DIM,
    builtFrom: sources.map((s) => s.rel),
    builtAt: new Date().toISOString(),
    count: entries.length,
    byTopic,
    quant: 'int8-per-vector-minmax',
    entries,
  };

  writeFileSync(OUT_PATH, JSON.stringify(artifact, null, 2) + '\n', 'utf8');

  process.stdout.write(
    `\n[build] wrote ${OUT_PATH}\n` +
      `[build] model=${artifact.model}  dim=${artifact.dim}  count=${artifact.count}  topics=${JSON.stringify(byTopic)}\n` +
      (usingFallback()
        ? `[build] NOTE: used the deterministic FALLBACK embedder (no bge run).\n`
        : `[build] real bge-small-en-v1.5 embeddings.\n`)
  );
}

main().catch((err) => {
  process.stderr.write(`[build] FAILED: ${err?.stack ?? err}\n`);
  process.exit(1);
});
