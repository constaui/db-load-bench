import csv
import mysql.connector
from mysql.connector import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError


class MySQLDatabase(BaseDatabase):

    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                **self.config,
                allow_local_infile=True,
            )
            cursor = self.connection.cursor()
            cursor.execute("SET GLOBAL local_infile = 1")
            cursor.close()
        except Error as e:
            raise DatabaseConnectionError(f"MySQL connection failed: {e}") from e

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def _quote(self, name: str) -> str:
        clean = name.strip().strip("`").replace("`", "``")
        return f"`{clean}`"

    def prepare(self, cursor, csv_file: str, table_name: str):
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            columns = list(csv.DictReader(f).fieldnames)
        if not columns:
            raise ValueError(f"CSV файл '{csv_file}' не содержит заголовков")
        column_defs = ", ".join(f"{self._quote(col)} TEXT" for col in columns)
        cursor.execute(f"DROP TABLE IF EXISTS {self._quote(table_name)}")
        cursor.execute(f"CREATE TABLE {self._quote(table_name)} ({column_defs})")
