from PyQt6.QtCore import QThread, pyqtSignal

from orchestrator.process_manager import ProcessManager
from src.db import MySQLDatabase, PgSQLDatabase
from src.db.exceptions import DatabaseConnectionError

DB_CLASSES = {
    "MySQL": MySQLDatabase,
    "PostgreSQL": PgSQLDatabase,
}

DEFAULT_RUNS = 10


class InsertWorker(QThread):

    log_message = pyqtSignal(str, str)
    finished = pyqtSignal(dict)
    run_progress = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self):
        db = None
        n_runs = self.config.get("n_runs", DEFAULT_RUNS)

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

            manager = ProcessManager(
                engine=self.config["engine"],
                conn_params={
                    **self.config["conn_params"],
                    "db_type": self.config["db_type"].lower(),
                },
            )

            self.log_message.emit(
                f"Запуск {n_runs} прогонов: [{self.config['engine']}] {method}...",
                "INFO",
            )

            for i in range(1, n_runs + 1):
                self.run_progress.emit(i, n_runs)

                self.log_message.emit(
                    f"Прогон {i}/{n_runs}: подготовка таблицы...", "INFO"
                )
                cursor = db.connection.cursor()
                db.prepare(cursor, csv_file, table)
                db.connection.commit()
                cursor.close()

                result = manager.run(
                    method=method,
                    csv_file=csv_file,
                    table_name=table,
                    batch_size=self.config.get("batch_size", 1000),
                )

                self.log_message.emit(
                    f"Прогон {i}/{n_runs}: {result.rows} строк "
                    f"за {result.elapsed:.3f}с — {result.rps:,.0f} RPS",
                    "SUCCESS",
                )

                self.finished.emit(result.to_dict())

            self.log_message.emit(f"Все {n_runs} прогонов завершены", "SUCCESS")

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
