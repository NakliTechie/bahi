# Corpus v1 — assembled + retrieval tuned (2026-06-05)

Builds on the Phase-0 spine (`PHASE0-RESULTS.md`). v1 ingests the **full bake-off output**
(TDS/TCS + the 6 workflow slices) into one searchable artifact and tunes hybrid retrieval at scale.

## Build — `ca-corpus.v1.json`

`build.mjs` generalized to ingest 7 sources (`plan/corpus-bakeoff/merged-tds.json` + `slices/*.json`):

- **181 entries**, real **bge-small-en-v1.5** (384-d, int8 per-vector min/max).
- byTopic: `GST 78 · GST-RCM 35 · Income-tax 23 · Compliance 22 · TDS 21 · TCS 2`.
- Handles both authoring shapes (TDS file has `section`/`actNew2025`; slices have `subtopic`/`tags`).
- New build-time **`codes`** field per entry = income-tax section aliases (e.g. `194J`, `393(1)`)
  **+ cued HSN/SAC/chapter codes** (e.g. chocolate→`1806/1905/1704`, apparel→`61`). Cue-gated
  (`HSN 2202`, `Chapter 87`) so years/amounts are never picked up as codes.
- Global id de-dup across slices; `sourceFile` provenance carried on each entry.

## Retrieval tuning — `retrieve.mjs`

Hybrid = `cosine(query, entry) + lexical boost`, then a confidence gate.

| Knob | Value | Rationale |
|---|---|---|
| `BOOST_EXACT` | 0.60 | query code (section **or** HSN/SAC) ∈ `entry.codes` — held from Phase 0, still clean at scale |
| `BOOST_FAMILY` | 0.25 | bare 3-digit family (`194` → any 194x) |
| `COSINE_FLOOR` | 0.50 | no-confident-match gate; **calibrated** (see below). Exact-code match always overrides. |

Query precision tokens now cover **HSN/SAC (4–8 digit) + cued 2-digit chapters**, not just income-tax
sections. Bare 2-digit numbers are never treated as codes (avoids `18%`/chapter-18 collisions).

## Calibration (20-query probe)

- **Off-topic correctly rejected:** `"weather in mumbai tomorrow"` → cos 0.434 < 0.50 → *no confident match*.
- **All tax queries admitted:** real lookups land cos 0.65–0.81; the floor sits cleanly below them.
- **Exact-code override works:** `"194J threshold"` cos was only 0.482 but the `194J` code match promotes it to #1.
- **Top-1 correct ~18/20.** Examples: rent→194I, prof-fee→194J, cash→194N, cement→18%, restaurant→composition,
  car→small-cars-18%, 87A→rebate entry, GSTR-3B→due-date entry.

## Known gaps / follow-ups (for Phase 1+)

1. **HSN-number lookups are patchy.** Entries only carry an HSN code where the *draft cued it*, so
   `"HSN 8703"` (cars) currently misses (the cars entry has no `8703` in `codes`) and falls back to a
   weak semantic match (footwear, 0.540). Fix: have the corpus drafters emit a **structured `hsn`/`sac`
   field per GST entry**, or add a build-time goods→HSN map. Natural-language ("GST on a car") already works.
2. **RCM specificity.** For `"reverse charge on legal fees"` the framework overview (0.652) edges out the
   specific legal-advocate entry (0.602). Both are top-2; a small boost for leaf/specific entries would flip them.
3. **`effectiveFrom` formats still mixed** (`"FY 2026-27"` vs ISO) — normalize in a future pass.
4. **Intent isn't classified:** `"how do I cook pasta"` (0.589) matches the pasta-GST entry. Acceptable — a
   CA-tool user typing "pasta" likely wants the rate; the floor only filters genuinely unrelated noise.

## Parity contract (unchanged, load-bearing)

The in-browser query embedder MUST reproduce `embed.mjs` exactly: bge-small-en-v1.5, **mean-pool + L2**,
**query prefix** `"Represent this sentence for searching relevant passages: "`. `retrieve.mjs` warns loudly
if the corpus model ≠ the query model.

## Files
`build.mjs` (generalized) · `retrieve.mjs` (v1 tuned) · `ca-corpus.v1.json` (artifact) · `CORPUS-V1-RESULTS.txt` (full top-5 run).
Run: `node build.mjs` then `node retrieve.mjs` (or `--calibrate`, or `"<query>"`).
