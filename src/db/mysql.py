import csv
import mysql.connector
from mysql.connector import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError


class MySQLDatabase(BaseDatabase):

    def connect(self):
        try:
            # На Windows с русской локалью mysql.connector может «жёстко»
            # упасть на декодировании серверных сообщений (cp1251) при
            # неудаче. Защитные меры:
            #   - use_pure=True — чисто-Python коннектор, без C-расширения,
            #     ошибки нормально становятся исключениями вместо abort;
            #   - charset=utf8mb4 — фиксированная кодировка соединения.
            cfg = dict(self.config)
            cfg.setdefault("charset", "utf8mb4")
            cfg.setdefault("use_pure", True)
            self.connection = mysql.connector.connect(
                **cfg,
                allow_local_infile=True,
            )
            # `SET GLOBAL local_infile = 1` требует привилегию SUPER /
            # SYSTEM_VARIABLES_ADMIN. Если её нет — сервер отвечает ошибкой,
            # и от неё не должно «закрываться приложение». Поэтому в try.
            # Если local_infile уже включён в my.cnf — file_insert всё равно
            # будет работать.
            try:
                cursor = self.connection.cursor()
                cursor.execute("SET GLOBAL local_infile = 1")
                cursor.close()
            except Error:
                # Молча игнорируем: file_insert либо уже разрешён сервером,
                # либо упадёт позже с понятной ошибкой.
                pass
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
