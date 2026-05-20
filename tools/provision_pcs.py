"""Bulk-provision pc_info rows for the RADA lab deployment.

Two modes:

  Mode A  --count N  --prefix PC  --output keys.csv
      Auto-generates ``N`` strong API keys (``secrets.token_urlsafe(24)``)
      against PC IDs ``PC-01, PC-02, ...`` (zero-padded to the width of N).

  Mode B  --input pcs.csv  --output keys.csv
      Reads ``pc_id,hostname`` from the input CSV and assigns a fresh API
      key to each row.

Common behaviour:

* Hashes every key with the same SHA-256(pepper + ':' + raw) used by
  ``ApiKeyHasher.java`` so the inserted rows authenticate without a server
  restart.
* Upserts pc_info via ``ON CONFLICT (pc_id) DO UPDATE`` so re-running the
  tool with the same PC IDs rotates their keys instead of erroring on the
  primary-key collision (operator is prompted unless ``--yes`` is passed).
* Writes a sensitive output CSV (``pc_id, raw_key, hashed_key,
  registered_at``) and tightens permissions to owner-only.
* ``--dry-run`` skips the DB and only writes the CSV.

The tool only uses the Python standard library (it never imports psycopg
unless that module is already installed) — when the host has no driver it
shells out to ``docker compose exec postgres psql``.
"""

from __future__ import annotations

import argparse
import csv
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Allow running as ``python tools/provision_pcs.py`` without packaging.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provisioning_common import (  # noqa: E402
    DbConfig,
    db_config_from_args,
    execute,
    hash_api_key,
    resolve_pepper,
    secure_chmod,
)


def _pad_width(count: int) -> int:
    # zero-pad so 9 -> "01"..."09", 40 -> "01"..."40", 100 -> "001".
    return max(2, len(str(count)))


def generate_rows_auto(count: int, prefix: str) -> list[dict]:
    width = _pad_width(count)
    rows = []
    for i in range(1, count + 1):
        pc_id = f"{prefix}-{str(i).zfill(width)}"
        rows.append(
            {
                "pc_id": pc_id,
                "hostname": pc_id,
                "raw_key": secrets.token_urlsafe(24),
            }
        )
    return rows


def read_rows_csv(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "pc_id" not in reader.fieldnames:
            raise SystemExit(f"input CSV {path} must have a pc_id column")
        for raw in reader:
            pc_id = (raw.get("pc_id") or "").strip()
            if not pc_id:
                continue
            rows.append(
                {
                    "pc_id": pc_id,
                    "hostname": (raw.get("hostname") or pc_id).strip(),
                    "raw_key": secrets.token_urlsafe(24),
                }
            )
    if not rows:
        raise SystemExit(f"input CSV {path} produced 0 rows")
    return rows


UPSERT_SQL = (
    "INSERT INTO pc_info (pc_id, hostname, api_key, is_active, registered_at) "
    "VALUES (%s, %s, %s, %s, %s) "
    "ON CONFLICT (pc_id) DO UPDATE SET "
    "  hostname = EXCLUDED.hostname, "
    "  api_key = EXCLUDED.api_key, "
    "  is_active = EXCLUDED.is_active, "
    "  registered_at = EXCLUDED.registered_at"
)


def upsert_rows(cfg: DbConfig, rows: list[dict], pepper: str, now: datetime) -> int:
    statements = []
    for r in rows:
        statements.append(
            (
                UPSERT_SQL,
                (
                    r["pc_id"],
                    r["hostname"],
                    r["hashed_key"],
                    True,
                    now.isoformat(sep=" "),
                ),
            )
        )
    return execute(cfg, statements)


def write_output_csv(path: str, rows: list[dict]) -> None:
    parent = Path(path).resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["pc_id", "raw_key", "hashed_key", "registered_at"])
        for r in rows:
            writer.writerow(
                [r["pc_id"], r["raw_key"], r["hashed_key"], r["registered_at"]]
            )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="provision_pcs.py",
        description="Bulk-provision pc_info rows with strong API keys.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--count", type=int, help="Auto-generate this many PCs.")
    src.add_argument("--input", help="Read pc_id,hostname from this CSV.")
    p.add_argument(
        "--prefix",
        default="PC",
        help="PC ID prefix when --count is used (default: PC).",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Write raw keys to this CSV (treat as a secret).",
    )
    p.add_argument(
        "--pepper",
        help="Override API_KEY_PEPPER (otherwise read from env).",
    )
    p.add_argument(
        "--db-url",
        help="Direct postgres URL, e.g. postgresql://user:pw@host:5432/db",
    )
    p.add_argument(
        "--from-compose",
        action="store_true",
        help="Use docker compose exec postgres psql instead of a direct URL.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute hashes and write CSV, but do not touch the database.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm overwrite of existing pc_id rows.",
    )
    return p


def confirm_overwrite(cfg: DbConfig, rows: list[dict], auto_yes: bool) -> None:
    from _provisioning_common import query

    pc_ids = [r["pc_id"] for r in rows]
    # Build an ANY array literal for portability across the two drivers.
    placeholders = ",".join(["%s"] * len(pc_ids))
    sql = f"SELECT pc_id FROM pc_info WHERE pc_id IN ({placeholders})"
    try:
        existing = query(cfg, sql, pc_ids)
    except Exception as e:
        print(
            f"WARNING: could not pre-check existing pc_ids ({e}); "
            "proceeding — ON CONFLICT will still handle collisions.",
            file=sys.stderr,
        )
        return
    found = {row[0] for row in existing}
    if not found:
        return
    print(
        f"NOTE: {len(found)} existing pc_id row(s) will be UPDATED "
        f"(api_key rotated): {sorted(found)}"
    )
    if auto_yes:
        return
    if not sys.stdin.isatty():
        print(
            "Refusing to overwrite without --yes when stdin is not a TTY.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    reply = input("Proceed? [y/N] ").strip().lower()
    if reply not in {"y", "yes"}:
        raise SystemExit("aborted by operator")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    pepper = resolve_pepper(args)
    now = datetime.now(timezone.utc).astimezone()

    if args.count is not None:
        if args.count <= 0:
            raise SystemExit("--count must be > 0")
        rows = generate_rows_auto(args.count, args.prefix)
    else:
        rows = read_rows_csv(args.input)

    for r in rows:
        r["hashed_key"] = hash_api_key(pepper, r["raw_key"])
        r["registered_at"] = now.isoformat(sep=" ", timespec="seconds")

    # Check for raw-key collisions inside the batch (UNIQUE on api_key).
    seen_hashes = set()
    for r in rows:
        if r["hashed_key"] in seen_hashes:
            raise SystemExit(
                f"Internal hash collision for {r['pc_id']} — regenerate or report a bug."
            )
        seen_hashes.add(r["hashed_key"])

    write_output_csv(args.output, rows)
    chmod_status = secure_chmod(args.output)

    if args.dry_run:
        print(f"[dry-run] Wrote {len(rows)} rows to {args.output} ({chmod_status})")
        print("[dry-run] No database changes were made.")
        return 0

    cfg = db_config_from_args(args)
    confirm_overwrite(cfg, rows, args.yes)
    affected = upsert_rows(cfg, rows, pepper, now)

    print(f"Provisioned {len(rows)} PCs.")
    print(f"Output: {args.output} ({chmod_status})")
    print(f"DB updated: pc_info rows inserted/updated = {affected}")
    print(
        "WARNING: the output CSV contains raw API keys. Distribute securely "
        "and DELETE after."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
