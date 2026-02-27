import psycopg2
import csv
from psycopg2 import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError
from psycopg2.extras import execute_values


class PgSQLDatabase(BaseDatabase):

    def connect(self):
        try:
            self.connection = psycopg2.connect(**self.config)
        except Error as e:
            raise DatabaseConnectionError(f"PostgreSQL connection failed: {e}") from e

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def _quote(self, name: str) -> str:
        """Экранирует идентификатор для PostgreSQL двойными кавычками."""
        clean = name.strip().strip('"')
        clean = clean.replace('"', '""')  # внутренние кавычки удваиваем
        return f'"{clean}"'

    def prepare(self, cursor, csv_file: str, table_name: str):
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            columns = list(csv.DictReader(f).fieldnames)

        if not columns:
            raise ValueError(f"CSV файл '{csv_file}' не содержит заголовков")

        column_defs = ", ".join(f"{self._quote(col)} TEXT" for col in columns)
        table = self._quote(table_name)

        cursor.execute(f"DROP TABLE IF EXISTS {table}")
        cursor.execute(f"CREATE TABLE {table} ({column_defs})")

    def default_insert(self, csv_file: str, table_name: str) -> int:
        cursor = None
        try:
            cursor = self.connection.cursor()
            insert_count = 0

            with open(csv_file, "r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    col_names = ", ".join(self._quote(col) for col in row.keys())
                    placeholders = ", ".join(["%s"] * len(row))
                    cursor.execute(
                        f"INSERT INTO {self._quote(table_name)} ({col_names}) VALUES ({placeholders})",
                        list(row.values()),
                    )
                    insert_count += 1

            self.connection.commit()
            return insert_count

        except Exception as e:
            self.connection.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()

    def bulk_insert(
        self, csv_file: str, table_name: str, batch_size: int = 1000
    ) -> int:
        cursor = None
        try:
            cursor = self.connection.cursor()
            insert_count = 0

            with open(csv_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames

                col_names = ", ".join(self._quote(col) for col in columns)
                sql = f"INSERT INTO {self._quote(table_name)} ({col_names}) VALUES %s"

                batch = []
                for row in reader:
                    batch.append(list(row.values()))

                    if len(batch) >= batch_size:
                        execute_values(cursor, sql, batch, page_size=batch_size)
                        insert_count += len(batch)
                        batch.clear()

                if batch:
                    execute_values(cursor, sql, batch, page_size=batch_size)
                    insert_count += len(batch)

            self.connection.commit()
            return insert_count

        except Exception as e:
            self.connection.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()

    def file_insert(self, csv_file: str, table_name: str) -> int:
        """
        Использует COPY FROM STDIN — самый быстрый способ загрузки в PostgreSQL.
        Файл читается на стороне клиента и стримится в БД, SQL-парсинг не задействован.
        """
        cursor = None
        try:
            cursor = self.connection.cursor()

            # Считаем строки заранее — COPY не возвращает rowcount надёжно
            with open(csv_file, "r", newline="", encoding="utf-8") as f:
                row_count = sum(1 for _ in csv.DictReader(f))

            with open(csv_file, "r", newline="", encoding="utf-8") as f:
                cursor.copy_expert(
                    f"COPY {self._quote(table_name)} FROM STDIN WITH (FORMAT csv, HEADER true)",
                    f,
                )

            self.connection.commit()
            return row_count

        except Exception as e:
            self.connection.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()
