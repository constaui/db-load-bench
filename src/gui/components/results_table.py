from __future__ import annotations

import csv as csv_module
import io
from collections import defaultdict
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QFileDialog,
    QLabel,
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt

from ..utils.chart_data import ChartStore

METHODS = ["default_insert", "bulk_insert", "file_insert"]
METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}

COLOR_EMPTY = QColor("#f5f5f5")
COLOR_MIN = QColor("#c8e6c9")
COLOR_MAX = QColor("#1b5e20")
COLOR_SPEEDUP = QColor("#e3f2fd")  # фон строки speedup
COLOR_HEADER = QColor("#37474f")  # фон заголовков
COLOR_SUBHDR = QColor("#546e7a")


def _lerp_color(color_a: QColor, color_b: QColor, t: float) -> QColor:
    """Линейная интерполяция между двумя цветами, t ∈ [0, 1]."""
    r = int(color_a.red() + (color_b.red() - color_a.red()) * t)
    g = int(color_a.green() + (color_b.green() - color_a.green()) * t)
    b = int(color_a.blue() + (color_b.blue() - color_a.blue()) * t)
    return QColor(r, g, b)


def _header_item(text: str, bg: QColor = COLOR_HEADER) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setBackground(bg)
    font = QFont()
    font.setBold(True)
    item.setFont(font)
    fg = QColor("white")
    item.setForeground(fg)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
    return item


def _data_item(text: str, bg: QColor = COLOR_EMPTY) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setBackground(bg)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


def _aggregate(store: ChartStore) -> dict[tuple, float]:
    """
    Возвращает усреднённый RPS по ключу (engine, db_type, method).
    """
    buckets: dict[tuple, list[float]] = defaultdict(list)
    for run in store:
        key = (run.engine, run.db_type, run.method)
        buckets[key].append(run.rps)
    return {k: sum(v) / len(v) for k, v in buckets.items()}


class ResultsTableWidget(QWidget):
    """
    Сводная таблица средних значений RPS по осям:
        строки  — языки программирования
        столбцы — (СУБД × метод вставки)

    Для каждого языка добавляется подстрока «ускорение» (×N),
    показывающая во сколько раз bulk/file быстрее default_insert.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._store: ChartStore = []

        title = QLabel("Средний RPS по языкам, методам и СУБД")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._export_btn = QPushButton("Экспорт в CSV")
        self._export_btn.clicked.connect(self._export_csv)

        top_bar = QHBoxLayout()
        top_bar.addWidget(title, stretch=1)
        top_bar.addWidget(self._export_btn)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top_bar)
        layout.addWidget(self._table)
        self.setLayout(layout)

    def refresh(self, store: ChartStore) -> None:
        self._store = store
        self._rebuild()

    def clear(self) -> None:
        self._store = []
        self._table.clearContents()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)

    def _rebuild(self) -> None:
        if not self._store:
            self.clear()
            return

        avg = _aggregate(self._store)
        engines = sorted({run.engine for run in self._store})
        db_types = sorted({run.db_type for run in self._store})

        all_rps = [v for v in avg.values() if v > 0]
        rps_min = min(all_rps) if all_rps else 1.0
        rps_max = max(all_rps) if all_rps else 1.0

        n_data_cols = len(db_types) * len(METHODS)
        n_cols = 1 + n_data_cols

        n_data_rows = len(engines) * 2
        n_rows = 2 + n_data_rows

        self._table.setRowCount(n_rows)
        self._table.setColumnCount(n_cols)

        self._table.setItem(0, 0, _header_item(""))
        for di, db in enumerate(db_types):
            col_start = 1 + di * len(METHODS)

            self._table.setItem(0, col_start, _header_item(db))
            self._table.setSpan(0, col_start, 1, len(METHODS))

        self._table.setItem(1, 0, _header_item("Язык", COLOR_SUBHDR))
        for di, db in enumerate(db_types):
            for mi, method in enumerate(METHODS):
                col = 1 + di * len(METHODS) + mi
                self._table.setItem(
                    1, col, _header_item(METHOD_LABELS[method], COLOR_SUBHDR)
                )

        all_rps = [v for v in avg.values() if v > 0]
        rps_min = min(all_rps) if all_rps else 0.0
        rps_max = max(all_rps) if all_rps else 1.0

        for ei, engine in enumerate(engines):
            data_row = 2 + ei * 2
            speedup_row = data_row + 1

            lang_item = _header_item(engine, QColor("#455a64"))
            self._table.setItem(data_row, 0, lang_item)
            self._table.setSpan(data_row, 0, 2, 1)

            for di, db in enumerate(db_types):
                for mi, method in enumerate(METHODS):
                    col = 1 + di * len(METHODS) + mi
                    rps = avg.get((engine, db, method))

                    if rps is not None:
                        t = (rps - rps_min) / (rps_max - rps_min + 1e-9)
                        bg = _lerp_color(COLOR_MIN, COLOR_MAX, t)
                        item = _data_item(f"{rps:,.0f}", bg)
                        item.setForeground(
                            QColor("white") if t > 0.5 else QColor("#212121")
                        )
                    else:
                        item = _data_item("—")
                    self._table.setItem(data_row, col, item)

                    if rps is not None and rps > 0:
                        ratio = rps / rps_min
                        is_min = abs(rps - rps_min) < 1
                        is_max = abs(rps - rps_max) < 1

                        sp_item = _data_item(f"×{ratio:.1f}")
                        sp_item.setBackground(COLOR_SPEEDUP)

                        if is_min:
                            sp_item.setBackground(QColor("#ffebee"))
                            sp_item.setForeground(QColor("#b71c1c"))
                            font = QFont()
                            font.setBold(True)
                            sp_item.setFont(font)
                        elif is_max:
                            sp_item.setBackground(QColor("#e8f5e9"))
                            sp_item.setForeground(QColor("#1b5e20"))
                            font = QFont()
                            font.setBold(True)
                            sp_item.setFont(font)
                    else:
                        sp_item = _data_item("—")
                        sp_item.setBackground(COLOR_SPEEDUP)

                    self._table.setItem(speedup_row, col, sp_item)

        self._table.resizeColumnsToContents()
        self._table.resizeRowsToContents()
        self._table.setColumnWidth(0, 90)

    def _export_csv(self) -> None:
        if not self._store:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить CSV", "results_summary.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        avg = _aggregate(self._store)
        engines = sorted({run.engine for run in self._store})
        db_types = sorted({run.db_type for run in self._store})

        buf = io.StringIO()
        writer = csv_module.writer(buf)

        header = ["Язык"]
        for db in db_types:
            for method in METHODS:
                header.append(f"{db} / {METHOD_LABELS[method]} (RPS)")
        writer.writerow(header)

        for engine in engines:
            rps_row = [engine]
            speedup_row = [f"{engine} (ускорение)"]
            for db in db_types:
                default_rps = avg.get((engine, db, "default_insert"))
                for method in METHODS:
                    rps = avg.get((engine, db, method))
                    rps_row.append(f"{rps:.1f}" if rps else "")
                    if method == "default_insert":
                        speedup_row.append("base")
                    elif rps and default_rps:
                        speedup_row.append(f"x{rps / default_rps:.2f}")
                    else:
                        speedup_row.append("")
            writer.writerow(rps_row)
            writer.writerow(speedup_row)

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(buf.getvalue())
