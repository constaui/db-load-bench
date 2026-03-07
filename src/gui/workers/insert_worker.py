from PyQt6.QtCore import QThread, pyqtSignal

from orchestrator.process_manager import ProcessManager
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

            self.log_message.emit("Подготовка таблицы...", "INFO")
            cursor = db.connection.cursor()
            db.prepare(cursor, csv_file, table)
            db.connection.commit()
            cursor.close()
            self.log_message.emit("Таблица готова", "SUCCESS")

            manager = ProcessManager(
                engine=self.config["engine"],
                conn_params={
                    **self.config["conn_params"],
                    "db_type": self.config["db_type"].lower(),
                },
            )

            self.log_message.emit(
                f"Запуск [{self.config['engine']}] {self.config['method']}...", "INFO"
            )

            result = manager.run(
                method=self.config["method"],
                csv_file=self.config["csv_file"],
                table_name="Test",
                batch_size=self.config.get("batch_size", 1000),
            )

            self.log_message.emit(
                f"Вставлено {result.rows} строк за {result.elapsed:.3f}с", "SUCCESS"
            )
            self.finished.emit(result.to_dict())

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
