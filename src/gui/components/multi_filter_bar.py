from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class FilterSelection:
    """Текущий выбор пользователя по трём осям."""

    engines: frozenset[str]
    db_types: frozenset[str]
    methods: frozenset[str]


METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}


class _CheckGroup(QGroupBox):
    """Группа чекбоксов с заголовком и кнопкой «Все» (toggle-all)."""

    changed = pyqtSignal()

    def __init__(self, title: str, label_map: Optional[dict[str, str]] = None):
        super().__init__(title)
        self._label_map = label_map or {}
        self._boxes: dict[str, QCheckBox] = {}
        self._known: set[str] = set()

        self._all = QCheckBox("Все")
        self._all.setTristate(True)
        self._all.clicked.connect(self._on_all_clicked)

        self._row = QHBoxLayout()
        self._row.setContentsMargins(6, 2, 6, 2)
        self._row.setSpacing(8)
        self._row.addWidget(self._all)
        self._row.addStretch(1)
        self.setLayout(self._row)

    def set_values(self, values: list[str]) -> None:
        """Пересоздаёт чекбоксы. Сохраняет выбор по совпадающим ключам.
        Новые (ранее не виденные) значения по умолчанию включаются."""
        prev_selected = self.selected()
        prev_known = self._known

        # Сносим всё, что есть после _all (включая stretch), затем добавляем
        # новые чекбоксы и в конце возвращаем stretch. Старая версия
        # останавливала цикл при count==2, оставляя «лишний» первый чекбокс.
        while self._row.count() > 1:
            item = self._row.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self._boxes.clear()

        for v in values:
            label = self._label_map.get(v, v)
            cb = QCheckBox(label)
            if v not in prev_known:
                checked = True
            else:
                checked = v in prev_selected
            cb.setChecked(checked)
            cb.toggled.connect(self._on_child_toggled)
            self._boxes[v] = cb
            self._row.addWidget(cb)

        self._row.addStretch(1)

        self._known = set(values)
        self._refresh_all_state()

    def selected(self) -> frozenset[str]:
        return frozenset(k for k, cb in self._boxes.items() if cb.isChecked())

    def _on_all_clicked(self) -> None:
        target = self._all.checkState() != Qt.CheckState.Checked
        for cb in self._boxes.values():
            cb.blockSignals(True)
            cb.setChecked(target)
            cb.blockSignals(False)
        self._refresh_all_state()
        self.changed.emit()

    def _on_child_toggled(self, _checked: bool) -> None:
        self._refresh_all_state()
        self.changed.emit()

    def _refresh_all_state(self) -> None:
        n = len(self._boxes)
        sel = sum(1 for cb in self._boxes.values() if cb.isChecked())
        self._all.blockSignals(True)
        if n == 0 or sel == 0:
            self._all.setCheckState(Qt.CheckState.Unchecked)
        elif sel == n:
            self._all.setCheckState(Qt.CheckState.Checked)
        else:
            self._all.setCheckState(Qt.CheckState.PartiallyChecked)
        self._all.blockSignals(False)


class MultiFilterBar(QWidget):
    """Колонка с тремя группами чекбоксов: Языки / СУБД / Методы.

    Группы расположены вертикально, чтобы при большом числе значений
    чекбоксы не сжимались горизонтально.
    """

    changed = pyqtSignal(FilterSelection)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._engines = _CheckGroup("Языки")
        self._dbs = _CheckGroup("СУБД")
        self._methods = _CheckGroup("Методы", METHOD_LABELS)

        self._engines.changed.connect(self._emit)
        self._dbs.changed.connect(self._emit)
        self._methods.changed.connect(self._emit)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._engines)
        layout.addWidget(self._dbs)
        layout.addWidget(self._methods)
        self.setLayout(layout)

    def set_options(
        self,
        engines: list[str],
        db_types: list[str],
        methods: list[str],
    ) -> None:
        """Обновляет доступные значения. Не эмитит сигнал."""
        for g, vals in (
            (self._engines, engines),
            (self._dbs, db_types),
            (self._methods, methods),
        ):
            g.blockSignals(True)
            g.set_values(vals)
            g.blockSignals(False)

    def selection(self) -> FilterSelection:
        return FilterSelection(
            engines=self._engines.selected(),
            db_types=self._dbs.selected(),
            methods=self._methods.selected(),
        )

    def _emit(self) -> None:
        self.changed.emit(self.selection())
