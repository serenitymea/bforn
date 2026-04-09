import os
import time
import logging
from typing import Any, Literal

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

_DSN = "postgresql://{user}:{password}@{host}:{port}/{db}".format(
    user=os.environ["PGUSER"],
    password=os.environ["PGPASSWORD"],
    host=os.environ["PGHOST"],
    port=os.getenv("PGPORT", "5432"),
    db=os.environ["PGDATABASE"],
)

_pool: ThreadedConnectionPool | None = None


def init_pool(retries: int = 10, delay: float = 3.0) -> None:
    """Creates a connection pool with retry logic call once at startup"""
    global _pool
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            candidate = ThreadedConnectionPool(1, 10, dsn=_DSN)
            conn = candidate.getconn()
            candidate.putconn(conn)
            _pool = candidate
            logger.info("DB pool created on attempt %d", attempt)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("DB attempt %d/%d failed: %s. Retry in %.0fs…", attempt, retries, exc, delay)
            time.sleep(delay)
    raise RuntimeError(f"Cannot connect to DB after {retries} attempts") from last_exc


def execute(
    sql: str,
    params: tuple = (),
    *,
    fetch: Literal["none", "one", "all"] = "none",
    write: bool = False,
) -> Any:
    """
    Executes SQL within a single pooled connection
    write=True - commit after execution
    fetch="one" - returns a single row as a dict or None
    fetch="all" - returns a list of dicts
    """
    assert _pool is not None, "call init_pool() before execute()"
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if write:
                conn.commit()
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def get_raw_conn():
    """Returns a connection for manual transaction management (e.g. SELECT … FOR UPDATE)"""
    assert _pool is not None
    return _pool.getconn()


def release_conn(conn) -> None:
    assert _pool is not None
    _pool.putconn(conn)