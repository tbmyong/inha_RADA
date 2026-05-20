"""Shared helpers for PC provisioning toolkit.

Keeps the SHA-256(pepper + ":" + raw) hashing contract identical to
server-spring/.../security/ApiKeyHasher.java so that newly inserted
pc_info rows authenticate via the existing Spring filter.

Database access is intentionally minimal: we prefer psycopg if installed,
otherwise fall back to shelling out to ``docker compose exec postgres
psql`` so the toolkit works on hosts that only have the dev compose
stack (the scenario flagged in the brief — no psycopg in requirements).
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence


HASH_HEX_LENGTH = 64


def hash_api_key(pepper: str, raw_key: str) -> str:
    """Return lowercase hex SHA-256 of ``pepper + ":" + raw_key``.

    Matches ApiKeyHasher.java byte-for-byte (UTF-8, colon separator).
    """
    if raw_key is None:
        raise ValueError("raw_key must not be None")
    pepper = pepper or ""
    md = hashlib.sha256()
    md.update(pepper.encode("utf-8"))
    md.update(b":")
    md.update(raw_key.encode("utf-8"))
    return md.hexdigest()


def resolve_pepper(args) -> str:
    """Pull pepper from CLI override or API_KEY_PEPPER env."""
    if getattr(args, "pepper", None):
        return args.pepper
    pepper = os.environ.get("API_KEY_PEPPER", "")
    if not pepper:
        print(
            "WARNING: API_KEY_PEPPER is empty; hashes will be unsalted. "
            "This must match the Spring server pepper to authenticate.",
            file=sys.stderr,
        )
    return pepper


# ---------------------------------------------------------------------------
# DB layer — psycopg first, docker compose psql fallback.
# ---------------------------------------------------------------------------


@dataclass
class DbConfig:
    """Either a direct connection URL or compose-exec marker."""

    db_url: str | None = None
    via_compose: bool = False
    compose_service: str = "postgres"
    compose_user: str = "rada"
    compose_db: str = "pc_monitor"


def db_config_from_args(args) -> DbConfig:
    if getattr(args, "from_compose", False):
        return DbConfig(
            via_compose=True,
            compose_user=os.environ.get("POSTGRES_USER", "rada"),
            compose_db=os.environ.get("POSTGRES_DB", "pc_monitor"),
        )
    url = getattr(args, "db_url", None) or os.environ.get("DATABASE_URL")
    if not url:
        # Default to compose if nothing else is given — most common case in dev.
        return DbConfig(
            via_compose=True,
            compose_user=os.environ.get("POSTGRES_USER", "rada"),
            compose_db=os.environ.get("POSTGRES_DB", "pc_monitor"),
        )
    return DbConfig(db_url=url)


def _try_import_psycopg():
    try:  # psycopg 3
        import psycopg  # type: ignore

        return ("psycopg3", psycopg)
    except ImportError:
        pass
    try:  # psycopg2
        import psycopg2  # type: ignore
        import psycopg2.extras  # noqa: F401

        return ("psycopg2", psycopg2)
    except ImportError:
        return (None, None)


def _exec_compose_psql(cfg: DbConfig, sql: str, *, expect_rows: bool = False):
    """Run a single SQL statement through docker compose exec postgres psql.

    Returns parsed rows (list of dicts) when expect_rows is True,
    otherwise the number of affected rows reported by psql (best-effort).
    """
    if shutil.which("docker") is None:
        raise RuntimeError("docker CLI not found; install psycopg or pass --db-url")
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        cfg.compose_service,
        "psql",
        "-U",
        cfg.compose_user,
        "-d",
        cfg.compose_db,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",  # unaligned, tuples-only
        "-F",
        "\x1f",  # ASCII unit separator as column delimiter
        "-c",
        sql,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"psql failed (rc={proc.returncode}):\nstderr: {proc.stderr.strip()}\n"
            f"stdout: {proc.stdout.strip()}"
        )
    if not expect_rows:
        return proc.stdout.strip()
    rows = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        rows.append(line.split("\x1f"))
    return rows


def execute(cfg: DbConfig, statements: Sequence[tuple[str, Sequence]]):
    """Run a batch of parametrised SQL statements in one transaction.

    Each item is ``(sql_with_%s_placeholders, params_tuple)``.

    The psycopg path keeps the transaction open and commits at the end.
    The compose-psql fallback bakes parameters into a single multi-statement
    script wrapped in BEGIN/COMMIT — values are escaped via dollar-quoting.
    Numeric/bool literals must be passed pre-formatted (we only quote text).
    """
    kind, mod = _try_import_psycopg()
    if kind is None:
        return _execute_via_compose(cfg, statements)
    return _execute_via_psycopg(cfg, statements, kind, mod)


def _execute_via_psycopg(cfg, statements, kind, mod):
    affected = 0
    if cfg.via_compose:
        # psycopg installed but caller asked for compose — honor compose by
        # connecting to localhost:5432 (the compose port mapping).
        conn_str = (
            f"host=127.0.0.1 port=5432 dbname={cfg.compose_db} "
            f"user={cfg.compose_user} password={os.environ.get('POSTGRES_PASSWORD','rada_dev_pw')}"
        )
    else:
        conn_str = cfg.db_url
    if kind == "psycopg3":
        with mod.connect(conn_str) as conn:
            with conn.cursor() as cur:
                for sql, params in statements:
                    cur.execute(sql, params)
                    affected += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.commit()
    else:
        conn = mod.connect(conn_str)
        try:
            with conn.cursor() as cur:
                for sql, params in statements:
                    cur.execute(sql, params)
                    affected += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.commit()
        finally:
            conn.close()
    return affected


def _pg_quote(val) -> str:
    """Quote a Python value as a Postgres literal for inline SQL."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return f"'{s}'"


def _execute_via_compose(cfg, statements):
    # Render parameters inline (safely quoted) and concatenate into one
    # transaction script.
    rendered = ["BEGIN;"]
    for sql, params in statements:
        out = []
        param_iter = iter(params)
        # Replace each %s with the next quoted literal.
        i = 0
        while i < len(sql):
            if sql[i : i + 2] == "%s":
                out.append(_pg_quote(next(param_iter)))
                i += 2
            else:
                out.append(sql[i])
                i += 1
        rendered.append("".join(out) + ";")
    rendered.append("COMMIT;")
    script = "\n".join(rendered)
    _exec_compose_psql(cfg, script)
    # psql doesn't expose rowcount per-statement easily; the caller asked
    # for the count so we return the number of non-control statements as a
    # proxy (every input statement is expected to affect 1 row).
    return len(statements)


def query(cfg: DbConfig, sql: str, params: Sequence = ()) -> list[list[str]]:
    """Run a SELECT and return rows as list-of-string-lists (psql semantics)."""
    kind, mod = _try_import_psycopg()
    if kind is None:
        # Inline params for compose path.
        out = []
        param_iter = iter(params)
        i = 0
        while i < len(sql):
            if sql[i : i + 2] == "%s":
                out.append(_pg_quote(next(param_iter)))
                i += 2
            else:
                out.append(sql[i])
                i += 1
        return _exec_compose_psql(cfg, "".join(out), expect_rows=True)
    if cfg.via_compose:
        conn_str = (
            f"host=127.0.0.1 port=5432 dbname={cfg.compose_db} "
            f"user={cfg.compose_user} password={os.environ.get('POSTGRES_PASSWORD','rada_dev_pw')}"
        )
    else:
        conn_str = cfg.db_url
    if kind == "psycopg3":
        with mod.connect(conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [[str(c) for c in row] for row in rows]
    else:
        conn = mod.connect(conn_str)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [[str(c) for c in row] for row in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Filesystem helpers — best-effort 0600 on the output CSV.
# ---------------------------------------------------------------------------


def secure_chmod(path: str) -> str:
    """Tighten permissions on a freshly-written sensitive file.

    On POSIX: chmod 600.
    On Windows: use icacls to grant only the current user Read/Write.

    Returns a short human-readable status string.
    """
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
            return "chmod 600"
        except OSError as e:
            return f"chmod failed: {e}"
    # Windows
    try:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        if not user:
            return "icacls skipped (no USERNAME)"
        if shutil.which("icacls") is None:
            return "icacls not available"
        # /inheritance:r removes inherited ACEs; then grant only current user.
        subprocess.run(
            ["icacls", path, "/inheritance:r"],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["icacls", path, "/grant:r", f"{user}:(R,W)"],
            capture_output=True,
            check=False,
        )
        return f"icacls restricted to {user}"
    except Exception as e:  # pragma: no cover — best effort
        return f"ACL hardening failed: {e}"
