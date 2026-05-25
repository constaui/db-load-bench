from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class FileInput(QWidget):
    """
    Список CSV-файлов для прогона матрицы (разные размеры данных).
    """

    files_changed = pyqtSignal(list)
    log_message = pyqtSignal(str, str)

    def __init__(self, label: str = "Файлы CSV", parent=None):
        super().__init__(parent)

        self._label = QLabel(label)
        self._label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        # Минимум 5 строк по высоте; дальше растёт сколько даст родитель.
        row_h = self._list.fontMetrics().height() + 4  # ~высота одной строки
        self._list.setMinimumHeight(row_h * 5 + 4)
        self._list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._add_btn = QPushButton("+ Добавить…")
        self._remove_btn = QPushButton("− Убрать выбранные")
        self._clear_btn = QPushButton("Очистить")
        self._add_btn.clicked.connect(self._on_add)
        self._remove_btn.clicked.connect(self._on_remove)
        self._clear_btn.clicked.connect(self._on_clear)

        # Кнопки делят строку поровну (flex-like).
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self._add_btn, stretch=1)
        btn_row.addWidget(self._remove_btn, stretch=1)
        btn_row.addWidget(self._clear_btn, stretch=1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        # Метка и кнопки — фиксированной высоты, список — растягивается.
        layout.addWidget(self._label, stretch=0)
        layout.addWidget(self._list, stretch=1)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _on_add(self) -> None:
        downloads = str(Path.home() / "Downloads")
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите CSV-файлы",
            downloads,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not paths:
            return
        existing = set(self.get_paths())
        added = 0
        for p in paths:
            if p in existing:
                continue
            self._list.addItem(p)
            existing.add(p)
            added += 1
        if added:
            self.log_message.emit(f"Добавлено файлов: {added}", "INFO")
            self.files_changed.emit(self.get_paths())

    def _on_remove(self) -> None:
        rows = sorted(
            (self._list.row(i) for i in self._list.selectedItems()), reverse=True
        )
        for r in rows:
            self._list.takeItem(r)
        if rows:
            self.files_changed.emit(self.get_paths())

    def _on_clear(self) -> None:
        if self._list.count() == 0:
            return
        self._list.clear()
        self.files_changed.emit([])

    def get_paths(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def add_path(self, path: str) -> None:
        if path and path not in self.get_paths():
            self._list.addItem(path)
            self.files_changed.emit(self.get_paths())
