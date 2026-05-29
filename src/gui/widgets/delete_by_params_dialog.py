"""
Диалог удаления записей из results.json по параметрам.

Идея: пользователь чекбоксами выбирает значения по 5 осям (язык, СУБД,
метод, rows, batch_size). Удаляются записи, которые совпали по ВСЕМ
осям (логическое И). По умолчанию все чекбоксы выбраны — это означает
«удалить вообще всё»; пользователь снимает галки с того, что хочет
сохранить.

Возвращает frozenset тех `id(MethodRun)` (через индекс в store), которые
надо удалить.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..utils.chart_data import ChartStore


METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}


def _format_rows(n: int) -> str:
    """Форматирование rows с разделителем тысяч."""
    return f"{n:,}".replace(",", " ")


class _CheckGroup(QGroupBox):
    """Группа чекбоксов с кнопкой «Все/ничего»."""

    def __init__(
        self,
        title: str,
        values: list,
        label_fn=None,
        parent=None,
    ):
        super().__init__(title, parent)
        self._label_fn = label_fn or (lambda v: str(v))
        self._boxes: dict = {}

        outer = QVBoxLayout()
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(2)

        # Кнопка-чекбокс «Все»
        self._all = QCheckBox("Все")
        self._all.setTristate(True)
        self._all.setChecked(True)
        self._all.clicked.connect(self._on_all_clicked)
        outer.addWidget(self._all)

        # Список значений в скролл-области (важно для rows / batch — их может
        # быть много, окно не должно тянуться).
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(120)
        scroll.setMaximumHeight(180)
        inner = QWidget()
        inner_l = QVBoxLayout(inner)
        inner_l.setContentsMargins(4, 2, 4, 2)
        inner_l.setSpacing(2)

        for v in values:
            cb = QCheckBox(self._label_fn(v))
            cb.setChecked(True)
            cb.toggled.connect(self._on_child_toggled)
            self._boxes[v] = cb
            inner_l.addWidget(cb)
        inner_l.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        self.setLayout(outer)

    def selected(self) -> set:
        return {v for v, cb in self._boxes.items() if cb.isChecked()}

    def _on_all_clicked(self):
        target = self._all.checkState() != Qt.CheckState.Checked
        for cb in self._boxes.values():
            cb.blockSignals(True)
            cb.setChecked(target)
            cb.blockSignals(False)
        self._refresh_all_state()

    def _on_child_toggled(self, _checked: bool):
        self._refresh_all_state()

    def _refresh_all_state(self):
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


class DeleteByParamsDialog(QDialog):
    """Диалог: выбор параметров для удаления записей из results.json."""

    def __init__(self, store: ChartStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Удалить записи по параметрам")
        self._store = store

        # Собираем уникальные значения по осям
        engines = sorted({r.engine for r in store})
        db_types = sorted({r.db_type for r in store})
        methods_order = ["default_insert", "bulk_insert", "file_insert"]
        methods_present = {r.method for r in store}
        methods = [m for m in methods_order if m in methods_present] + sorted(
            methods_present - set(methods_order)
        )
        rows_set = sorted({r.rows for r in store if r.rows > 0})
        batch_set = sorted(
            {r.batch_size for r in store if r.batch_size is not None}
        )

        self._g_engines = _CheckGroup("Языки", engines)
        self._g_dbs = _CheckGroup("СУБД", db_types)
        self._g_methods = _CheckGroup(
            "Методы", methods, label_fn=lambda m: METHOD_LABELS.get(m, m)
        )
        self._g_rows = _CheckGroup(
            "Объём (rows)", rows_set, label_fn=_format_rows
        )
        self._g_batch = _CheckGroup(
            "Batch size (для bulk)",
            batch_set,
            label_fn=_format_rows,
        )

        # Подключаем сигналы для пересчёта счётчика
        for group in (
            self._g_engines, self._g_dbs, self._g_methods,
            self._g_rows, self._g_batch,
        ):
            for cb in group._boxes.values():
                cb.toggled.connect(self._refresh_count)
            group._all.clicked.connect(self._refresh_count)

        # Главный layout: 5 групп в две строки + счётчик + кнопки
        groups_row1 = QHBoxLayout()
        groups_row1.addWidget(self._g_engines)
        groups_row1.addWidget(self._g_dbs)
        groups_row1.addWidget(self._g_methods)

        groups_row2 = QHBoxLayout()
        groups_row2.addWidget(self._g_rows)
        groups_row2.addWidget(self._g_batch)

        # Подсказка
        hint = QLabel(
            "Удалены будут записи, которые подходят ПО ВСЕМ осям "
            "одновременно.\n"
            "Записи без batch_size (default / file) удаляются независимо от "
            "выбора в колонке «Batch size»."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")

        # Счётчик совпадений
        self._count_label = QLabel()
        self._count_label.setStyleSheet("font-weight: bold;")

        # Кнопки
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self._delete_btn = btns.addButton(
            "Удалить", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        self._delete_btn.setStyleSheet(
            "QPushButton { background: #d32f2f; color: white; padding: 6px 14px; }"
        )
        btns.rejected.connect(self.reject)
        self._delete_btn.clicked.connect(self._on_delete_clicked)

        layout = QVBoxLayout()
        layout.addLayout(groups_row1)
        layout.addLayout(groups_row2)
        layout.addWidget(hint)
        layout.addWidget(self._count_label)
        layout.addWidget(btns)
        self.setLayout(layout)

        self._matching_indices: list[int] = []
        self._refresh_count()

    # ────────────── логика отбора ──────────────

    def _matches(self, r) -> bool:
        if r.engine not in self._g_engines.selected():
            return False
        if r.db_type not in self._g_dbs.selected():
            return False
        if r.method not in self._g_methods.selected():
            return False
        if r.rows > 0 and r.rows not in self._g_rows.selected():
            return False
        # batch_size: применяем только если значение присутствует.
        # default/file без batch удаляются без оглядки на batch-чекбоксы.
        if r.batch_size is not None and r.batch_size not in self._g_batch.selected():
            return False
        return True

    def _refresh_count(self):
        self._matching_indices = [
            i for i, r in enumerate(self._store) if self._matches(r)
        ]
        n = len(self._matching_indices)
        total = len(self._store)
        self._count_label.setText(
            f"Будет удалено: {n} из {total} записей"
            + ("  ← сейчас НИЧЕГО не выбрано" if n == 0 else "")
        )
        self._delete_btn.setEnabled(n > 0)

    # ────────────── обработчики ──────────────

    def _on_delete_clicked(self):
        n = len(self._matching_indices)
        if n == 0:
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить {n} записей из файла результатов?\n\n"
            f"Это действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.accept()

    # ────────────── публичный API ──────────────

    def matching_indices(self) -> list[int]:
        """Индексы записей в исходном store, которые надо удалить."""
        return list(self._matching_indices)
