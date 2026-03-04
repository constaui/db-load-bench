from datetime import datetime
from PyQt6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
)
from PyQt6.QtGui import QTextCharFormat, QColor
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtGui import QFont


LOG_TYPE = {
    "INFO": "#000000",
    "SUCCESS": "#4caf50",
    "ERROR": "#f44336",
}


class LogWidget(QGroupBox):
    """Блок с логами"""

    def __init__(self) -> None:
        super().__init__("Лог")

        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(_monospace_font())

        clear_btn = QPushButton("Очистить")
        save_btn = QPushButton("Сохранить")
        clear_btn.clicked.connect(self.text_area.clear)
        save_btn.clicked.connect(self._save_to_file)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(save_btn)

        layout = QVBoxLayout()
        layout.addLayout(btn_layout)
        layout.addWidget(self.text_area)
        self.setLayout(layout)

    @pyqtSlot(str, str)
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {message}"

        color = LOG_TYPE.get(level, "#ffffff")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))

        cursor = self.text_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(line + "\n", fmt)
        self.text_area.setTextCursor(cursor)
        self.text_area.ensureCursorVisible()

    def _save_to_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить лог", "", "Text Files (*.txt);;All Files (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text_area.toPlainText())


def _monospace_font():
    font = QFont("Courier New")
    return font
