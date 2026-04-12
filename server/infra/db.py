import os
import logging
from contextlib import contextmanager
from typing import Any, Optional, TYPE_CHECKING
import psycopg

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool as ConnectionPoolType
else:
    ConnectionPoolType = Any

try:
    from psycopg_pool import ConnectionPool as PsycopgConnectionPool
except Exception:  # pragma: no cover - optional dependency at runtime
    PsycopgConnectionPool = None

DATABASE_URL = os.getenv("DATABASE_URL",
                          "postgresql://checker:114514@localhost:5432/postgres")
DB_CONNECT_TIMEOUT_SEC = int(os.getenv("DB_CONNECT_TIMEOUT_SEC", "8"))
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
DB_POOL_MAX_IDLE_SEC = int(os.getenv("DB_POOL_MAX_IDLE_SEC", "300"))

_DB_POOL: Optional[ConnectionPoolType] = None
_POOL_WARNING_LOGGED = False


def _create_pool() -> Optional[ConnectionPoolType]:
    global _POOL_WARNING_LOGGED
    if PsycopgConnectionPool is None:
        if not _POOL_WARNING_LOGGED:
            logging.warning("psycopg_pool not installed; fallback to one-connection-per-request mode")
            _POOL_WARNING_LOGGED = True
        return None

    min_size = max(1, DB_POOL_MIN_SIZE)
    max_size = max(min_size, DB_POOL_MAX_SIZE)
    pool = PsycopgConnectionPool(
        conninfo=DATABASE_URL,
        min_size=min_size,
        max_size=max_size,
        timeout=float(DB_CONNECT_TIMEOUT_SEC),
        max_idle=float(max(1, DB_POOL_MAX_IDLE_SEC)),
        kwargs={"connect_timeout": DB_CONNECT_TIMEOUT_SEC},
        open=True,
    )
    logging.info("db connection pool enabled: min=%s max=%s", min_size, max_size)
    return pool


def get_pool() -> Optional[ConnectionPoolType]:
    global _DB_POOL
    if _DB_POOL is None:
        _DB_POOL = _create_pool()
    return _DB_POOL


def close_pool() -> None:
    global _DB_POOL
    if _DB_POOL is not None:
        _DB_POOL.close()
        _DB_POOL = None


@contextmanager
def get_conn():
    pool = get_pool()
    if pool is not None:
        with pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return

    conn = psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT_SEC)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


