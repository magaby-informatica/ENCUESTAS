import psycopg2
import psycopg2.extras
from psycopg2 import pool
import os

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://neondb_owner:npg_9J6hYMfwLdrI@ep-proud-wind-atb91ral-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
)

_pool = pool.ThreadedConnectionPool(minconn=2, maxconn=20, dsn=DATABASE_URL)


class UpperDictCursor(psycopg2.extras.RealDictCursor):
    """Cursor que devuelve filas como dicts con claves en MAYÚSCULAS,
    igual que PyMySQL DictCursor, para no tener que cambiar nada en app.py."""

    def fetchone(self):
        row = super().fetchone()
        if row is None:
            return None
        return {k.upper(): v for k, v in row.items()}

    def fetchall(self):
        rows = super().fetchall()
        return [{k.upper(): v for k, v in r.items()} for r in rows]


class DictConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor(cursor_factory=UpperDictCursor)

    def commit(self):
        self._conn.commit()

    def close(self):
        _pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_connection():
    conn = _pool.getconn()
    conn.autocommit = False
    return DictConnection(conn)
