"""Unit tests for the PC provisioning toolkit (DB-free).

Covers the hashing contract (must match ApiKeyHasher.java), auto-id
formatting, idempotency of the hash, output CSV layout, and the entropy
profile of generated keys (UNIQUE-constraint sanity).
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys
from pathlib import Path

import pytest

# Make tools/ importable without a packaging step.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from _provisioning_common import hash_api_key  # noqa: E402
from provision_pcs import (  # noqa: E402
    _pad_width,
    build_parser,
    generate_rows_auto,
    write_output_csv,
)


def test_hash_matches_java_contract():
    # ApiKeyHasherTest.matches_sql_digest_contract pre-computes
    # SHA-256("pep:rawkey") — we must reproduce it byte-for-byte.
    expected = hashlib.sha256(b"pep:rawkey").hexdigest()
    assert hash_api_key("pep", "rawkey") == expected
    assert len(hash_api_key("pep", "rawkey")) == 64
    assert hash_api_key("pep", "rawkey").islower()


def test_hash_is_deterministic_and_pepper_sensitive():
    h1 = hash_api_key("pepper-A", "key-1")
    h2 = hash_api_key("pepper-A", "key-1")
    h3 = hash_api_key("pepper-B", "key-1")
    h4 = hash_api_key("pepper-A", "key-2")
    assert h1 == h2
    assert h1 != h3
    assert h1 != h4


def test_pc_id_zero_padded_for_40():
    rows = generate_rows_auto(40, "PC")
    assert rows[0]["pc_id"] == "PC-01"
    assert rows[8]["pc_id"] == "PC-09"
    assert rows[9]["pc_id"] == "PC-10"
    assert rows[39]["pc_id"] == "PC-40"
    assert len({r["pc_id"] for r in rows}) == 40


def test_pc_id_width_scales_with_count():
    # 5 → 2 wide minimum (per _pad_width contract)
    assert _pad_width(5) == 2
    # 100 → 3 wide
    assert _pad_width(100) == 3
    rows = generate_rows_auto(100, "LAB")
    assert rows[0]["pc_id"] == "LAB-001"
    assert rows[99]["pc_id"] == "LAB-100"


def test_generated_keys_have_high_entropy_no_collisions():
    # secrets.token_urlsafe(24) → ~192 bits; 1000-row batch should never
    # produce duplicates. This guards against an accidental swap to a
    # weak generator that would later fail the UNIQUE(api_key) constraint.
    rows = generate_rows_auto(1000, "STRESS")
    keys = {r["raw_key"] for r in rows}
    assert len(keys) == 1000


def test_write_output_csv_shape(tmp_path):
    pepper = "test-pepper"
    rows = generate_rows_auto(3, "DEMO")
    for r in rows:
        r["hashed_key"] = hash_api_key(pepper, r["raw_key"])
        r["registered_at"] = "2026-05-20 12:00:00"
    out = tmp_path / "keys.csv"
    write_output_csv(str(out), rows)
    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)
    assert header == ["pc_id", "raw_key", "hashed_key", "registered_at"]
    assert len(body) == 3
    # Hash column must be 64 hex chars.
    for line in body:
        assert len(line[2]) == 64
        int(line[2], 16)  # raises if not hex


def test_cli_rejects_mutually_exclusive_modes():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--count", "5", "--input", "x.csv", "--output", "o.csv"])


def test_cli_requires_output():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--count", "5"])
