"""
Generate a sample .khata file containing AI-originated audit entries so the
Smart Capture v1.1 pytest suite (test_smart_capture.py) can exercise T05-T08.

Starts from pharma.khata, appends two new entries to the audit chain:
  1. An owner-mode AI accept              → actor='ai', no payload flag
  2. A CA-mode AI-assisted accept         → actor='ca', payload aiAssisted=true

Recomputes the chain and the manifest.integrity.auditHead so the file passes
hash-walk verification end-to-end.

Run:
    python3 sample-data/make_ai_sample.py
"""

import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path


SAMPLE_DIR = Path(__file__).resolve().parent
SOURCE = SAMPLE_DIR / "pharma.khata"
OUT    = SAMPLE_DIR / "pharma_ai.khata"


def canonical_json(obj):
    """Match Bahi's canonicalJson: keys sorted, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append_audit_entry(con, actor, action, ref, payload_dict, origin):
    """Append a new audit row consistent with the existing chain. Returns new hash."""
    last = con.execute(
        "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = last[0] if last else ""
    payload = canonical_json(payload_dict)
    h = sha256_hex(prev_hash + origin + payload)
    ts = "2026-05-05T10:00:00.000Z"  # frozen for reproducibility
    con.execute(
        "INSERT INTO audit_log (ts, actor, action, ref, origin, payload, prev_hash, hash, signature) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (ts, actor, action, ref, origin, payload, prev_hash, h),
    )
    return h


def main():
    if not SOURCE.exists():
        raise SystemExit(f"Source missing: {SOURCE}")

    # Read source archive
    with zipfile.ZipFile(SOURCE) as z_in:
        names = z_in.namelist()
        manifest = json.loads(z_in.read("manifest.json"))
        books_bytes = z_in.read("books.sqlite")
        # Pull every other file (snapshots, attachments, etc.) for verbatim copy
        extras = {n: z_in.read(n) for n in names if n not in {"manifest.json", "books.sqlite"}}

    # Mutate the SQLite
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tf.write(books_bytes)
    tf.close()
    con = sqlite3.connect(tf.name)
    try:
        # Append two AI-originated audit rows
        # The actor enum extension goes via khata-standard PR #22: owner|ca|system|ai
        origin = "https://bahi.naklitechie.com"
        h1 = append_audit_entry(
            con,
            actor="ai",
            action="entry.post",
            ref="entry:synthetic-ai-1",
            payload_dict={
                "entryId":    9990001,
                "voucherType": "purchase",
                "voucherRef":  "P-2026-AI-1",
                "postedAt":    "2026-05-05",
                "totalDr":     59000,
                "lineCount":   3,
            },
            origin=origin,
        )
        h2 = append_audit_entry(
            con,
            actor="ca",
            action="entry.post",
            ref="entry:synthetic-ai-2",
            payload_dict={
                # CA-mode AI-assisted: actor='ca' + aiAssisted=true preserves AI provenance
                # while keeping accountability on the human CA. Per khata-standard PR #22.
                "entryId":     9990002,
                "voucherType": "purchase",
                "voucherRef":  "P-2026-AI-2",
                "postedAt":    "2026-05-05",
                "totalDr":     17700,
                "lineCount":   2,
                "aiAssisted":  True,
            },
            origin=origin,
        )
        con.commit()
    finally:
        con.close()

    # Read mutated bytes
    with open(tf.name, "rb") as f:
        new_books = f.read()
    Path(tf.name).unlink(missing_ok=True)

    # Update manifest.integrity.auditHead + booksHash
    new_books_hash = hashlib.sha256(new_books).hexdigest()
    if "integrity" not in manifest:
        manifest["integrity"] = {}
    manifest["integrity"]["auditHead"] = h2
    manifest["integrity"]["booksHash"] = new_books_hash

    # Write the new archive (verbatim copy of extras + mutated books + updated manifest)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z_out:
        z_out.writestr("manifest.json", json.dumps(manifest, indent=2))
        z_out.writestr("books.sqlite", new_books)
        for name, data in extras.items():
            z_out.writestr(name, data)

    # Sanity report
    with sqlite3.connect(":memory:") as con2:
        con2.executescript("ATTACH ':memory:' AS x;")
    print(f"OK  wrote {OUT.name}")
    print(f"    audit head: {h2}")
    print(f"    books hash: {new_books_hash}")
    print(f"    appended:   actor='ai' row (owner-mode AI), then actor='ca' + aiAssisted=true row (CA-mode AI-assist)")


if __name__ == "__main__":
    main()
