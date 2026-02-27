import mysql.connector
from mysql.connector import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError
import csv


class MySQLDatabase(BaseDatabase):

    def connect(self):
        try:
            config = {
                **self.config,
                "allow_local_infile": True,
            }
            self.connection = mysql.connector.connect(**config)
            self._enable_local_infile()
        except Error as e:
            raise DatabaseConnectionError(f"MySQL connection failed: {e}") from e

    def _enable_local_infile(self):
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute("SET GLOBAL local_infile = 1")
        except Error as e:
            raise DatabaseConnectionError(
                f"Не удалось включить local_infile. "
                f"Проверьте права пользователя (требуется SUPER или SYSTEM_VARIABLES_ADMIN): {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def _quote(self, name: str) -> str:
        """Экранирует идентификатор для MySQL бэктиками."""
        clean = name.strip().strip("`")
        clean = clean.replace("`", "``")  # внутренние бэктики удваиваем
        return f"`{clean}`"

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
                placeholders = ", ".join(["%s"] * len(columns))
                sql = f"INSERT INTO {self._quote(table_name)} ({col_names}) VALUES ({placeholders})"

                batch = []
                for row in reader:
                    batch.append(list(row.values()))

                    if len(batch) >= batch_size:
                        cursor.executemany(sql, batch)
                        insert_count += len(batch)
                        batch.clear()

                # Остаток последнего батча
                if batch:
                    cursor.executemany(sql, batch)
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
        Использует LOAD DATA LOCAL INFILE — самый быстрый способ загрузки в MySQL.
        Файл передаётся напрямую в сервер, минуя построчный SQL.
        Требует allow_local_infile=True в конфиге подключения.
        """
        cursor = None
        try:
            cursor = self.connection.cursor()

            # Считаем строки заранее — LOAD DATA не возвращает точный rowcount
            with open(csv_file, "r", newline="", encoding="utf-8") as f:
                row_count = sum(1 for _ in csv.DictReader(f))

            table = self._quote(table_name)

            # Абсолютный путь обязателен для LOCAL INFILE
            abs_path = csv_file.replace("\\", "/")

            cursor.execute(
                f"""
                LOAD DATA LOCAL INFILE '{abs_path}'
                INTO TABLE {table}
                FIELDS TERMINATED BY ','
                OPTIONALLY ENCLOSED BY '"'
                LINES TERMINATED BY '\\n'
                IGNORE 1 ROWS
            """
            )

            self.connection.commit()
            return row_count

        except Exception as e:
            self.connection.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()
