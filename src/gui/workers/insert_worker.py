from __future__ import annotations

import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from orchestrator.environment import capture_environment
from orchestrator.process_manager import ProcessManager, RunCancelled
from src.db import MySQLDatabase, PgSQLDatabase
from src.db.exceptions import DatabaseConnectionError


DB_CLASSES = {
    "MySQL": MySQLDatabase,
    "PostgreSQL": PgSQLDatabase,
}


def _decode_libpq_bytes(raw: bytes) -> str:
    """Перебирает вероятные кодировки сообщений libpq/MySQL: UTF-8 → cp1251
    (русская Windows) → cp1252 (западноевропейская Windows) → latin-1."""
    for enc in ("utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _humanize_unicode_error(e: UnicodeDecodeError) -> str:
    """Превращает сырой UnicodeDecodeError в осмысленное сообщение,
    декодируя байты из e.object подходящей кодировкой."""
    raw = e.object if isinstance(e.object, (bytes, bytearray)) else b""
    if not raw:
        return f"Сервер вернул сообщение в не-UTF8 кодировке: {e}"
    msg = _decode_libpq_bytes(bytes(raw)).strip()
    return f"Сервер вернул сообщение (декодировано): {msg}"


def _format_eta(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{int(seconds)} с"
    if seconds < 3600:
        return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h} ч {m:02d} мин"


class InsertWorker(QThread):
    """
    Прогоняет декартову матрицу: engines × csv_files × methods × batch_sizes × n_runs.

    На каждый MethodRun навешивает session_id, label, timestamp, environment —
    чтобы спустя время отчёт можно было собрать обратно по сессии.

    Stop: graceful между прогонами + kill текущего subprocess'а.
    """

    log_message = pyqtSignal(str, str)
    finished = pyqtSignal(dict)
    run_progress = pyqtSignal(int, int, float)  # current, total, eta_seconds
    error = pyqtSignal(str)
    session_started = pyqtSignal(str, str, int)  # session_id, label, total_runs
    session_finished = pyqtSignal(str)  # session_id

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._stopping: bool = False
        self._manager: Optional[ProcessManager] = None

    def stop(self) -> None:
        """Прерывает серию: убивает текущий subprocess и просит выйти из цикла."""
        self._stopping = True
        if self._manager is not None:
            self._manager.terminate_current()

    def _build_matrix(self) -> list[tuple[str, str, str, Optional[int]]]:
        """Декартово произведение (engine, file, method, batch_size).
        Для не-bulk методов batch_size = None (одна ячейка)."""
        engines = self.config["engines"]
        files = self.config["csv_files"]
        methods = self.config["methods"]
        batch_sizes = self.config.get("batch_sizes") or [1000]

        cells: list[tuple[str, str, str, Optional[int]]] = []
        for engine in engines:
            for csv_file in files:
                for method in methods:
                    if method == "bulk_insert":
                        for bs in batch_sizes:
                            cells.append((engine, csv_file, method, bs))
                    else:
                        cells.append((engine, csv_file, method, None))
        return cells

    def _validate(self) -> Optional[str]:
        cfg = self.config
        if not cfg.get("engines"):
            return "Не выбран ни один движок"
        if not cfg.get("methods"):
            return "Не выбран ни один метод вставки"
        if not cfg.get("csv_files"):
            return "Не добавлен ни один CSV-файл"
        for path in cfg["csv_files"]:
            if not Path(path).exists():
                return f"Файл не найден: {path}"
        if not cfg["conn_params"].get("database"):
            return "Не указана база данных"
        return None

    def run(self):
        err = self._validate()
        if err:
            self.log_message.emit(err, "ERROR")
            self.error.emit(err)
            return

        db = None
        try:
            db_class = DB_CLASSES.get(self.config["db_type"])
            if db_class is None:
                msg = f"Неизвестная СУБД: {self.config['db_type']}"
                self.log_message.emit(msg, "ERROR")
                self.error.emit(msg)
                return

            db = db_class(self.config["conn_params"])
            self.log_message.emit(f"Подключение к {self.config['db_type']}...", "INFO")
            db.connect()
            self.log_message.emit("Подключение успешно", "SUCCESS")

            db_version = db.get_version()
            env = capture_environment(db_version=db_version)
            session_id = str(uuid.uuid4())
            label = self.config.get("label", "")

            matrix = self._build_matrix()
            n_runs = self.config.get("n_runs", 10)
            total = len(matrix) * n_runs
            processed = 0          # учитывает и успешные, и ошибочные прогоны
            succeeded = 0          # только успешные (для ETA-усреднения)
            succeeded_elapsed = 0.0

            self.log_message.emit(
                f"Сессия {session_id[:8]} — {label or 'без метки'} — "
                f"{len(matrix)} ячеек × {n_runs} прогонов = {total} запусков",
                "INFO",
            )
            self.session_started.emit(session_id, label, total)
            self.run_progress.emit(0, total, 0.0)

            table = "Test"
            for engine, csv_file, method, batch in matrix:
                if self._stopping:
                    break

                conn_for_engine = {
                    **self.config["conn_params"],
                    "db_type": self.config["db_type"].lower(),
                }
                self._manager = ProcessManager(
                    engine=engine, conn_params=conn_for_engine
                )

                cell_label = self._cell_label(engine, csv_file, method, batch)
                self.log_message.emit(f"▶ Ячейка: {cell_label}", "INFO")

                for run_i in range(1, n_runs + 1):
                    if self._stopping:
                        break

                    success = False
                    dt = 0.0
                    result = None
                    try:
                        cursor = db.connection.cursor()
                        db.prepare(cursor, csv_file, table)
                        db.connection.commit()
                        cursor.close()

                        t_started = time.perf_counter()
                        timestamp = datetime.now().isoformat(timespec="seconds")
                        result = self._manager.run(
                            method=method,
                            csv_file=csv_file,
                            table_name=table,
                            batch_size=batch if batch is not None else 1000,
                        )
                        dt = time.perf_counter() - t_started
                        success = True
                    except RunCancelled:
                        self.log_message.emit("Прогон прерван пользователем", "INFO")
                        break
                    except Exception as e:
                        self.log_message.emit(
                            f"Ошибка в {cell_label} (прогон {run_i}/{n_runs}): {e}",
                            "ERROR",
                        )

                    processed += 1

                    if success and result is not None:
                        result.session_id = session_id
                        result.label = label
                        result.timestamp = timestamp
                        result.environment = env

                        succeeded += 1
                        succeeded_elapsed += dt

                        self.log_message.emit(
                            f"  [{processed}/{total}] {result.rows} строк за "
                            f"{result.elapsed:.3f} с — {result.rps:,.0f} RPS",
                            "SUCCESS",
                        )
                        self.finished.emit(result.to_dict())

                    avg = (succeeded_elapsed / succeeded) if succeeded else 0.0
                    eta = avg * (total - processed)
                    self.run_progress.emit(processed, total, eta)

                if self._stopping:
                    break

            if self._stopping:
                self.log_message.emit(
                    f"Сессия прервана: {processed}/{total} прогонов "
                    f"(успешно: {succeeded})",
                    "INFO",
                )
            else:
                self.log_message.emit(
                    f"Сессия завершена: {processed}/{total} прогонов "
                    f"(успешно: {succeeded}, с ошибкой: {processed - succeeded})",
                    "SUCCESS",
                )

            self.session_finished.emit(session_id)

        except DatabaseConnectionError as e:
            self.log_message.emit(str(e), "ERROR")
            self.error.emit(str(e))
        except UnicodeDecodeError as e:
            # libpq / mysql.connector могут вернуть локализованное сообщение
            # в кодировке OS (cp1251 на русской Windows). Декодируем сами
            # и показываем настоящую причину ошибки вместо «invalid byte».
            human = _humanize_unicode_error(e)
            self.log_message.emit(human, "ERROR")
            self.error.emit(human)
        except Exception as e:
            # На всякий случай — если UnicodeDecodeError вложен в другую
            # ошибку (бывает в C-расширениях), пытаемся раскопать причину.
            cause = e
            depth = 0
            while cause and depth < 5:
                if isinstance(cause, UnicodeDecodeError):
                    msg = _humanize_unicode_error(cause)
                    self.log_message.emit(msg, "ERROR")
                    self.error.emit(msg)
                    break
                cause = cause.__cause__ or cause.__context__
                depth += 1
            else:
                self.log_message.emit(f"Неожиданная ошибка: {e}", "ERROR")
                self.error.emit(str(e))
        finally:
            if db:
                db.close()
                self.log_message.emit("Соединение закрыто", "INFO")
            self._manager = None

    @staticmethod
    def _cell_label(engine: str, csv_file: str, method: str, batch) -> str:
        fname = Path(csv_file).name
        parts = [engine, fname, method]
        if batch is not None:
            parts.append(f"batch={batch}")
        return " / ".join(parts)
