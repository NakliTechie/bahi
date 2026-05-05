"""
Smart Capture (v1.1) audit-tag tests for the Bahi sample .khata files.

Seeds the regression net for actor='ai' tagging, aiAssisted payload flags,
and BYOK key leakage. The three pre-existing sample files (pharma, manufacturing,
consulting) all predate Smart Capture, so the "no AI entries" assertions are
expected to pass cleanly today and would only fail if the AI runtime were ever
to silently inject an entry into them.

The four AI-originated tests (T05-T08) are skeleton-skipped today because there
isn't yet a sample .khata containing AI-originated entries. Once a Smart Capture
gate-1 sample is generated (e.g. via the v1.1.0 gate sequence in agent §13),
flip the @unittest.skip marker off and they exercise the real flow.

Covers (per spec §8.3 / agent §14):
    T01. No actor='ai' rows in pre-AI sample files
    T02. No aiAssisted=true payloads in pre-AI sample files
    T03. Every actor value belongs to the v10 enum {owner, ca, system, ai}
    T04. No BYOK key prefix appears anywhere in the .khata blob
    T05. AI-originated entries write actor='ai' correctly                (skeleton)
    T06. CA mode + AI yields actor='ca' + aiAssisted=true                (skeleton)
    T07. Hash chain verifies across mixed-actor sessions                 (skeleton)
    T08. .khata round-trip preserves actor + aiAssisted payload values   (skeleton)

Run:
    python3 -m unittest sample-data/test_smart_capture.py -v
"""

import json
import os
import re
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

SAMPLE_DIR = Path("/Users/chiragpatnaik/Code/Browser/Bahi/sample-data")

FILES = {
    "pharma":        SAMPLE_DIR / "pharma.khata",
    "manufacturing": SAMPLE_DIR / "manufacturing.khata",
    "consulting":    SAMPLE_DIR / "consulting.khata",
}

# Per khata-standard PR #22 (extends the actor enum from owner|ca|system to
# owner|ca|system|ai). Match exactly what the audit-log spec accepts.
VALID_ACTORS = {"owner", "ca", "system", "ai"}

# Known BYOK API key prefixes. If any of these patterns shows up in a saved
# file, the export-time scrub or some other path leaked a credential.
BYOK_KEY_PREFIX_PATTERNS = [
    r"sk-ant-[A-Za-z0-9_-]{16,}",          # Anthropic
    r"sk-[A-Za-z0-9]{20,}",                 # OpenAI / Mistral
    r"sk-or-v1-[A-Za-z0-9]{16,}",           # OpenRouter
]


_TMP_PATHS = {}


def open_khata(path):
    """Returns (manifest_dict, sqlite3.Connection, raw_blob_bytes)."""
    z = zipfile.ZipFile(path)
    manifest = json.loads(z.read("manifest.json"))
    data = z.read("books.sqlite")
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tf.write(data)
    tf.close()
    con = sqlite3.connect(tf.name)
    con.row_factory = sqlite3.Row
    _TMP_PATHS[id(con)] = tf.name
    return manifest, con, data


def close_khata(con):
    path = _TMP_PATHS.pop(id(con), None)
    con.close()
    if path and os.path.exists(path):
        os.unlink(path)


def read_full_blob(path):
    with open(path, "rb") as f:
        return f.read()


class SmartCaptureBase(unittest.TestCase):
    """Opens every sample file once per test class."""

    @classmethod
    def setUpClass(cls):
        cls.books = {}
        for name, path in FILES.items():
            if not path.exists():
                continue
            m, con, raw = open_khata(path)
            cls.books[name] = {
                "manifest": m,
                "con":      con,
                "books":    raw,
                "fullBlob": read_full_blob(path),
                "path":     path,
            }

    @classmethod
    def tearDownClass(cls):
        for b in cls.books.values():
            close_khata(b["con"])


# ───────────────────────── T01 — actor='ai' regression net ─────

class TestNoAiRows(SmartCaptureBase):

    def test_T01_no_actor_ai_in_pre_ai_samples(self):
        for name, b in self.books.items():
            rows = b["con"].execute(
                "SELECT COUNT(*) AS c FROM audit_log WHERE actor = 'ai'"
            ).fetchone()
            self.assertEqual(
                rows["c"], 0,
                f"{name}: pre-AI sample contains actor='ai' rows; was AI accidentally introduced?"
            )


# ───────────────────────── T02 — aiAssisted regression net ─────

class TestNoAiAssistedPayload(SmartCaptureBase):

    def test_T02_no_aiAssisted_true_in_payloads(self):
        for name, b in self.books.items():
            rows = b["con"].execute(
                "SELECT COUNT(*) AS c FROM audit_log WHERE payload LIKE '%\"aiAssisted\":true%'"
            ).fetchone()
            self.assertEqual(
                rows["c"], 0,
                f"{name}: payload contains aiAssisted=true; pre-AI sample shouldn't carry this flag"
            )


# ───────────────────────── T03 — actor enum sanity ─────

class TestActorEnum(SmartCaptureBase):

    def test_T03_every_actor_in_enum(self):
        for name, b in self.books.items():
            rows = b["con"].execute(
                "SELECT DISTINCT actor FROM audit_log"
            ).fetchall()
            for r in rows:
                self.assertIn(
                    r["actor"], VALID_ACTORS,
                    f"{name}: unknown actor value '{r['actor']}'; expected one of {sorted(VALID_ACTORS)}"
                )


# ───────────────────────── T04 — BYOK key leakage scan ─────

class TestNoBYOKKeyLeakage(SmartCaptureBase):

    def test_T04_no_byok_key_prefix_in_full_blob(self):
        compiled = [re.compile(p) for p in BYOK_KEY_PREFIX_PATTERNS]
        for name, b in self.books.items():
            blob = b["fullBlob"]
            try:
                text = blob.decode("utf-8", errors="replace")
            except Exception:
                text = ""
            for rx in compiled:
                m = rx.search(text)
                self.assertIsNone(
                    m,
                    f"{name}: matched BYOK key prefix pattern {rx.pattern!r} at position {m.start() if m else -1}; "
                    "the export-time scrub or some other path leaked a credential."
                )


# ───────────────────────── T05–T08 — AI-originated round-trip skeletons ─────
#
# These need a sample .khata containing genuine AI-originated entries (Stage 2
# bill ingest accept flow). Generate one via the v1.1.0 gate sequence in
# agent-handoff §13, then drop @unittest.skip and parameterise FILES_AI below.

FILES_AI = {
    "pharma_ai": SAMPLE_DIR / "pharma_ai.khata",
}


@unittest.skipIf(not FILES_AI, "no AI-originated sample .khata yet — generate via v1.1.0 gate")
class TestAiOriginatedSamples(unittest.TestCase):

    def test_T05_actor_ai_present_in_owner_mode_ai_accepts(self):
        for name, path in FILES_AI.items():
            m, con, _ = open_khata(path)
            try:
                rows = con.execute(
                    "SELECT COUNT(*) AS c FROM audit_log WHERE actor = 'ai'"
                ).fetchone()
                self.assertGreater(
                    rows["c"], 0,
                    f"{name}: sample marked as AI-originated but no actor='ai' rows present"
                )
            finally:
                close_khata(con)

    def test_T06_ca_mode_ai_accept_marks_aiAssisted_true(self):
        # Walks audit_log rows where actor='ca' and verifies any AI-assisted entries
        # carry aiAssisted=true in the canonical-JSON payload.
        for name, path in FILES_AI.items():
            m, con, _ = open_khata(path)
            try:
                rows = con.execute(
                    "SELECT payload FROM audit_log WHERE actor = 'ca'"
                ).fetchall()
                # At least one CA row should carry aiAssisted=true if the scenario covers it.
                ai_assisted_count = sum(
                    1 for r in rows
                    if json.loads(r["payload"]).get("aiAssisted") is True
                )
                self.assertGreaterEqual(
                    ai_assisted_count, 1,
                    f"{name}: CA-mode AI-accept scenario should produce >=1 ca row with aiAssisted=true"
                )
            finally:
                close_khata(con)

    def test_T07_hash_chain_verifies_across_mixed_actors(self):
        import hashlib
        for name, path in FILES_AI.items():
            m, con, _ = open_khata(path)
            try:
                rows = con.execute(
                    "SELECT origin, payload, prev_hash, hash FROM audit_log ORDER BY id ASC"
                ).fetchall()
                prev = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
                # Bahi's existing chain uses raw 64-hex (no sha256: prefix); fall back to that
                if rows and not rows[0]["prev_hash"].startswith("sha256:"):
                    prev = "0" * 64
                bad = 0
                for r in rows:
                    if r["prev_hash"] != prev:
                        bad += 1
                        prev = r["hash"]
                        continue
                    combined = (prev + (r["origin"] or "") + r["payload"]).encode("utf-8")
                    computed = hashlib.sha256(combined).hexdigest()
                    if computed != r["hash"]:
                        bad += 1
                    prev = r["hash"]
                self.assertEqual(bad, 0, f"{name}: hash chain has {bad} broken link(s)")
            finally:
                close_khata(con)

    def test_T08_round_trip_preserves_actor_and_aiAssisted(self):
        # Reads each AI sample, re-zips its parts byte-for-byte equivalent, re-opens,
        # asserts every actor value AND every aiAssisted flag survives the trip.
        for name, path in FILES_AI.items():
            with zipfile.ZipFile(path) as z_in:
                manifest_in = z_in.read("manifest.json")
                books_in = z_in.read("books.sqlite")
                # Round-trip
                tf_out = tempfile.NamedTemporaryFile(delete=False, suffix=".khata")
                tf_out.close()
                with zipfile.ZipFile(tf_out.name, "w", zipfile.ZIP_DEFLATED) as z_out:
                    z_out.writestr("manifest.json", manifest_in)
                    z_out.writestr("books.sqlite", books_in)
                try:
                    m_in, con_in, _ = open_khata(path)
                    m_out, con_out, _ = open_khata(Path(tf_out.name))
                    in_rows = con_in.execute(
                        "SELECT actor, payload FROM audit_log ORDER BY id"
                    ).fetchall()
                    out_rows = con_out.execute(
                        "SELECT actor, payload FROM audit_log ORDER BY id"
                    ).fetchall()
                    self.assertEqual(len(in_rows), len(out_rows), f"{name}: row count drifted")
                    for i, (a, b) in enumerate(zip(in_rows, out_rows)):
                        self.assertEqual(a["actor"], b["actor"], f"{name}: row {i} actor drift")
                        self.assertEqual(
                            json.loads(a["payload"]).get("aiAssisted"),
                            json.loads(b["payload"]).get("aiAssisted"),
                            f"{name}: row {i} aiAssisted drift",
                        )
                    close_khata(con_in)
                    close_khata(con_out)
                finally:
                    if os.path.exists(tf_out.name):
                        os.unlink(tf_out.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
