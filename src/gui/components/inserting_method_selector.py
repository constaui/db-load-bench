from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


METHOD_LABELS = {
    "default_insert": "Default",
    "bulk_insert": "Bulk",
    "file_insert": "File",
}


class InsertingMethodSelector(QWidget):
    """
    Мульти-выбор методов вставки + список batch-size'ов для bulk_insert.
    Batch-size'ы вводятся через запятую: "100, 500, 1000, 5000".
    """

    log_message = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._boxes: dict[str, QCheckBox] = {}

        method_row = QHBoxLayout()
        method_row.setContentsMargins(0, 0, 0, 0)
        method_row.addWidget(QLabel("Методы:"))
        for key, label in METHOD_LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(key == "default_insert")
            cb.toggled.connect(self._on_method_toggled)
            self._boxes[key] = cb
            method_row.addWidget(cb)
        method_row.addStretch(1)

        self._batch_input = QLineEdit("1000")
        self._batch_input.setPlaceholderText("через запятую: 100, 500, 1000")
        self._batch_label = QLabel("Batch sizes (bulk):")

        batch_row = QHBoxLayout()
        batch_row.setContentsMargins(0, 0, 0, 0)
        batch_row.addWidget(self._batch_label)
        batch_row.addWidget(self._batch_input, stretch=1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(method_row)
        layout.addLayout(batch_row)
        self.setLayout(layout)

        self._refresh_batch_visibility()

    def _on_method_toggled(self, _checked: bool) -> None:
        self._refresh_batch_visibility()

    def _refresh_batch_visibility(self) -> None:
        visible = self._boxes["bulk_insert"].isChecked()
        self._batch_input.setVisible(visible)
        self._batch_label.setVisible(visible)

    def get_methods(self) -> list[str]:
        return [key for key, cb in self._boxes.items() if cb.isChecked()]

    def get_batch_sizes(self) -> list[int]:
        """Парсит "100, 500, 1000" → [100, 500, 1000]. Пустая строка → [1000]."""
        raw = self._batch_input.text().strip()
        if not raw:
            return [1000]
        out: list[int] = []
        for token in raw.replace(";", ",").split(","):
            token = token.strip()
            if not token:
                continue
            try:
                v = int(token)
                if v > 0:
                    out.append(v)
            except ValueError:
                self.log_message.emit(
                    f"Игнорирую некорректный batch-size: {token!r}", "ERROR"
                )
        return out or [1000]
