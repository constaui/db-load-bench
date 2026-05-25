from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .widgets import ConfigWidget, LogWidget, ResultsWidget
from .workers import InsertWorker


class MainWindow(QMainWindow):
    """Главное окно приложения"""

    def __init__(self) -> None:
        super().__init__()
        self.worker: InsertWorker | None = None
        self.setWindowTitle("DB Load Bench")

        self.config_widget = ConfigWidget()
        self.results_widget = ResultsWidget()
        self.log_widget = LogWidget()

        # Обе кнопки — одинаковые QPushButton без особого стиля.
        # Стилизация Stop (плоский вид) применяется к обеим.
        self.run_btn = QPushButton("▶ Выполнить серию")
        self.stop_btn = QPushButton("■ Остановить")
        self.stop_btn.setEnabled(False)

        # Прогресс растягивается на всю строку.
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        self._progress.setFormat("0 / 0")

        self.run_btn.clicked.connect(self._on_run_clicked)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.config_widget.log_message.connect(self.log_widget.log)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.results_widget)
        right_splitter.addWidget(self.log_widget)
        right_splitter.setSizes([600, 200])

        # Кнопки делят строку поровну (flex-like) и занимают её целиком.
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.run_btn, stretch=1)
        btn_row.addWidget(self.stop_btn, stretch=1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.config_widget)
        left_layout.addWidget(self._progress)
        left_layout.addLayout(btn_row)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([360, 900])
        main_splitter.setMinimumSize(1100, 600)

        self.setCentralWidget(main_splitter)

    def _on_run_clicked(self):
        if self.worker is not None and self.worker.isRunning():
            return

        config = self.config_widget.get_config()

        self.worker = InsertWorker(config)
        self.worker.log_message.connect(self.log_widget.log)
        self.worker.finished.connect(self.results_widget.update_results)
        self.worker.error.connect(self._on_session_error)
        self.worker.run_progress.connect(self._on_progress)
        self.worker.session_started.connect(self.results_widget.start_session)
        self.worker.session_finished.connect(self.results_widget.end_session)
        self.worker.session_finished.connect(self._on_session_finished)

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress.setFormat("0 / 0")

        self.worker.start()

    def _on_stop_clicked(self):
        if self.worker is not None and self.worker.isRunning():
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("Останавливаем...")
            self.worker.stop()

    def _on_progress(self, current: int, total: int):
        self._progress.setMaximum(total if total > 0 else 1)
        self._progress.setValue(current)
        self._progress.setFormat(f"{current} / {total}")

    def _on_session_error(self, _msg: str):
        # Если сессия упала уже после start_session — буфер мог остаться поднятым,
        # снимем его и нарисуем то, что успели набрать.
        self.results_widget.end_session("")
        self._reset_buttons()
        self._progress.setVisible(False)

    def _on_session_finished(self, _session_id: str):
        self._reset_buttons()

    def _reset_buttons(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Остановить")
