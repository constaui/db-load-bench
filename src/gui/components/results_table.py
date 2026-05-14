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
from ..utils.metric_source import SOURCES, MetricSource, get_source

METHODS = ["default_insert", "bulk_insert", "file_insert"]
METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}

STAT_LABELS = {
    "mean_std": "Среднее ± std",
    "mean": "Среднее",
    "median": "Медиана",
    "min": "Минимум",
    "max": "Максимум",
    "std": "Ст. отклонение",
}
STAT_KEYS = list(STAT_LABELS.keys())

COLOR_EMPTY = QColor("#f5f5f5")
COLOR_GOOD = QColor("#1b5e20")
COLOR_NEUTRAL = QColor("#c8e6c9")
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


def _collect_stats(
    store: ChartStore, source: MetricSource
) -> dict[tuple[str, str, str], dict[str, float]]:
    """Статистика по выбранному источнику для каждой связки (engine, db, method)."""
    buckets: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for run in store:
        v = source.extract(run)
        if v is None:
            continue
        buckets[(run.engine, run.db_type, run.method)].append(v)
    return {k: stats_for(v) for k, v in buckets.items()}


def _format_cell(stats: dict[str, float], stat_key: str, source: MetricSource) -> str:
    if stat_key == "mean_std":
        return f"{source.format(stats['mean'])} ± {source.format(stats['std'])}"
    if stat_key == "mean":
        return source.format(stats["mean"])
    return source.format(stats.get(stat_key, 0.0))


def _stat_value(stats: dict[str, float], stat_key: str) -> float:
    """Скалярное значение, по которому строится тепловая шкала и ускорение."""
    if stat_key in ("mean_std", "mean"):
        return stats["mean"]
    return stats.get(stat_key, 0.0)


class ResultsTableWidget(QWidget):
    """
    Сводная таблица по выбранному источнику метрик (RPS / CPU / RSS / I/O / ...).

    Управление:
      - Источник: что мерить (RPS, CPU% avg, RSS peak, ...).
      - Статистика: как агрегировать повторы (Среднее ± std, Среднее, Медиана, ...).

    Ячейка содержит выбранную статистику. Подстрока «×default» показывает
    отношение к default_insert той же связки (engine, db). Цвет тепловой
    шкалы инвертируется для метрик «меньше = лучше».
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._store: ChartStore = []
        self._source_key: str = SOURCES[0].key
        self._stat: str = "mean_std"

        title = QLabel("Сводная таблица результатов")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)

        self._source_combo = QComboBox()
        for s in SOURCES:
            self._source_combo.addItem(s.label, s.key)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)

        self._stat_combo = QComboBox()
        for key in STAT_KEYS:
            self._stat_combo.addItem(STAT_LABELS[key], key)
        self._stat_combo.currentIndexChanged.connect(self._on_stat_changed)

        self._export_btn = QPushButton("Экспорт в CSV")
        self._export_btn.clicked.connect(self._export_csv)

        top_bar = QHBoxLayout()
        top_bar.addWidget(title)
        top_bar.addStretch(1)
        top_bar.addWidget(QLabel("Источник:"))
        top_bar.addWidget(self._source_combo)
        top_bar.addWidget(QLabel("Статистика:"))
        top_bar.addWidget(self._stat_combo)
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

    def _on_source_changed(self, _index: int) -> None:
        key = self._source_combo.currentData()
        if key:
            self._source_key = key
            self._rebuild()

    def _on_stat_changed(self, _index: int) -> None:
        key = self._stat_combo.currentData()
        if key:
            self._stat = key
            self._rebuild()

    def _rebuild(self) -> None:
        if not self._store:
            self.clear()
            return

        source = get_source(self._source_key)
        stats_map = _collect_stats(self._store, source)
        engines = sorted({r.engine for r in self._store})
        db_types = sorted({r.db_type for r in self._store})
        methods = [m for m in METHODS if any(r.method == m for r in self._store)]

        values = [
            _stat_value(s, self._stat)
            for s in stats_map.values()
            if s.get("n", 0) > 0
        ]
        values = [v for v in values if v > 0]
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
                base_val = _stat_value(base_stats, self._stat) if base_stats else None

                for mi, method in enumerate(methods):
                    col = 1 + di * len(methods) + mi
                    stats = stats_map.get((engine, db, method))

                    if stats and stats["n"] > 0:
                        val = _stat_value(stats, self._stat)
                        text = _format_cell(stats, self._stat, source)
                        if v_max > v_min and val > 0:
                            t = (val - v_min) / (v_max - v_min + 1e-9)
                            if source.lower_is_better:
                                t = 1.0 - t
                        else:
                            t = 0.5
                        bg = _lerp_color(COLOR_NEUTRAL, COLOR_GOOD, t)
                        item = _data_item(text, bg)
                        item.setForeground(
                            QColor("white") if t > 0.5 else QColor("#212121")
                        )
                        item.setToolTip(
                            f"<b>{engine} / {db} / {method}</b><br>"
                            f"источник: {source.label}<br>"
                            f"n = {int(stats['n'])}<br>"
                            f"mean = {source.format(stats['mean'])}<br>"
                            f"median = {source.format(stats['median'])}<br>"
                            f"std = {source.format(stats['std'])}<br>"
                            f"min = {source.format(stats['min'])}<br>"
                            f"max = {source.format(stats['max'])}"
                        )
                    else:
                        item = _data_item("—")
                        item.setToolTip("нет данных для выбранного источника")
                    self._table.setItem(data_row, col, item)

                    if method == "default_insert":
                        sp_item = _data_item("base", COLOR_BASE)
                    elif (
                        stats
                        and stats["n"] > 0
                        and base_val
                        and base_val > 0
                    ):
                        ratio = _stat_value(stats, self._stat) / base_val
                        sp_item = _data_item(f"×{ratio:.2f}", COLOR_SPEEDUP)
                        # Для метрик "меньше = лучше" знак выгоды инвертируется.
                        if source.lower_is_better:
                            better = ratio < 1.0
                        else:
                            better = ratio > 1.0
                        sp_item.setForeground(
                            QColor("#1b5e20") if better else QColor("#b71c1c")
                        )
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

        source = get_source(self._source_key)
        stats_map = _collect_stats(self._store, source)
        engines = sorted({r.engine for r in self._store})
        db_types = sorted({r.db_type for r in self._store})
        methods = [m for m in METHODS if any(r.method == m for r in self._store)]

        buf = io.StringIO()
        writer = csv_module.writer(buf)

        writer.writerow(
            [f"Источник: {source.label}; статистика: {STAT_LABELS[self._stat]}"]
        )
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
                base_val = _stat_value(base, self._stat) if base else None
                for method in methods:
                    stats = stats_map.get((engine, db, method))
                    if stats and stats["n"] > 0:
                        val_row.append(_format_cell(stats, self._stat, source))
                    else:
                        val_row.append("")
                    if method == "default_insert":
                        sp_row.append("base")
                    elif stats and stats["n"] > 0 and base_val:
                        ratio = _stat_value(stats, self._stat) / base_val
                        sp_row.append(f"×{ratio:.2f}")
                    else:
                        sp_row.append("")
            writer.writerow(val_row)
            writer.writerow(sp_row)

        writer.writerow([])
        writer.writerow([f"Полная статистика — {source.label}"])
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
                            source.format(stats["mean"]),
                            source.format(stats["median"]),
                            source.format(stats["std"]),
                            source.format(stats["min"]),
                            source.format(stats["max"]),
                        ]
                    )

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(buf.getvalue())
