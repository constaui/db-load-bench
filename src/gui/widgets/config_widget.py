from PyQt6.QtWidgets import QGroupBox, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
from ..components import (
    FileInput,
    DatabaseParametersForm,
    DatabaseTypeSelector,
    InsertingMethodSelector,
)


class ConfigWidget(QGroupBox):
    log_message = pyqtSignal(str, str)

    def __init__(self):
        super().__init__("Настройки")

        self.file_input = FileInput(label="Файл")
        self.db_params_form = DatabaseParametersForm()
        self.db_selector = DatabaseTypeSelector()
        self.method_selector = InsertingMethodSelector()

        self.db_selector.db_changed.connect(self.db_params_form.load_from_env)

        self.file_input.log_message.connect(self.log_message)
        self.db_params_form.log_message.connect(self.log_message)
        self.db_selector.log_message.connect(self.log_message)
        self.method_selector.log_message.connect(self.log_message)

        self.db_params_form.load_from_env(self.db_selector.get_prefix())

        layout = QVBoxLayout()
        layout.addWidget(self.db_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.file_input, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.db_params_form, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.method_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(0)
        self.setLayout(layout)

    def get_config(self) -> dict:
        return {
            "db_type": self.db_selector.get_db_name(),
            "conn_params": self.db_params_form.get_params(),
            "csv_file": self.file_input.get_path(),
            "method": self.method_selector.get_method(),
            "batch_size": self.method_selector.get_batch_size(),
        }
