from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox
from PyQt6.QtCore import pyqtSignal, Qt

from ..components import (
    FileInput,
    DatabaseParametersForm,
    DatabaseTypeSelector,
    InsertingMethodSelector,
    EngineSelector,
)


class ConfigWidget(QGroupBox):
    """Блок с настройками параметров БД"""

    log_message = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__("Настройки")

        self.engine_selector = EngineSelector()
        self.file_input = FileInput(label="Файл")
        self.db_params_form = DatabaseParametersForm()
        self.db_selector = DatabaseTypeSelector()
        self.method_selector = InsertingMethodSelector()
        runs_layout = QHBoxLayout()
        runs_label = QLabel("Прогонов:")
        self._runs_spin = QSpinBox()
        self._runs_spin.setRange(1, 100)
        self._runs_spin.setValue(10)
        self._runs_spin.setFixedWidth(60)
        runs_layout.addWidget(runs_label)
        runs_layout.addWidget(self._runs_spin)
        runs_layout.addStretch()

        self.engine_selector.log_message.connect(self.log_message)
        self.db_selector.db_changed.connect(self.db_params_form.load_from_env)
        self.file_input.log_message.connect(self.log_message)
        self.db_params_form.log_message.connect(self.log_message)
        self.db_selector.log_message.connect(self.log_message)
        self.method_selector.log_message.connect(self.log_message)
        self.db_params_form.load_from_env(self.db_selector.get_prefix())

        layout = QVBoxLayout()
        layout.addWidget(self.engine_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.db_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.file_input, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.db_params_form, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.method_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(runs_layout)
        layout.addStretch(0)
        self.setLayout(layout)

    def get_config(self) -> dict:
        return {
            "engine": self.engine_selector.get_engine(),
            "db_type": self.db_selector.get_db_name(),
            "conn_params": self.db_params_form.get_params(),
            "csv_file": self.file_input.get_path(),
            "method": self.method_selector.get_method(),
            "batch_size": self.method_selector.get_batch_size(),
            "n_runs": self._runs_spin.value(),
        }
