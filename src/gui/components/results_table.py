from __future__ import annotations

import csv as csv_module
import io
from collections import defaultdict

from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt

from ..utils.chart_data import ChartStore, stats_for

METHODS = ["default_insert", "bulk_insert", "file_insert"]
METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}

METRIC_LABELS = {
    "mean": "Среднее (± std)",
    "median": "Медиана",
    "min": "Минимум",
    "max": "Максимум",
    "std": "Ст. отклонение",
}
METRIC_KEYS = list(METRIC_LABELS.keys())

COLOR_EMPTY = QColor("#f5f5f5")
COLOR_MIN = QColor("#c8e6c9")
COLOR_MAX = QColor("#1b5e20")
COLOR_SPEEDUP = QColor("#e3f2fd")
COLOR_HEADER = QColor("#37474f")
COLOR_SUBHDR = QColor("#546e7a")
COLOR_BASE = QColor("#eeeeee")


def _lerp_color(color_a: QColor, color_b: QColor, t: float) -> QColor:
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
    item.setForeground(QColor("white"))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
    return item


def _data_item(text: str, bg: QColor = COLOR_EMPTY) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setBackground(bg)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


def _collect_stats(store: ChartStore) -> dict[tuple[str, str, str], dict[str, float]]:
    """RPS-статистика по ключу (engine, db_type, method)."""
    buckets: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for run in store:
        buckets[(run.engine, run.db_type, run.method)].append(run.rps)
    return {k: stats_for(v) for k, v in buckets.items()}


def _format_cell(stats: dict[str, float], metric: str) -> str:
    value = stats.get(metric, 0.0)
    if metric == "mean":
        std = stats.get("std", 0.0)
        return f"{value:,.0f} ± {std:,.0f}"
    return f"{value:,.0f}"


class ResultsTableWidget(QWidget):
    """
    Сводная таблица статистик RPS по осям:
        строки  — языки программирования (с подстрокой ускорения)
        столбцы — (СУБД × метод вставки)

    Метрика переключается выпадающим списком: mean / median / min / max / std.
    Ускорение считается относительно default_insert той же связки (engine, db).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._store: ChartStore = []
        self._metric: str = "mean"

        title = QLabel("Сводная таблица RPS")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)

        self._metric_combo = QComboBox()
        for key in METRIC_KEYS:
            self._metric_combo.addItem(METRIC_LABELS[key], key)
        self._metric_combo.currentIndexChanged.connect(self._on_metric_changed)

        self._export_btn = QPushButton("Экспорт в CSV")
        self._export_btn.clicked.connect(self._export_csv)

        top_bar = QHBoxLayout()
        top_bar.addWidget(title)
        top_bar.addStretch(1)
        top_bar.addWidget(QLabel("Метрика:"))
        top_bar.addWidget(self._metric_combo)
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

    def _on_metric_changed(self, _index: int) -> None:
        data = self._metric_combo.currentData()
        if data:
            self._metric = data
            self._rebuild()

    def _rebuild(self) -> None:
        if not self._store:
            self.clear()
            return

        stats_map = _collect_stats(self._store)
        engines = sorted({r.engine for r in self._store})
        db_types = sorted({r.db_type for r in self._store})
        methods = [m for m in METHODS if any(r.method == m for r in self._store)]

        values = [
            s[self._metric]
            for s in stats_map.values()
            if s.get("n", 0) > 0 and s[self._metric] > 0
        ]
        v_min = min(values) if values else 0.0
        v_max = max(values) if values else 1.0

        n_data_cols = len(db_types) * len(methods)
        n_cols = 1 + n_data_cols
        n_rows = 2 + len(engines) * 2

        self._table.setRowCount(n_rows)
        self._table.setColumnCount(n_cols)
        self._table.clearSpans()

        self._table.setItem(0, 0, _header_item(""))
        for di, db in enumerate(db_types):
            col_start = 1 + di * len(methods)
            self._table.setItem(0, col_start, _header_item(db))
            if len(methods) > 1:
                self._table.setSpan(0, col_start, 1, len(methods))

        self._table.setItem(1, 0, _header_item("Язык", COLOR_SUBHDR))
        for di, _db in enumerate(db_types):
            for mi, method in enumerate(methods):
                col = 1 + di * len(methods) + mi
                self._table.setItem(
                    1, col, _header_item(METHOD_LABELS.get(method, method), COLOR_SUBHDR)
                )

        for ei, engine in enumerate(engines):
            data_row = 2 + ei * 2
            speedup_row = data_row + 1

            lang_item = _header_item(engine, QColor("#455a64"))
            self._table.setItem(data_row, 0, lang_item)
            self._table.setSpan(data_row, 0, 2, 1)

            for di, db in enumerate(db_types):
                base_stats = stats_map.get((engine, db, "default_insert"))
                base_val = base_stats[self._metric] if base_stats else None

                for mi, method in enumerate(methods):
                    col = 1 + di * len(methods) + mi
                    stats = stats_map.get((engine, db, method))

                    if stats and stats["n"] > 0:
                        val = stats[self._metric]
                        text = _format_cell(stats, self._metric)
                        t = (val - v_min) / (v_max - v_min + 1e-9) if val > 0 else 0.0
                        bg = _lerp_color(COLOR_MIN, COLOR_MAX, t)
                        item = _data_item(text, bg)
                        item.setForeground(
                            QColor("white") if t > 0.5 else QColor("#212121")
                        )
                        item.setToolTip(
                            f"<b>{engine} / {db} / {method}</b><br>"
                            f"n = {int(stats['n'])}<br>"
                            f"mean = {stats['mean']:,.1f}<br>"
                            f"median = {stats['median']:,.1f}<br>"
                            f"std = {stats['std']:,.1f}<br>"
                            f"min = {stats['min']:,.1f}<br>"
                            f"max = {stats['max']:,.1f}"
                        )
                    else:
                        item = _data_item("—")
                    self._table.setItem(data_row, col, item)

                    if method == "default_insert":
                        sp_item = _data_item("base", COLOR_BASE)
                    elif (
                        stats
                        and stats["n"] > 0
                        and base_val is not None
                        and base_val > 0
                    ):
                        ratio = stats[self._metric] / base_val
                        sp_item = _data_item(f"×{ratio:.2f}", COLOR_SPEEDUP)
                        if ratio >= 1.0:
                            sp_item.setForeground(QColor("#1b5e20"))
                        else:
                            sp_item.setForeground(QColor("#b71c1c"))
                        if ratio >= 2.0 or ratio <= 0.5:
                            font = QFont()
                            font.setBold(True)
                            sp_item.setFont(font)
                    else:
                        sp_item = _data_item("—", COLOR_SPEEDUP)
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

        stats_map = _collect_stats(self._store)
        engines = sorted({r.engine for r in self._store})
        db_types = sorted({r.db_type for r in self._store})
        methods = [m for m in METHODS if any(r.method == m for r in self._store)]

        buf = io.StringIO()
        writer = csv_module.writer(buf)

        writer.writerow([f"Метрика: {METRIC_LABELS[self._metric]} (RPS)"])
        header = ["Язык"]
        for db in db_types:
            for method in methods:
                header.append(f"{db} / {METHOD_LABELS.get(method, method)}")
        writer.writerow(header)

        for engine in engines:
            val_row: list[str] = [engine]
            sp_row: list[str] = [f"{engine} (×default)"]
            for db in db_types:
                base = stats_map.get((engine, db, "default_insert"))
                base_val = base[self._metric] if base else None
                for method in methods:
                    stats = stats_map.get((engine, db, method))
                    if stats and stats["n"] > 0:
                        val_row.append(_format_cell(stats, self._metric))
                    else:
                        val_row.append("")
                    if method == "default_insert":
                        sp_row.append("base")
                    elif stats and stats["n"] > 0 and base_val:
                        sp_row.append(f"×{stats[self._metric] / base_val:.2f}")
                    else:
                        sp_row.append("")
            writer.writerow(val_row)
            writer.writerow(sp_row)

        writer.writerow([])
        writer.writerow(["Полная статистика (RPS) — по всем срезам"])
        writer.writerow(
            ["engine", "db_type", "method", "n", "mean", "median", "std", "min", "max"]
        )
        for engine in engines:
            for db in db_types:
                for method in methods:
                    stats = stats_map.get((engine, db, method))
                    if not stats or stats["n"] == 0:
                        continue
                    writer.writerow(
                        [
                            engine,
                            db,
                            method,
                            int(stats["n"]),
                            f"{stats['mean']:.1f}",
                            f"{stats['median']:.1f}",
                            f"{stats['std']:.1f}",
                            f"{stats['min']:.1f}",
                            f"{stats['max']:.1f}",
                        ]
                    )

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(buf.getvalue())
