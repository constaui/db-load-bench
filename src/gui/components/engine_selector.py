from PyQt6.QtWidgets import QWidget, QFormLayout, QComboBox
from PyQt6.QtCore import pyqtSignal


ENGINE_CONFIGS = {
    "Python": "PYTHON",
}


class EngineSelector(QWidget):
    """Окно с выбором движка (языка программирования)"""

    engine_changed = pyqtSignal(str)
    log_message = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.combo = QComboBox()
        self.combo.addItems(ENGINE_CONFIGS.keys())
        self.combo.currentTextChanged.connect(self._on_changed)

        layout = QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("Движок", self.combo)
        self.setLayout(layout)

    def _on_changed(self, engine_name: str):
        prefix = ENGINE_CONFIGS.get(engine_name, "")
        self.log_message.emit(f"Выбран движок: {engine_name}", "INFO")
        self.engine_changed.emit(prefix)

    def get_prefix(self) -> str:
        return ENGINE_CONFIGS.get(self.combo.currentText(), "")

    def get_engine(self) -> str:
        return self.combo.currentText()
