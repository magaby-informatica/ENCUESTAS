import psycopg2
import psycopg2.extras
from psycopg2 import pool, OperationalError
import os

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://neondb_owner:npg_9J6hYMfwLdrI@ep-proud-wind-atb91ral-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
)

_pool = None

def get_pool():
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DATABASE_URL)
    return _pool


class CaseInsensitiveDict(dict):
    def __getitem__(self, key):
        try:
            return super().__getitem__(key.upper())
        except KeyError:
            return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        return super().__contains__(key.upper()) or super().__contains__(key)


class SmartDictCursor(psycopg2.extras.RealDictCursor):
    def fetchone(self):
        row = super().fetchone()
        if row is None:
            return None
        return CaseInsensitiveDict({k.upper(): v for k, v in row.items()})

    def fetchall(self):
        rows = super().fetchall()
        return [CaseInsensitiveDict({k.upper(): v for k, v in r.items()}) for r in rows]


class DictConnection:
    def __init__(self):
        self._conn = None
        self._connect()

    def _connect(self):
        """Obtiene una conexiÃ³n del pool, reconectando si es necesario."""
        try:
            conn = get_pool().getconn()
            # Verificar que la conexiÃ³n estÃ¡ viva
            conn.cursor().execute("SELECT 1")
            conn.autocommit = False
            self._conn = conn
        except (OperationalError, Exception):
            # Si la conexiÃ³n estÃ¡ muerta, crear una nueva directamente
            self._conn = psycopg2.connect(dsn=DATABASE_URL)
            self._conn.autocommit = False

    def cursor(self):
        return self._conn.cursor(cursor_factory=SmartDictCursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()
    def close(self):
        try:
            get_pool().putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_connection():
    return DictConnection()
