from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
)
from PyQt6.QtCore import pyqtSignal


class FileInput(QWidget):
    """Окно с выбором файла"""

    file_selected = pyqtSignal(str)
    log_message = pyqtSignal(str, str)

    def __init__(self, label: str = "Файл", parent=None):
        super().__init__(parent)

        self.label = QLabel(label)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Путь к файлу...")
        self.input.setReadOnly(True)

        self.button = QPushButton("Выбрать")
        self.button.clicked.connect(self._open_dialog)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.input, stretch=1)
        layout.addWidget(self.button)

        self.setLayout(layout)

    def _open_dialog(self):
        downloads = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл",
            downloads,
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.input.setText(path)
            self.file_selected.emit(path)
            self.log_message.emit(f"Выбран файл: {path}", "INFO")

    def get_path(self) -> str:
        return self.input.text()

    def set_path(self, path: str):
        self.input.setText(path)
