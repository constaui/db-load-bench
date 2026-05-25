import csv
import psycopg2
from psycopg2 import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError


def _decode_libpq_bytes(raw: bytes) -> str:
    """Декодирует «сырые» байты от libpq, перебирая вероятные кодировки.

    Опция `-c lc_messages=C` применяется сервером ПОСЛЕ авторизации, поэтому
    ошибки, возникшие на этапе подключения (неверный пароль, отсутствующая
    база, неверный хост), возвращаются в локали сервера — обычно cp1251 на
    русской Windows. psycopg2 декодирует их как UTF-8 и падает.
    """
    for enc in ("utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


class PgSQLDatabase(BaseDatabase):

    def connect(self):
        try:
            # На Windows с русской локалью libpq возвращает сообщения об ошибках
            # в cp1251, а psycopg2 декодирует их как UTF-8 → UnicodeDecodeError
            # ("0xc2 invalid continuation byte"). Принудительно требуем у сервера
            # ASCII-сообщения и UTF-8 как клиентскую кодировку данных.
            cfg = dict(self.config)
            existing = (cfg.pop("options", "") or "").strip()
            cfg["options"] = (existing + " -c lc_messages=C").strip()
            cfg.setdefault("client_encoding", "UTF8")
            self.connection = psycopg2.connect(**cfg)
        except UnicodeDecodeError as e:
            # libpq вернул сообщение в не-UTF8 кодировке. Декодируем сами и
            # пробрасываем понятное сообщение наверх — без этого приложение
            # упало бы с непойманным UnicodeDecodeError.
            raw = e.object if isinstance(e.object, (bytes, bytearray)) else b""
            msg = (
                _decode_libpq_bytes(bytes(raw)).strip()
                if raw
                else "(не удалось извлечь сообщение)"
            )
            raise DatabaseConnectionError(
                f"PostgreSQL connection failed: {msg}"
            ) from e
        except Error as e:
            raise DatabaseConnectionError(f"PostgreSQL connection failed: {e}") from e

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def _quote(self, name: str) -> str:
        clean = name.strip().strip('"').replace('"', '""')
        return f'"{clean}"'

    def prepare(self, cursor, csv_file: str, table_name: str):
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            columns = list(csv.DictReader(f).fieldnames)
        if not columns:
            raise ValueError(f"CSV файл '{csv_file}' не содержит заголовков")

        column_defs = ", ".join(f"{self._quote(col)} TEXT" for col in columns)

        cursor.execute(f"DROP TABLE IF EXISTS {self._quote(table_name)}")
        cursor.execute(f"CREATE TABLE {self._quote(table_name)} ({column_defs})")
