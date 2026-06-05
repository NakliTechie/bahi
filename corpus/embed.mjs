// corpus/embed.mjs
// ---------------------------------------------------------------------------
// SHARED embedding code path for Bahi's CA-lookup sidecar (Phase 0 spine).
//
// WHY a shared module:
//   The whole point of precomputing corpus vectors at build time is that the
//   browser, at query time, must embed the user's question with the EXACT same
//   model + pooling + normalization. If build-time and query-time embeddings
//   diverge by even a pooling detail, cosine scores become meaningless. So both
//   build.mjs (passages) and retrieve.mjs (queries) import embed() from here.
//   When this spine is ported into index.html, this file IS the contract the
//   in-browser embedder must reproduce.
//
// MODEL (pinned): BAAI/bge-small-en-v1.5  — 384-dim, English, retrieval-tuned.
//   - mean-pooling over token embeddings (NOT CLS pooling)
//   - L2-normalize the pooled vector (so dot product == cosine similarity)
//   - bge asymmetric handling: QUERIES get a fixed instruction prefix;
//     PASSAGES are embedded as-is. This is the documented bge usage.
//
// FALLBACK (no-network sandboxes):
//   If the model can't be fetched, we fall back to a deterministic hashed
//   bag-of-words embedding so the retrieval MATH still runs end-to-end. The
//   fallback uses the SAME pooling contract (an L2-normalized fixed-dim vector)
//   so build/retrieve stay parity-correct against each other. It is NOT
//   semantically equivalent to bge — it only proves the pipeline wiring.
// ---------------------------------------------------------------------------

import { env, pipeline } from '@huggingface/transformers';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Pin the model cache to corpus/.cache so it is predictable + gitignored.
env.cacheDir = join(__dirname, '.cache');
// We rely on the network only for the first download; allow remote models.
env.allowRemoteModels = true;

// --- pinned model constants (exported so build/retrieve can record them) -----
export const MODEL_ID = 'Xenova/bge-small-en-v1.5'; // ONNX build of BAAI/bge-small-en-v1.5
export const MODEL_NAME = 'bge-small-en-v1.5';
export const DIM = 384;
// bge query instruction — prepended to QUERIES only, never to passages.
export const BGE_QUERY_PREFIX =
  'Represent this sentence for searching relevant passages: ';

// Fallback marker so callers can report which path actually ran.
export const FALLBACK_MODEL_NAME = 'hashed-bow-fallback';

let _extractor = null;       // cached transformers.js feature-extraction pipeline
let _usingFallback = false;  // flips true if the real model fails to load

/**
 * Lazily load the bge feature-extraction pipeline. On any failure (e.g. no
 * network in the sandbox) we mark fallback mode and return null; callers then
 * route through the deterministic hashed embedder.
 */
async function getExtractor() {
  if (_extractor || _usingFallback) return _extractor;
  try {
    _extractor = await pipeline('feature-extraction', MODEL_ID, {
      // quantized ONNX keeps the download small; pooling/normalize are applied
      // by us below so we control the exact contract.
      dtype: 'q8',
    });
  } catch (err) {
    _usingFallback = true;
    _extractor = null;
    process.stderr.write(
      `\n[embed] bge-small load FAILED (${err?.message ?? err}).\n` +
        `[embed] Falling back to deterministic hashed bag-of-words embeddings.\n` +
        `[embed] The real bge wiring is intact but needs a network-enabled run.\n\n`
    );
  }
  return _extractor;
}

/** True once a real-model load has been attempted and failed. */
export function usingFallback() {
  return _usingFallback;
}

/** The model name that actually produced vectors (for recording in artifacts). */
export function activeModelName() {
  return _usingFallback ? FALLBACK_MODEL_NAME : MODEL_NAME;
}

// --- math helpers ------------------------------------------------------------

/** L2-normalize a Float array in place; returns it. */
export function l2normalize(vec) {
  let sum = 0;
  for (let i = 0; i < vec.length; i++) sum += vec[i] * vec[i];
  const norm = Math.sqrt(sum) || 1; // guard against zero vector
  for (let i = 0; i < vec.length; i++) vec[i] /= norm;
  return vec;
}

/**
 * Deterministic hashed bag-of-words fallback embedding.
 *   - tokenize to lowercase word/number tokens
 *   - hash each token -> bucket in [0, DIM), accumulate (signed) counts
 *   - L2-normalize (same contract as the real path)
 * Identical text -> identical vector, so build/query stay parity-correct.
 */
export function hashedEmbed(text, dim = DIM) {
  const vec = new Float32Array(dim);
  const tokens = String(text)
    .toLowerCase()
    .match(/[a-z0-9]+/g) || [];
  for (const tok of tokens) {
    const h = createHash('md5').update(tok).digest();
    // first 4 bytes -> bucket; 5th byte's low bit -> sign (mild collision relief)
    const bucket = ((h[0] << 24) | (h[1] << 16) | (h[2] << 8) | h[3]) >>> 0;
    const sign = h[4] & 1 ? 1 : -1;
    vec[bucket % dim] += sign;
  }
  return Array.from(l2normalize(vec));
}

// --- public embedding API ----------------------------------------------------

/**
 * Embed raw text with mean-pooling + L2-normalization via bge-small.
 * (Low-level: no bge query/passage prefix is applied here.)
 * Falls back to hashedEmbed() if the model is unavailable.
 * @returns {Promise<number[]>} length-DIM float vector
 */
export async function embed(text) {
  const extractor = await getExtractor();
  if (!extractor) return hashedEmbed(text);
  // pooling:'mean' + normalize:true reproduces the browser contract exactly.
  const output = await extractor(text, { pooling: 'mean', normalize: true });
  return Array.from(output.data);
}

/**
 * Embed a PASSAGE (corpus entry searchable text). bge embeds passages as-is.
 */
export async function embedPassage(text) {
  return embed(text);
}

/**
 * Embed a QUERY. bge prepends a fixed instruction to queries only.
 * The in-browser query embedder MUST do the same to stay parity-correct.
 */
export async function embedQuery(text) {
  return embed(BGE_QUERY_PREFIX + text);
}
