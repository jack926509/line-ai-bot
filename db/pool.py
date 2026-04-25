"""連線池與 transaction context manager"""
import os
import logging
from contextlib import contextmanager

from psycopg2 import pool

logger = logging.getLogger("lumio.db")

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 5, DATABASE_URL)
    return _pool


@contextmanager
def get_db():
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)
