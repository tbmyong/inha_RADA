"""Deactivate one or more pc_info rows.

Examples:
  python tools/revoke_pc.py PC-07
  python tools/revoke_pc.py --all-inactive-since 30d
  python tools/revoke_pc.py PC-07 --dry-run

The tool never deletes rows — it only flips ``is_active`` to FALSE so the
Spring authentication filter rejects subsequent metric posts while
preserving historical audit data.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _provisioning_common import db_config_from_args, execute, query  # noqa: E402


_DURATION_RE = re.compile(r"^(\d+)([dhm])$")


def parse_duration(text: str) -> str:
    """Return a Postgres INTERVAL literal from a short suffix string."""
    m = _DURATION_RE.match(text)
    if not m:
        raise SystemExit(
            "--all-inactive-since expects e.g. 30d, 12h, 45m"
        )
    amount, unit = m.groups()
    unit_word = {"d": "days", "h": "hours", "m": "minutes"}[unit]
    return f"{amount} {unit_word}"


def revoke_one(cfg, pc_id: str, dry_run: bool) -> int:
    if dry_run:
        rows = query(
            cfg,
            "SELECT pc_id, is_active FROM pc_info WHERE pc_id = %s",
            (pc_id,),
        )
        if not rows:
            print(f"[dry-run] {pc_id}: not found")
            return 0
        print(f"[dry-run] would deactivate {pc_id} (was is_active={rows[0][1]})")
        return 1
    affected = execute(
        cfg,
        [
            (
                "UPDATE pc_info SET is_active = FALSE WHERE pc_id = %s",
                (pc_id,),
            )
        ],
    )
    print(f"deactivated {pc_id} (rows affected: {affected})")
    return affected


def revoke_stale(cfg, interval: str, dry_run: bool) -> int:
    """Deactivate PCs whose most recent metric is older than the interval.

    We use ``metric_data.timestamp`` (the canonical client-supplied time)
    rather than registered_at so freshly provisioned but never-used PCs
    are *not* swept by accident — they simply have no metric_data rows
    and therefore fall outside this query.
    """
    select_sql = (
        "SELECT p.pc_id, MAX(m.timestamp) AS last_seen "
        "FROM pc_info p LEFT JOIN metric_data m ON m.pc_id = p.pc_id "
        "WHERE p.is_active = TRUE "
        "GROUP BY p.pc_id "
        f"HAVING MAX(m.timestamp) IS NOT NULL AND MAX(m.timestamp) < NOW() - INTERVAL '{interval}'"
    )
    candidates = query(cfg, select_sql)
    if not candidates:
        print("no PCs stale enough to revoke")
        return 0
    pc_ids = [row[0] for row in candidates]
    print(f"found {len(pc_ids)} stale PC(s):")
    for row in candidates:
        print(f"  {row[0]} (last seen: {row[1]})")
    if dry_run:
        print("[dry-run] no rows updated")
        return 0
    placeholders = ",".join(["%s"] * len(pc_ids))
    affected = execute(
        cfg,
        [
            (
                f"UPDATE pc_info SET is_active = FALSE WHERE pc_id IN ({placeholders})",
                pc_ids,
            )
        ],
    )
    print(f"deactivated {len(pc_ids)} PC(s)")
    return affected


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="revoke_pc.py",
        description="Deactivate pc_info rows by id or by inactivity window.",
    )
    p.add_argument("pc_id", nargs="?", help="Single PC id to deactivate.")
    p.add_argument(
        "--all-inactive-since",
        help="Deactivate PCs with no metric_data within this window (e.g. 30d).",
    )
    p.add_argument("--db-url", help="Direct postgres URL.")
    p.add_argument("--from-compose", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.pc_id and not args.all_inactive_since:
        raise SystemExit("pass a PC id or --all-inactive-since <duration>")
    if args.pc_id and args.all_inactive_since:
        raise SystemExit("pass either a PC id or --all-inactive-since, not both")
    cfg = db_config_from_args(args)
    if args.pc_id:
        revoke_one(cfg, args.pc_id, args.dry_run)
    else:
        interval = parse_duration(args.all_inactive_since)
        revoke_stale(cfg, interval, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
