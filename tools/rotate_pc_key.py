"""Rotate the API key of a single PC.

Usage:
    python tools/rotate_pc_key.py PC-07 --output PC-07.key

The previous raw key is invalidated immediately upon DB update. The new
raw key is written to ``--output`` as a single line (the operator then
re-deploys that one line to the affected client config).
"""

from __future__ import annotations

import argparse
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provisioning_common import (  # noqa: E402
    db_config_from_args,
    execute,
    hash_api_key,
    query,
    resolve_pepper,
    secure_chmod,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rotate_pc_key.py",
        description="Rotate the api_key of a single pc_info row.",
    )
    p.add_argument("pc_id", help="PC id to rotate.")
    p.add_argument("--output", required=True, help="Write new raw key here.")
    p.add_argument("--pepper", help="Override API_KEY_PEPPER.")
    p.add_argument("--db-url")
    p.add_argument("--from-compose", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pepper = resolve_pepper(args)
    cfg = db_config_from_args(args)

    existing = query(
        cfg, "SELECT pc_id, is_active FROM pc_info WHERE pc_id = %s", (args.pc_id,)
    )
    if not existing:
        raise SystemExit(f"{args.pc_id}: no such pc_info row")

    new_raw = secrets.token_urlsafe(24)
    new_hash = hash_api_key(pepper, new_raw)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_raw + "\n", encoding="utf-8")
    chmod_status = secure_chmod(str(out_path))

    if args.dry_run:
        print(f"[dry-run] new key written to {out_path} ({chmod_status})")
        print(f"[dry-run] would set pc_info.api_key for {args.pc_id} to a new hash")
        return 0

    execute(
        cfg,
        [
            (
                "UPDATE pc_info SET api_key = %s, registered_at = %s WHERE pc_id = %s",
                (new_hash, datetime.now(timezone.utc).isoformat(sep=" "), args.pc_id),
            )
        ],
    )
    print(f"rotated {args.pc_id}: new raw key at {out_path} ({chmod_status})")
    print("Previous raw key is invalidated. Re-deploy this file to the PC and DELETE locally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
