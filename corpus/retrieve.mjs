// corpus/retrieve.mjs
// ---------------------------------------------------------------------------
// Hybrid retrieval harness for the Bahi CA-lookup corpus (v1, 181 entries).
//
//   load    corpus/ca-corpus.v1.json
//   embed   the query with the SAME model + pooling as build time (embed.mjs,
//           via embedQuery -> applies the bge query prefix)
//   score   HYBRID = cosine(query, dequantized entry vec)  +  lexical boost
//           for precision tokens that exact-match an entry's `codes`
//           (income-tax sections like 194J / 206C(1H) AND HSN/SAC like 8703)
//   gate    a no-confident-match floor: if the top hit is neither an exact
//           code match nor above COSINE_FLOOR, return "no confident match"
//   rank    descending; print top-5 per query
//
// Run:  node retrieve.mjs                 -> the built-in sample + off-topic set
//       node retrieve.mjs "your query"    -> a single ad-hoc query
//       node retrieve.mjs --calibrate     -> one-line-per-query floor calibration
// ---------------------------------------------------------------------------

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { embedQuery, activeModelName, usingFallback } from './embed.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CORPUS_PATH = join(__dirname, 'ca-corpus.v1.json');

const TOP_K = 5;
// Lexical boost weights. cosine(query,passage) with the bge prefix lands ~0.55-0.80
// for good hits and ~0.30-0.45 for off-topic, so an exact-code match worth ~0.6
// decisively promotes the right entry without drowning semantics.
const BOOST_EXACT = 0.6;   // a query code (section or HSN/SAC) is in entry.codes
const BOOST_FAMILY = 0.25; // bare 3-digit family (e.g. "194" -> any 194x section)

// No-confident-match floor. Calibrated against the off-topic probes below
// (cooking/weather sit ~0.41-0.45 cos here, real lookups ~0.55+), so 0.50 cleanly
// separates them. An exact code match always counts as confident regardless.
const COSINE_FLOOR = 0.50;

// --- load ------------------------------------------------------------------

function loadCorpus() {
  const raw = JSON.parse(readFileSync(CORPUS_PATH, 'utf8'));
  if (!raw.entries?.length) throw new Error(`No entries in ${CORPUS_PATH}`);
  return raw;
}

// --- math ------------------------------------------------------------------

/** Dequantize an int8 vector back to ~float using per-vector min/max. */
function dequantize(q, vmin, vmax) {
  const range = vmax - vmin || 1;
  const out = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) out[i] = ((q[i] + 128) / 255) * range + vmin;
  return out;
}

/** Cosine similarity; query is unit-length, corpus vec only approx after round-trip. */
function cosine(query, vec) {
  let dot = 0;
  let nv = 0;
  for (let i = 0; i < query.length; i++) {
    dot += query[i] * vec[i];
    nv += vec[i] * vec[i];
  }
  return dot / (Math.sqrt(nv) || 1);
}

// --- lexical channel -------------------------------------------------------

function normCode(s) {
  return String(s).toUpperCase().replace(/[\s-]/g, '');
}

/** Leading digit family of a code, e.g. "194IA" -> "194", "206C(1H)" -> "206". */
function digitFamily(code) {
  const m = String(code).match(/^\D*(\d{2,3})/);
  return m ? m[1] : '';
}

/**
 * Precision tokens from a query:
 *   strong  = income-tax section handles (194J, 206C(1H)) + HSN/SAC numbers
 *             (4-8 digit) + 2-digit chapter ONLY when cued ("chapter 61").
 *   family  = bare 3-digit numbers (income-tax family fallback, weaker boost).
 * Both normalized to the corpus `codes` style. We never treat a bare 2-digit
 * number as a code (avoids GST-rate / chapter collisions like "18%").
 */
function extractQueryCodes(query) {
  const strong = new Set();
  const family = new Set();
  let m;

  // section handles: 3-digit (+ optional alpha and/or paren sub-clause)
  const secRe = /\b(\d{3}(?:[-\s]?[A-Za-z]+)?(?:\s*\(\s*\d+\s*[A-Za-z]?\s*\))?)/g;
  while ((m = secRe.exec(query)) !== null) {
    const norm = normCode(m[1]);
    if (/[A-Z]/.test(norm) || /\(/.test(norm)) strong.add(norm);
  }
  // HSN/SAC: 4-8 digit
  const hsnRe = /\b(\d{4,8})\b/g;
  while ((m = hsnRe.exec(query)) !== null) strong.add(m[1]);
  // 2-digit chapter, cued only
  const chRe = /\b(?:chapter|hsn|heading)\s*:?\s*(\d{2})\b/gi;
  while ((m = chRe.exec(query)) !== null) strong.add(m[1]);
  // bare 3-digit family
  const famRe = /\b(\d{3})\b/g;
  while ((m = famRe.exec(query)) !== null) family.add(m[1]);

  return { strong, family };
}

/** Lexical boost for one entry. Returns { boost, why[], exact }. */
function lexicalBoost(entry, q) {
  const codes = (entry.codes ?? entry.sectionAliases ?? []).map(normCode);
  const why = [];
  let boost = 0;
  let exact = false;

  for (const c of q.strong) {
    if (codes.includes(c)) {
      boost += BOOST_EXACT;
      why.push(`code=${c}`);
      exact = true;
    }
  }
  if (!exact) {
    const families = new Set(codes.map(digitFamily).filter(Boolean));
    for (const d of q.family) {
      if (families.has(d)) {
        boost += BOOST_FAMILY;
        why.push(`fam=${d}`);
      }
    }
  }
  return { boost, why, exact };
}

// --- ranking ---------------------------------------------------------------

async function rank(corpus, query) {
  const qVec = await embedQuery(query);
  const q = extractQueryCodes(query);

  const scored = corpus.entries.map((entry) => {
    const vec = dequantize(entry.vec, entry.vmin, entry.vmax);
    const sim = cosine(qVec, vec);
    const { boost, why, exact } = lexicalBoost(entry, q);
    return { entry, sim, boost, why, exact, score: sim + boost };
  });

  scored.sort((a, b) => b.score - a.score);
  const top = scored[0];
  const confident = !!top && (top.exact || top.sim >= COSINE_FLOOR);
  return { q, results: scored.slice(0, TOP_K), confident, top };
}

// --- presentation ----------------------------------------------------------

function truncate(s, n) {
  if (!s) return '(n/a)';
  s = String(s).replace(/\s+/g, ' ').trim();
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

function fmtResult(r, idx) {
  const e = r.entry;
  const tag = e.section ? `[${e.section}]` : e.subtopic ? `[${e.subtopic}]` : '';
  const boostStr = r.boost > 0 ? ` +boost ${r.boost.toFixed(2)} (${r.why.join(',')})` : '';
  return (
    `  ${idx + 1}. score=${r.score.toFixed(3)}  cos=${r.sim.toFixed(3)}${boostStr}\n` +
    `     ${e.id} ${tag} — ${truncate(e.title, 80)}\n` +
    `     rate: ${truncate(e.rate, 90)}\n`
  );
}

const SAMPLE_QUERIES = [
  // income-tax / TDS-TCS
  'what is the TDS rate on rent',
  'is professional fee subject to TDS',
  '194J threshold',
  'TDS on cash withdrawal',
  'tax on partner remuneration',
  // GST goods / services / RCM
  'GST rate on cement',
  'GST on restaurant food',
  'GST rate for apparel',
  'is packaged drinking water taxed',
  'GST on buying a car',
  'reverse charge on legal fees from an advocate',
  'GST on goods transport agency',
  'HSN 8703',
  // income-tax basics
  'what is the section 87A rebate',
  'new regime income tax slabs',
  '80C deduction limit',
  // compliance
  'GSTR-3B due date',
  'when is advance tax due',
  // off-topic floor probes (should return NO confident match)
  'how do I cook pasta',
  'weather in mumbai tomorrow',
];

async function main() {
  const corpus = loadCorpus();
  const args = process.argv.slice(2);
  const calibrate = args.includes('--calibrate');
  const argQuery = args.filter((a) => a !== '--calibrate').join(' ').trim();
  const queries = argQuery ? [argQuery] : SAMPLE_QUERIES;

  process.stdout.write(
    `[retrieve] corpus model=${corpus.model} dim=${corpus.dim} count=${corpus.count}\n` +
      `[retrieve] query embedder=${activeModelName()}${usingFallback() ? ' (FALLBACK)' : ''}\n` +
      `[retrieve] hybrid = cosine + lexical code boost · floor=${COSINE_FLOOR}\n` +
      '='.repeat(74) + '\n'
  );

  if (corpus.model !== activeModelName()) {
    process.stdout.write(
      `[retrieve] !! PARITY WARNING: corpus="${corpus.model}" vs query="${activeModelName()}". ` +
        `Rebuild under the same model.\n` + '='.repeat(74) + '\n'
    );
  }

  if (calibrate) {
    // one line per query: top cosine, exact-match flag, confident verdict
    for (const qy of queries) {
      const { results, confident, top } = await rank(corpus, qy);
      const verdict = confident ? 'OK ' : 'NO ';
      process.stdout.write(
        `${verdict} cos=${top.sim.toFixed(3)} exact=${top.exact ? 'Y' : 'n'}  ` +
          `top=${top.entry.id.slice(0, 32).padEnd(32)}  "${qy}"\n`
      );
    }
    return;
  }

  for (const qy of queries) {
    const { q, results, confident, top } = await rank(corpus, qy);
    const tok = q.strong.size || q.family.size
      ? ` [tokens: ${[...q.strong, ...q.family].join(', ')}]`
      : '';
    process.stdout.write(`\nQUERY: "${qy}"${tok}\n`);
    if (!confident) {
      process.stdout.write(
        `  (no confident match — top cos=${top.sim.toFixed(3)} < floor ${COSINE_FLOOR}, no exact code)\n`
      );
      continue;
    }
    results.forEach((r, i) => process.stdout.write(fmtResult(r, i)));
  }
  process.stdout.write('\n');
}

main().catch((err) => {
  process.stderr.write(`[retrieve] FAILED: ${err?.stack ?? err}\n`);
  process.exit(1);
});
