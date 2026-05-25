from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ..components import (
    DatabaseParametersForm,
    DatabaseTypeSelector,
    EngineSelector,
    FileInput,
    InsertingMethodSelector,
)


class ConfigWidget(QGroupBox):
    """
    Настройки серии экспериментов. Разделены на два логических блока:
    «Что тестируем» и «Куда подключаемся».
    """

    log_message = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__("Настройки")

        # ── Тест ────────────────────────────────────────────────────────────
        self.engine_selector = EngineSelector()
        self.method_selector = InsertingMethodSelector()
        self.file_input = FileInput(label="CSV-файлы")

        self._runs_spin = QSpinBox()
        self._runs_spin.setRange(1, 100)
        self._runs_spin.setValue(10)
        self._runs_spin.setFixedWidth(70)

        runs_row = QHBoxLayout()
        runs_row.addWidget(QLabel("Прогонов на ячейку:"))
        runs_row.addWidget(self._runs_spin)
        runs_row.addStretch(1)

        test_box = QGroupBox("Тест")
        test_layout = QVBoxLayout()
        test_layout.addWidget(self.engine_selector, stretch=0)
        test_layout.addWidget(self.method_selector, stretch=0)
        # Список CSV-файлов забирает излишек вертикального пространства.
        test_layout.addWidget(self.file_input, stretch=1)
        test_layout.addLayout(runs_row)
        test_box.setLayout(test_layout)

        # ── Подключение ─────────────────────────────────────────────────────
        self.db_selector = DatabaseTypeSelector()
        self.db_params_form = DatabaseParametersForm()

        conn_box = QGroupBox("Подключение")
        conn_layout = QVBoxLayout()
        conn_layout.addWidget(self.db_selector)
        conn_layout.addWidget(self.db_params_form)
        conn_box.setLayout(conn_layout)

        # ── Сигналы ─────────────────────────────────────────────────────────
        self.engine_selector.log_message.connect(self.log_message)
        self.db_selector.db_changed.connect(self.db_params_form.load_from_env)
        self.file_input.log_message.connect(self.log_message)
        self.db_params_form.log_message.connect(self.log_message)
        self.db_selector.log_message.connect(self.log_message)
        self.method_selector.log_message.connect(self.log_message)
        self.db_params_form.load_from_env(self.db_selector.get_prefix())

        # test_box растягивается (там список CSV) — он принимает излишек
        # высоты; conn_box остаётся компактным сверху.
        root = QVBoxLayout()
        root.addWidget(test_box, stretch=1)
        root.addWidget(conn_box, stretch=0)
        self.setLayout(root)

    def get_config(self) -> dict:
        return {
            "engines": self.engine_selector.get_engines(),
            "methods": self.method_selector.get_methods(),
            "batch_sizes": self.method_selector.get_batch_sizes(),
            "csv_files": self.file_input.get_paths(),
            "db_type": self.db_selector.get_db_name(),
            "conn_params": self.db_params_form.get_params(),
            "n_runs": self._runs_spin.value(),
        }
