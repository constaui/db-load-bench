from PyQt6.QtWidgets import QWidget, QHBoxLayout, QToolTip
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QBarSeries,
    QBarSet,
    QBarCategoryAxis,
    QValueAxis,
)
from PyQt6.QtGui import QPainter, QCursor
from PyQt6.QtCore import Qt

from .chart_legend import ChartLegend
from ..utils.chart_data import ChartStore, get_aggregated, series_label


class BarChartWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._chart = QChart()
        self._chart.setTitle("Пропускная способность методов вставки (строк/сек)")
        self._chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self._chart.legend().setVisible(False)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._legend = ChartLegend()

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        layout.addWidget(self._legend)
        self.setLayout(layout)

        self._categories: list[str] = []

    def refresh(self, store: ChartStore):
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

        aggregated = get_aggregated(store)
        if not aggregated:
            return

        self._categories = sorted({run.db_type for run in aggregated.values()})

        bar_sets: dict[str, QBarSet] = {}
        for run in aggregated.values():
            label = series_label(run)
            if label not in bar_sets:
                bar_sets[label] = QBarSet(label)

                for _ in self._categories:
                    bar_sets[label].append(0.0)

        for run in aggregated.values():
            label = series_label(run)
            idx = self._categories.index(run.db_type)
            bar_sets[label].replace(idx, run.rps)

        series = QBarSeries()
        for bar_set in bar_sets.values():
            series.append(bar_set)

        series.hovered.connect(self._on_hovered)
        self._chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(self._categories)
        axis_x.setTitleText("СУБД")
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

        db_type = self._categories[index] if index < len(self._categories) else "?"
        rps = bar_set.at(index)

        QToolTip.showText(
            QCursor.pos(),
            f"<b>{bar_set.label()}</b><br>"
            f"СУБД: {db_type}<br>"
            f"Строк/сек: {rps:,.0f}",
            self._view,
        )

    def clear(self):
        self._chart.removeAllSeries()
        self._categories = []
        self._legend.rebuild(self._chart)
