from PyQt6.QtWidgets import QWidget, QFormLayout, QComboBox, QSpinBox, QLabel
from PyQt6.QtCore import pyqtSignal


INSERT_METHODS = {
    "Default Insert": "default_insert",
    "Bulk Insert": "bulk_insert",
    "File Insert": "file_insert",
}


class InsertingMethodSelector(QWidget):
    method_changed = pyqtSignal(str)
    log_message = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.combo = QComboBox()
        self.combo.addItems(INSERT_METHODS.keys())
        self.combo.currentTextChanged.connect(self._toggle_batch_size)

        self.batch_size_input = QSpinBox()
        self.batch_size_input.setRange(100, 100_000)
        self.batch_size_input.setValue(1000)
        self.batch_size_input.setSingleStep(500)

        self.batch_size_label = QLabel("Batch size")

        layout = QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("Метод вставки", self.combo)
        layout.addRow(self.batch_size_label, self.batch_size_input)
        self.setLayout(layout)

        self._toggle_batch_size(self.combo.currentText())

    def _toggle_batch_size(self, label: str):
        visible = INSERT_METHODS.get(label) == "bulk_insert"
        self.batch_size_input.setVisible(visible)
        self.batch_size_label.setVisible(visible)

    def get_batch_size(self) -> int:
        return self.batch_size_input.value()

    def _on_changed(self, label: str):
        self.method_changed.emit(INSERT_METHODS[label])
        self.log_message.emit(f"Выбран метод: {INSERT_METHODS[label]}", "INFO")

    def get_method(self) -> str:
        """Возвращает имя метода для вызова через getattr(db, method)."""
        return INSERT_METHODS[self.combo.currentText()]

    @staticmethod
    def register(label: str, method: str):
        """Регистрирует новый метод без изменения класса."""
        INSERT_METHODS[label] = method
