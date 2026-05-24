import csv
import psycopg2
from psycopg2 import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError


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
