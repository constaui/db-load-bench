from PyQt6.QtWidgets import QWidget, QFormLayout, QComboBox
from PyQt6.QtCore import pyqtSignal


DB_CONFIGS = {
    "MySQL": "MYSQL",
    "PostgreSQL": "PGSQL",
}


class DatabaseTypeSelector(QWidget):
    """Окно с выбором СУБД"""

    db_changed = pyqtSignal(str)
    log_message = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.combo = QComboBox()
        self.combo.addItems(DB_CONFIGS.keys())
        self.combo.currentTextChanged.connect(self._on_changed)

        layout = QFormLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("СУБД", self.combo)
        self.setLayout(layout)

    def _on_changed(self, db_name: str):
        prefix = DB_CONFIGS.get(db_name, "")
        self.log_message.emit(f"Выбрана СУБД: {db_name}", "INFO")
        self.db_changed.emit(prefix)

    def get_prefix(self) -> str:
        return DB_CONFIGS.get(self.combo.currentText(), "")

    def get_db_name(self) -> str:
        return self.combo.currentText()
