from PyQt6.QtWidgets import (
    QMainWindow,
    QPushButton,
    QSplitter,
    QWidget,
    QVBoxLayout,
    QProgressBar,
)
from PyQt6.QtCore import Qt

from .widgets import LogWidget, ConfigWidget, ResultsWidget
from .workers import InsertWorker


class MainWindow(QMainWindow):
    """Главное окно приложения"""

    def __init__(self) -> None:
        super().__init__()
        self.worker = None
        self.setWindowTitle("DB Load Bench")

        self.config_widget = ConfigWidget()
        self.results_widget = ResultsWidget()
        self.log_widget = LogWidget()
        self.run_btn = QPushButton("Выполнить")
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFormat("Прогон %v из %m")

        self.run_btn.clicked.connect(self._on_run_clicked)
        self.config_widget.log_message.connect(self.log_widget.log)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.results_widget)
        right_splitter.addWidget(self.log_widget)
        right_splitter.setSizes([600, 200])

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.config_widget)
        left_layout.addWidget(self._progress)
        left_layout.addWidget(self.run_btn)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([300, 900])
        main_splitter.setMinimumSize(1000, 600)

        self.setCentralWidget(main_splitter)

    def _on_run_clicked(self):
        config = self.config_widget.get_config()

        if not config["csv_file"]:
            self.log_widget.log("Не выбран CSV файл", "ERROR")
            return
        if not config["conn_params"]["database"]:
            self.log_widget.log("Не указана база данных", "ERROR")
            return

        self.worker = InsertWorker(config)
        self.worker.log_message.connect(self.log_widget.log)
        self.worker.finished.connect(self.results_widget.update_results)
        self.worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self.worker.error.connect(lambda: self.run_btn.setEnabled(True))
        self.worker.run_progress.connect(self._on_progress)
        self.worker.finished.connect(lambda _: None)

        self.run_btn.setEnabled(False)
        self.worker.start()

    def _on_progress(self, current: int, total: int):
        self._progress.setVisible(True)
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        if current == total:
            self._progress.setVisible(False)
