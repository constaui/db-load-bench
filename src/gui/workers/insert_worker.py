import time
from PyQt6.QtCore import QThread, pyqtSignal

from src.db import MySQLDatabase, PgSQLDatabase
from src.db.exceptions import DatabaseConnectionError

DB_CLASSES = {
    "MySQL": MySQLDatabase,
    "PostgreSQL": PgSQLDatabase,
}


class InsertWorker(QThread):
    """Воркер для загрузки данных в БД"""

    log_message = pyqtSignal(str, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self):
        db = None

        try:
            db_class = DB_CLASSES.get(self.config["db_type"])
            if db_class is None:
                self.error.emit(f"Неизвестная СУБД: {self.config['db_type']}")
                return
            db = db_class(self.config["conn_params"])

            self.log_message.emit(f"Подключение к {self.config['db_type']}...", "INFO")
            db.connect()
            self.log_message.emit("Подключение успешно", "SUCCESS")

            csv_file = self.config["csv_file"]
            table = "Test"
            method = self.config["method"]
            insert_fn = getattr(db, method)

            self.log_message.emit("Подготовка таблицы...", "INFO")
            cursor = db.connection.cursor()
            db.prepare(cursor, csv_file, table)
            db.connection.commit()
            cursor.close()
            self.log_message.emit("Таблица готова", "SUCCESS")

            self.log_message.emit(f"Запуск {method}...", "INFO")

            cursor = db.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()

            start = time.perf_counter()

            if method == "bulk_insert":
                rows = insert_fn(csv_file, table, self.config["batch_size"])
            else:
                rows = insert_fn(csv_file, table)

            elapsed = time.perf_counter() - start

            self.log_message.emit(
                f"Вставлено {rows} строк за {elapsed:.2f}с", "SUCCESS"
            )
            self.finished.emit(
                {
                    "engine": self.config["engine"],
                    "db_type": self.config["db_type"],
                    "method": method,
                    "experiment_config": {"rows": rows},
                    "method_config": {
                        "batch_size": (
                            self.config.get("batch_size")
                            if method == "bulk_insert"
                            else None
                        ),
                    },
                    "metrics": {
                        "elapsed": elapsed,
                        "rps": round(rows / elapsed, 1) if elapsed > 0 else 0,
                    },
                }
            )

        except DatabaseConnectionError as e:
            self.log_message.emit(str(e), "ERROR")
            self.error.emit(str(e))
        except Exception as e:
            self.log_message.emit(f"Неожиданная ошибка: {e}", "ERROR")
            self.error.emit(str(e))
        finally:
            if db:
                db.close()
                self.log_message.emit("Соединение закрыто", "INFO")
