# Phase 0 — CA-lookup engine spine: retrieval results

**Status: PASS.** The real `bge-small-en-v1.5` model downloaded and embedded in
this run (no fallback). All five sample queries return the correct entry at
top-1 via hybrid (semantic + lexical) retrieval.

## What ran

| | |
|---|---|
| Model | **bge-small-en-v1.5** (`Xenova/bge-small-en-v1.5`, ONNX q8) — REAL model, not fallback |
| Embedding | mean-pooling + L2-normalization; bge query prefix on queries only |
| Dim | 384 |
| Corpus | 23 TDS/TCS entries from `plan/corpus-bakeoff/merged-tds.json` |
| Quantization | int8, per-vector min/max |
| Artifact | `corpus/ca-corpus.v0.json` (~174 KB) |
| Retrieval | hybrid = cosine(query, dequantized vec) + lexical section-code boost |

Reproduce: `cd corpus && node build.mjs && node retrieve.mjs`

## Top-5 per sample query (verbatim from `retrieve.mjs`)

```
[retrieve] corpus model=bge-small-en-v1.5 dim=384 count=23
[retrieve] query embedder=bge-small-en-v1.5
[retrieve] top-5, hybrid = cosine + lexical section boost
========================================================================

QUERY: "what is the TDS rate on rent"
  1. score=0.780  cos=0.780
     tds-194i [194I] — TDS on rent
     rate: 2% for use of plant, machinery or equipment [sec 194-I(a)]; 10% for use of land, building…
  2. score=0.752  cos=0.752
     tds-194ib [194IB] — TDS on rent paid by individuals/HUF (not under audit)
     rate: 2% (reduced from 5% by the Finance/No.2 Act 2024 w.e.f. 01-10-2024).
  3. score=0.685  cos=0.685
     tds-194ia [194IA] — TDS on transfer of immovable property
     rate: 1%
  4. score=0.682  cos=0.682
     tds-193 [193] — TDS on interest on securities
     rate: 10%
  5. score=0.676  cos=0.676
     tds-194h [194H] — TDS on commission or brokerage
     rate: 2% (reduced from 5% by the Finance/No.2 Act 2024 w.e.f. 01-10-2024).

QUERY: "is professional fee subject to TDS"
  1. score=0.799  cos=0.799
     tds-194j [194J] — TDS on professional or technical services
     rate: 10% in general (professional fees, royalty, non-compete). 2% for fees for technical servi…
  2. score=0.694  cos=0.694
     tds-194t [194T] — TDS on partner remuneration / interest
     rate: 10%
  3. score=0.683  cos=0.683
     tds-194c [194C] — TDS on payments to contractors
     rate: 1% if payee is an individual or HUF; 2% if payee is any other person (company, firm, etc.)
  4. score=0.682  cos=0.682
     tds-195 [195] — TDS on payments to non-residents
     rate: Varies by nature of income — there is no single rate. Common 'rates in force' include 20%…
  5. score=0.678  cos=0.678
     tds-193 [193] — TDS on interest on securities
     rate: 10%

QUERY: "194J threshold" [precision tokens: 194J]
  1. score=1.082  cos=0.482 +boost 0.60 (alias=194J)
     tds-194j [194J] — TDS on professional or technical services
     rate: 10% in general (professional fees, royalty, non-compete). 2% for fees for technical servi…
  2. score=0.537  cos=0.537
     tds-194h [194H] — TDS on commission or brokerage
     rate: 2% (reduced from 5% by the Finance/No.2 Act 2024 w.e.f. 01-10-2024).
  3. score=0.533  cos=0.533
     tds-194q [194Q] — TDS on purchase of goods
     rate: 0.1% on the purchase value exceeding Rs 50 lakh in the financial year.
  4. score=0.532  cos=0.532
     tds-193 [193] — TDS on interest on securities
     rate: 10%
  5. score=0.523  cos=0.523
     tds-194k [194K] — TDS on income from mutual-fund units
     rate: 10%

QUERY: "TDS on cash withdrawal"
  1. score=0.813  cos=0.813
     tds-194n [194N] — TDS on cash withdrawals
     rate: 2% on cash withdrawal exceeding Rs 1 crore (for persons who have filed ITR). For non-file…
  2. score=0.717  cos=0.717
     tds-192a [192A] — TDS on premature EPF withdrawal
     rate: 10% on the taxable accumulated balance
  3. score=0.678  cos=0.678
     tds-194s [194S] — TDS on transfer of virtual digital assets
     rate: 1% of the consideration.
  4. score=0.657  cos=0.657
     tds-194 [194] — TDS on dividend
     rate: 10%
  5. score=0.654  cos=0.654
     tds-194q [194Q] — TDS on purchase of goods
     rate: 0.1% on the purchase value exceeding Rs 50 lakh in the financial year.

QUERY: "tax on partner remuneration"
  1. score=0.762  cos=0.762
     tds-194t [194T] — TDS on partner remuneration / interest
     rate: 10%
  2. score=0.637  cos=0.637
     tds-192 [192] — TDS on salary
     rate: Average rate of income-tax on estimated total salary (i.e. the employee's slab rate, incl…
  3. score=0.622  cos=0.622
     tds-194r [194R] — TDS on benefits or perquisites
     rate: 10% on the value/aggregate value of the benefit or perquisite.
  4. score=0.617  cos=0.617
     tds-195 [195] — TDS on payments to non-residents
     rate: Varies by nature of income — there is no single rate. Common 'rates in force' include 20%…
  5. score=0.614  cos=0.614
     tds-194d [194D] — TDS on insurance commission
     rate: 2% if payee is a resident other than a company; 10% if payee is a domestic company. (Rate…
```

### Extra spot-checks (lexical channel branches)

The five required queries only exercise one boost branch (exact alias), so two
more were run to validate the others. Both correct:

```
QUERY: "206C(1H) tcs sale of goods" [precision tokens: 206C(1H)]
  1. score=1.355  cos=0.755 +boost 0.60 (alias=206C(1H))   tcs-206c-1h [206C(1H)] — TCS on sale of goods (ABOLISHED…)
  2. score=0.688  cos=0.688                                 tcs-206c-1  [206C(1)]  — TCS on alcohol, scrap, minerals…

QUERY: "194-IA property purchase" [precision tokens: 194IA, 194]
  1. score=1.153  cos=0.553 +boost 0.60 (alias=194IA)       tds-194ia [194IA] — TDS on transfer of immovable property
  2. score=0.802  cos=0.552 +boost 0.25 (digits=194)        (a 194-family entry, weaker bare-digit boost)
```

## Retrieval quality notes

- **Top-1 correct on all five sample queries**, and the runners-up are
  sensible neighbours, not noise:
  - "rate on rent" → **194I** (rent), with **194IB** (small-payer rent) at #2 —
    exactly the two rent sections, ranked the way a CA would expect.
  - "cash withdrawal" → **194N**, with **192A** (premature *EPF withdrawal*) at
    #2 — a reasonable semantic cousin on the word "withdrawal".
  - "partner remuneration" → **194T**, with salary/perquisite/non-resident
    sections trailing.
- **The lexical boost earns its keep on code queries.** For `"194J threshold"`,
  bare cosine ranked 194J at only **0.482** (it would have landed ~6th, because
  "threshold" pulls toward every section that has a threshold). The exact
  section-alias boost (+0.60) lifts it to **1.082 — a decisive #1**. This is the
  precise failure mode pure-vector search has with statutory codes, and why
  retrieval is hybrid.
- **Score bands are healthy**: genuine semantic hits sit ~0.68–0.81 cosine;
  the long tail drops off. int8 quantization did not visibly degrade ranking
  (per-vector min/max keeps round-trip error small for top-k).
- **Small-corpus caveat:** with only 23 entries every query has a "right"
  answer present, so this validates *wiring and ranking behaviour*, not recall
  at scale. As the corpus grows (GST, income-tax, etc.) the boost weights
  (`BOOST_SECTION_ALIAS=0.6`, etc. in `retrieve.mjs`) may need re-tuning, and a
  score floor / "no confident match" threshold should be added before this is
  user-facing.

## The embed-parity constraint (load-bearing)

> **Precomputed corpus vectors and the in-browser query vector MUST come from
> the identical model + pooling + normalization.** Any drift makes the cosine
> scores meaningless — the corpus and the query would live in different vector
> spaces.

How the spine enforces this so the port to `index.html` can't silently break it:

1. **One shared code path.** Both `build.mjs` (passages) and `retrieve.mjs`
   (queries) embed through the *same* `embed.mjs` module — same model id
   (`bge-small-en-v1.5`), same mean-pool, same L2-norm, same bge query prefix
   (`"Represent this sentence for searching relevant passages: "`). When this
   is ported in-browser, `embed.mjs` is the literal contract the browser query
   embedder must reproduce.
2. **The artifact self-describes its model.** `ca-corpus.v0.json` records
   `"model": "bge-small-en-v1.5"`. `retrieve.mjs` compares that against the
   active query embedder and prints a loud **PARITY WARNING** (and explains the
   scores aren't comparable) if they differ — so a mismatched browser model
   can't pass silently.
3. **Quantization is one-sided.** Only the stored corpus vectors are int8; the
   query stays full-precision and cosine divides by the dequantized vector's
   norm. So quantization adds a small, bounded error on the corpus side only —
   it does not break parity.

## Fallback path (implemented, not exercised this run)

`embed.mjs` also implements a deterministic **hashed bag-of-words** fallback
(`hashedEmbed`): tokenize → md5-hash each token into a 384-bucket signed
vector → L2-normalize. It triggers only if the bge model can't be fetched
(offline sandbox). It shares the same pooling *contract* (an L2-normalized
fixed-dim vector) so build/retrieve stay parity-correct **against each other**,
which proves the retrieval math end-to-end without a network.

It is **NOT** semantically equivalent to bge and must never ship. **This run did
not use it** — the real bge model loaded. If you run in an offline environment,
the scripts will print `model=hashed-bow-fallback` and a note that the bge
wiring still needs a network-enabled run to validate semantic quality; that
validation has now been done here.
