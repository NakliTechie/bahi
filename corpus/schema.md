# Bahi CA-lookup corpus — entry schema (v0)

This is the formal schema for a single corpus entry in Bahi's CA-lookup
sidecar. It has two layers:

1. **Authoring fields** — what a human (or the bake-off pipeline) writes. These
   are the source of truth, hand-reviewable, and the only thing a CA edits.
   Seeded from `plan/corpus-bakeoff/merged-tds.json` (23 TDS/TCS entries).
2. **Build-time / retrieval fields** — derived by `build.mjs` and never edited
   by hand. They make an entry searchable on-device.

The built artifact `ca-corpus.v0.json` carries both layers per entry, plus a
small header describing how it was built.

---

## 1. Authoring fields

| Field | Type | Req | Meaning |
|-------|------|-----|---------|
| `id` | string | yes | Stable unique id, e.g. `tds-194j`, `tcs-206c-1h`. Used as the citation key and dedup key. |
| `topic` | string | yes | Top-level bucket: `TDS`, `TCS`, (later: `GST`, `IncomeTax`…). |
| `subtopic` | string | no | Finer bucket within a topic, e.g. `professional-services`, `rent`, `cash`. Optional; many seed entries instead lean on `section` + `tags`. |
| `section` | string | yes | The legacy **section number** the field is universally known by, e.g. `194J`, `206C(1)`. This is the primary human handle and the dominant search token (see §3, BOTH-Act aliasing). |
| `title` | string | yes | Short human title, e.g. "TDS on professional or technical services". |
| `body` | string | yes | 1–3 sentence plain-language explanation of when the provision applies. |
| `rate` | string | no* | The withholding rate(s), with conditionals spelled out (e.g. "1% individual/HUF; 2% others"). Free text because rates are rarely a single number. `*`Optional only for pure pointer/repealed entries. |
| `rate_no_pan` | string | no | Rate when payee has no/inoperative PAN (Sec 206AA/206CC), e.g. "20%". Carried from the seed; many sections share "20%" but several differ (194O/194Q = 5%). |
| `threshold` | string | no* | Monetary threshold(s) below which no tax is deducted/collected, with the basis (per-year / per-month / per-contract) spelled out. |
| `payer` | string | no | Who must deduct/collect (the deductor/collector). |
| `payee` | string | no | Who receives the payment (the deductee/collectee). |
| `sources` | array | yes | Provenance. Each item: `{ name, url, ref }`. `ref` should name the statutory section (e.g. "Sec 194J, Income-tax Act 1961"). At least one source required — the sidecar must always be able to cite. |
| `effectiveFrom` | string | yes | When the stated position takes effect. Mixed formats in the seed (`"FY 2026-27"`, `"2025-04-01"`); v0 keeps them as-is. **Normalize to ISO `YYYY-MM-DD` in a later pass.** |
| `effectiveTo` | string | no | When the position stops applying (for superseded/repealed provisions). Absent ⇒ currently in force. |
| `confidence` | enum | yes | `high` \| `medium` \| `low`. How sure we are of the stated rate/threshold. Surfaced in the UI so the CA knows when to double-check. |
| `caveats` | string | no | Important exceptions, stale-chart warnings, and "CA must verify" notes. Often the most valuable field for a practising CA. |
| `reviewFlags` | string[] | no | Open divergences from the bake-off / verifier that a CA still needs to resolve. Their presence means "not yet CA-signed-off". |
| `actNew2025` | string | no | Mapping to the **Income-tax Act 2025** (eff 01-04-2026): the new section (e.g. `Sec 393(1)`) and any tentative challan code. See §3 for why both Act numbers are kept. |
| `payer` / `payee` / `status` | — | — | `status` is a workflow flag from the seed (e.g. `draft-for-CA-review`); carried through untouched. |

> Authoring rule: never silently change a `rate`/`threshold` without updating
> `sources` and `effectiveFrom`/`effectiveTo`. The corpus's value is that every
> claim is dated and cited.

---

## 2. Build-time / retrieval fields

These are added by `build.mjs` and stored alongside the authoring fields in
`ca-corpus.v0.json`. **Hand-editing them is meaningless — rebuild instead.**

| Field | Type | Meaning |
|-------|------|---------|
| `searchText` | string | The composed searchable text that was actually embedded (see §3). Stored for transparency/debugging and to drive the lexical channel of hybrid retrieval. |
| `sectionAliases` | string[] | All section handles this entry should match on, e.g. `["393(1)", "194J"]` — the 2025-Act section first (primary), the 1961 number as alias. Drives the lexical exact-match boost. |
| `vec` | int8[] | The int8-quantized embedding of `searchText` (length = `dim`). |
| `vmin` / `vmax` | number | Per-vector quantization bounds. Dequantize with the formula in §4 to recover the approximate float vector for cosine similarity. |

### Artifact header (`ca-corpus.v0.json` top level)

```jsonc
{
  "model":     "bge-small-en-v1.5",   // or "hashed-bow-fallback" in no-net runs
  "dim":       384,
  "builtFrom": "plan/corpus-bakeoff/merged-tds.json",
  "builtAt":   "<ISO timestamp>",
  "count":     23,
  "quant":     "int8-per-vector-minmax",
  "entries":   [ /* authoring + build-time fields, one per entry */ ]
}
```

---

## 3. Searchable text composition & section aliasing

### 3a. Searchable text

`build.mjs` composes one `searchText` per entry by concatenating, in order:

```
title . body . "Section <section>." . "Also Sec <actNew2025-section>." .
  rate . threshold . tags-joined . extracted-key-terms
```

Rationale:
- **title + body** carry the semantic meaning the embedder keys on.
- **section (both Act numbers)** is injected as text so the *vector* channel
  also has some signal on "194J", not just the lexical channel.
- **rate + threshold** let queries like "194J threshold" or "10% professional"
  land semantically.
- **tags + key terms** (synonyms a user might type: "rent", "freelancer",
  "consultant", "cash withdrawal") widen recall.

The exact same composition is irrelevant to the *query* side — queries are
embedded raw (with the bge query prefix). What must match exactly is the
**model + pooling + normalization** (see §4), not the text recipe.

### 3b. BOTH-Act section aliasing (decision)

The Income-tax Act 1961 was repealed w.e.f. 01-04-2026 and replaced by the
**Income-tax Act 2025**. Provisions formerly known by 1961 numbers (194J, 194I,
206C(1)…) now live under new sections (mostly `Sec 393(x)` for non-salary TDS,
`Sec 392` for salary, `Sec 394` for TCS).

**Decision for v0:** key each entry on **both** numbers in `sectionAliases`,
with the **2025-Act section as primary** and the **1961 number as an alias**:

```
sectionAliases = [ <2025-Act section, e.g. "393(1)">, <1961 section, e.g. "194J"> ]
```

Why this ordering:
- The 2025 Act is the law in force for the periods Bahi targets (FY 2026-27+),
  so the *authoritative* handle is the new section. Making it primary future-
  proofs the corpus as people migrate their mental model.
- But **every practising CA, every existing chart, and every user query today
  still says "194J"/"194I"/"194C".** Dropping the legacy number would tank
  recall. So the 1961 number stays as a first-class alias that the lexical
  boost matches on with equal weight.
- `id` deliberately keeps the legacy number (`tds-194j`) as the citation key,
  because that is what users recognize. The alias list is what *retrieval*
  matches; `id` is what the *UI* shows.

`build.mjs` derives `sectionAliases` from `section` (1961) and the section
parsed out of `actNew2025` (2025). The lexical channel in `retrieve.mjs`
matches a query's section tokens against this list.

---

## 4. Embedding, pooling, quantization (the parity contract)

The single most important invariant of this whole design:

> **Precomputed corpus vectors and the in-browser query vector must come from
> the identical model, pooling, and normalization.** Any drift makes cosine
> scores meaningless.

So the contract — implemented once in `embed.mjs` and reused by both
`build.mjs` and `retrieve.mjs` — is:

1. **Model:** `bge-small-en-v1.5` (ONNX: `Xenova/bge-small-en-v1.5`), 384-dim.
   Pinned. The browser must load the same model id.
2. **Pooling:** **mean-pooling** over token embeddings (not CLS).
3. **Normalization:** **L2-normalize** the pooled vector, so a dot product
   equals cosine similarity.
4. **bge asymmetry:** passages embedded as-is; **queries** get the prefix
   `"Represent this sentence for searching relevant passages: "`. The browser
   query embedder must prepend the same string.

### int8 quantization (per-vector min/max)

Float32×384 ≈ 1.5 KB/entry; int8 cuts that ~4×, which matters when the corpus
ships in-browser. We quantize **per vector** (each entry keeps its own
`vmin`/`vmax`) for tighter range than a global scale:

```
# quantize (build time)
vmin = min(vec); vmax = max(vec)
q[i] = round( (vec[i] - vmin) / (vmax - vmin) * 255 ) - 128   # int8, [-128,127]

# dequantize (retrieve time)
vec[i] ≈ ( (q[i] + 128) / 255 ) * (vmax - vmin) + vmin
```

Cosine is then computed on the **dequantized** corpus vector vs the **full-
precision query** vector. (Quantizing only the stored corpus keeps query-side
math exact; the small quantization error on the corpus side is well within
retrieval tolerance for top-k.)

---

## 5. Hybrid retrieval (what `retrieve.mjs` does)

Pure vector search is fuzzy on exact codes — "194J" and "194C" are near-
synonyms to an embedder. So retrieval is **hybrid**:

- **Semantic channel:** cosine(query_vec, dequantized entry_vec).
- **Lexical boost:** regex-extract precision tokens from the query — section
  codes like `194J`, `206C(1H)`, and bare digit codes like `194` — and add a
  fixed boost when they exact-match an entry's `sectionAliases` (or appear in
  its `searchText`). This rescues exact-code queries that semantics alone would
  rank loosely.

Final score = `cosine + Σ(lexical boosts)`, then rank descending. The boost is
tuned so a precise section match reliably wins, without drowning out genuinely
semantic matches when no code is present in the query.
