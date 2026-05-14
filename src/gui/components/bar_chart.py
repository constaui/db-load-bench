from __future__ import annotations

from PyQt6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QPainter
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .chart_legend import ChartLegend
from ..utils.chart_data import ChartStore, get_aggregated


METHOD_LABELS = {
    "default_insert": "default",
    "bulk_insert": "bulk",
    "file_insert": "file",
}

AXIS_LABELS = {
    "engine": "по языку",
    "db_type": "по СУБД",
    "method": "по методу",
}

AXIS_TITLES = {
    "engine": "Язык",
    "db_type": "СУБД",
    "method": "Метод",
}


class BarChartWidget(QWidget):
    """
    Сравнительный bar-chart по RPS. Ось X переключается селектором: язык / СУБД
    / метод. Подпись серии содержит только оставшиеся (не-X) измерения, чтобы
    не дублировать категорию.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._store: ChartStore = []
        self._axis_mode: str = "engine"

        self._chart = QChart()
        self._chart.setTitle("Пропускная способность методов вставки (строк/сек)")
        self._chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self._chart.legend().setVisible(False)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._legend = ChartLegend()

        self._axis_combo = QComboBox()
        for key, label in AXIS_LABELS.items():
            self._axis_combo.addItem(label, key)
        idx = self._axis_combo.findData(self._axis_mode)
        if idx >= 0:
            self._axis_combo.setCurrentIndex(idx)
        self._axis_combo.currentIndexChanged.connect(self._on_axis_changed)

        top = QHBoxLayout()
        top.addWidget(QLabel("Ось X:"))
        top.addWidget(self._axis_combo)
        top.addStretch(1)

        chart_row = QHBoxLayout()
        chart_row.setContentsMargins(0, 0, 0, 0)
        chart_row.addWidget(self._view)
        chart_row.addWidget(self._legend)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(chart_row)
        self.setLayout(layout)

        self._categories: list[str] = []

    def refresh(self, store: ChartStore):
        self._store = store
        self._rebuild()

    def clear(self):
        self._store = []
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)
        self._categories = []
        self._legend.rebuild(self._chart)

    def _on_axis_changed(self, _index: int):
        data = self._axis_combo.currentData()
        if data:
            self._axis_mode = data
            self._rebuild()

    def _x_value(self, run) -> str:
        if self._axis_mode == "engine":
            return run.engine
        if self._axis_mode == "db_type":
            return run.db_type
        return METHOD_LABELS.get(run.method, run.method)

    def _series_label(self, run) -> str:
        """Подпись серии — только те оси, которые НЕ на X."""
        parts: list[str] = []
        if self._axis_mode != "engine":
            parts.append(run.engine)
        if self._axis_mode != "db_type":
            parts.append(run.db_type)
        if self._axis_mode != "method":
            parts.append(METHOD_LABELS.get(run.method, run.method))
        if run.method == "bulk_insert" and run.batch_size is not None:
            parts.append(f"batch={run.batch_size}")
        return " / ".join(parts) if parts else "all"

    def _rebuild(self):
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

        aggregated = get_aggregated(self._store)
        if not aggregated:
            self._categories = []
            self._legend.rebuild(self._chart)
            return

        self._categories = sorted(
            {self._x_value(run) for run in aggregated.values()}
        )

        cell: dict[tuple[str, str], float] = {}
        for run in aggregated.values():
            cell[(self._series_label(run), self._x_value(run))] = run.rps

        labels = sorted({lbl for lbl, _ in cell.keys()})

        series = QBarSeries()
        for label in labels:
            bs = QBarSet(label)
            for cat in self._categories:
                bs.append(cell.get((label, cat), 0.0))
            series.append(bs)

        series.hovered.connect(self._on_hovered)
        self._chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(self._categories)
        axis_x.setTitleText(AXIS_TITLES[self._axis_mode])
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setTitleText("Строк/сек")
        axis_y.setLabelFormat("%.0f")
        axis_y.setMin(0)
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        self._legend.rebuild(self._chart)

    def _on_hovered(self, status: bool, index: int, bar_set: QBarSet):
        if not status:
            QToolTip.hideText()
            return

        cat = self._categories[index] if index < len(self._categories) else "?"
        rps = bar_set.at(index)

        if rps <= 0:
            QToolTip.showText(
                QCursor.pos(),
                f"<b>{bar_set.label()}</b><br>"
                f"{AXIS_TITLES[self._axis_mode]}: {cat}<br>"
                f"нет данных",
                self._view,
            )
            return

        QToolTip.showText(
            QCursor.pos(),
            f"<b>{bar_set.label()}</b><br>"
            f"{AXIS_TITLES[self._axis_mode]}: {cat}<br>"
            f"Строк/сек: {rps:,.0f}",
            self._view,
        )
