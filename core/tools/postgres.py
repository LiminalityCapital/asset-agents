"""Thin psycopg wrapper. Stateless from the caller's perspective:
one connection per call, explicit connect + statement timeouts, no retry.

Callers pass parameterized SQL — never build queries with string concat."""

import logging
import os
import time
from urllib.parse import urlparse

log = logging.getLogger(__name__)


def _safe_dsn_label(db_url: str) -> str:
    """host:port/db for logs. Never logs credentials."""
    try:
        u = urlparse(db_url)
        host = u.hostname or "?"
        port = u.port or 5432
        db = (u.path or "/").lstrip("/") or "?"
        return f"{host}:{port}/{db}"
    except Exception:
        return "<unparsable DSN>"


def query(
    sql: str,
    params: tuple = (),
    *,
    statement_timeout_ms: int = 10_000,
    connect_timeout_s: int = 10,
) -> list[tuple]:
    """Run a parameterized query against DATABASE_URL; return all rows."""
    import psycopg  # local import so the module imports without psycopg installed

    db_url = os.environ["DATABASE_URL"]
    dsn = _safe_dsn_label(db_url)
    log.info("pg: connecting to %s (connect_timeout=%ds)", dsn, connect_timeout_s)

    t0 = time.perf_counter()
    with psycopg.connect(
        db_url,
        connect_timeout=connect_timeout_s,
        options=f"-c statement_timeout={statement_timeout_ms}",
    ) as conn:
        log.info("pg: connected in %.0fms", (time.perf_counter() - t0) * 1000)
        with conn.cursor() as cur:
            q0 = time.perf_counter()
            cur.execute(sql, params)
            rows = cur.fetchall()
            log.info(
                "pg: fetched %d row(s) in %.0fms",
                len(rows),
                (time.perf_counter() - q0) * 1000,
            )
            return rows
