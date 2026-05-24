from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget


ENGINES = ["Python", "Go", "Rust", "Java"]


class EngineSelector(QWidget):
    """Мульти-выбор движков для прогона матрицы экспериментов."""

    selection_changed = pyqtSignal(list)
    log_message = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._boxes: dict[str, QCheckBox] = {}

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Движки:"))
        for i, name in enumerate(ENGINES):
            cb = QCheckBox(name)
            cb.setChecked(i == 0)
            cb.toggled.connect(self._on_changed)
            self._boxes[name] = cb
            layout.addWidget(cb)
        layout.addStretch(1)
        self.setLayout(layout)

    def get_engines(self) -> list[str]:
        return [name for name, cb in self._boxes.items() if cb.isChecked()]

    def _on_changed(self, _checked: bool) -> None:
        sel = self.get_engines()
        self.selection_changed.emit(sel)
