from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCharts import (
    QBarCategoryAxis,
    QBoxPlotSeries,
    QBoxSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QCursor
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

from ..utils.chart_data import ChartStore, stats_for
from ..utils.metric_source import SOURCES, get_source

METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}

GROUP_BY_LABELS = {
    "engine": "по языку",
    "db_type": "по СУБД",
    "method": "по методу",
}


def _short_method(name: str) -> str:
    return METHOD_LABELS.get(name, name)


def _label(engine: str, db: str, method: str, mode: str) -> str:
    """Подпись для категории в зависимости от выбранной группировки оси X."""
    if mode == "engine":
        return f"{engine}\n{db}/{_short_method(method)}"
    if mode == "db_type":
        return f"{db}\n{engine}/{_short_method(method)}"
    return f"{_short_method(method)}\n{engine}/{db}"


def _sort_key(engine: str, db: str, method: str, mode: str) -> tuple:
    method_order = {"default_insert": 0, "bulk_insert": 1, "file_insert": 2}
    m = method_order.get(method, 99)
    if mode == "engine":
        return (engine, db, m)
    if mode == "db_type":
        return (db, engine, m)
    return (m, engine, db)


class BoxPlotWidget(QWidget):
    """
    Box-plot выбранной метрики. Каждая «коробка» — это группа
    (engine, db, method), показывающая распределение метрики по всем повторам.

    Источник метрики (RPS, CPU%, RSS, ...) и группировка по оси X — независимы.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._store: ChartStore = []
        self._group_mode: str = "engine"
        self._source_key: str = SOURCES[0].key

        self._chart = QChart()
        self._chart.setTitle("Распределение метрики по группам (box-plot)")
        self._chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self._chart.legend().setVisible(False)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._source_combo = QComboBox()
        for s in SOURCES:
            self._source_combo.addItem(s.label, s.key)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)

        self._group_combo = QComboBox()
        for key, label in GROUP_BY_LABELS.items():
            self._group_combo.addItem(label, key)
        self._group_combo.currentIndexChanged.connect(self._on_group_changed)

        top = QHBoxLayout()
        top.addWidget(QLabel("Источник:"))
        top.addWidget(self._source_combo)
        top.addSpacing(12)
        top.addWidget(QLabel("Группировка:"))
        top.addWidget(self._group_combo)
        top.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self._view)
        self.setLayout(layout)

    def refresh(self, store: ChartStore) -> None:
        self._store = store
        self._rebuild()

    def clear(self) -> None:
        self._store = []
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

    def _on_group_changed(self, _index: int) -> None:
        data = self._group_combo.currentData()
        if data:
            self._group_mode = data
            self._rebuild()

    def _on_source_changed(self, _index: int) -> None:
        data = self._source_combo.currentData()
        if data:
            self._source_key = data
            self._rebuild()

    def _rebuild(self) -> None:
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

        if not self._store:
            return

        source = get_source(self._source_key)
        buckets: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        for run in self._store:
            v = source.extract(run)
            if v is None:
                continue
            buckets[(run.engine, run.db_type, run.method)].append(v)

        if not buckets:
            self._chart.setTitle(
                f"Нет данных для «{source.label}» (метрика не замерена)"
            )
            return

        self._chart.setTitle(
            f"Распределение «{source.label}» по группам (box-plot)"
        )

        keys = sorted(buckets.keys(), key=lambda k: _sort_key(*k, self._group_mode))

        series = QBoxPlotSeries()
        categories: list[str] = []
        y_max = 0.0
        tooltips: dict[str, str] = {}

        for engine, db, method in keys:
            values = buckets[(engine, db, method)]
            stats = stats_for(values)
            if stats["n"] == 0:
                continue

            label = _label(engine, db, method, self._group_mode)
            categories.append(label)

            box = QBoxSet(
                stats["min"],
                stats["q1"],
                stats["median"],
                stats["q3"],
                stats["max"],
                label,
            )
            series.append(box)

            tooltips[label] = (
                f"<b>{engine} / {db} / {method}</b><br>"
                f"источник: {source.label}<br>"
                f"n = {int(stats['n'])}<br>"
                f"min = {source.format(stats['min'])}<br>"
                f"Q1 = {source.format(stats['q1'])}<br>"
                f"median = {source.format(stats['median'])}<br>"
                f"Q3 = {source.format(stats['q3'])}<br>"
                f"max = {source.format(stats['max'])}<br>"
                f"mean = {source.format(stats['mean'])} "
                f"± {source.format(stats['std'])}"
            )
            y_max = max(y_max, stats["max"])

        if not categories:
            return

        self._tooltips = tooltips
        series.hovered.connect(self._on_hovered)
        self._chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsAngle(-30)
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        title = source.label
        if source.unit:
            title = f"{source.label} ({source.unit})"
        axis_y.setTitleText(title)
        axis_y.setLabelFormat("%.2f" if any(c.isalpha() for c in source.unit) else "%.0f")
        axis_y.setMin(0)
        axis_y.setMax(y_max * 1.1 if y_max > 0 else 1.0)
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

    def _on_hovered(self, status: bool, box_set: QBoxSet) -> None:
        if not status:
            QToolTip.hideText()
            return
        text = getattr(self, "_tooltips", {}).get(box_set.label())
        if text:
            QToolTip.showText(QCursor.pos(), text, self._view)
