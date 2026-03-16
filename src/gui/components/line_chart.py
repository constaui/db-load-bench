from PyQt6.QtWidgets import QWidget, QHBoxLayout, QToolTip
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtGui import QPainter, QCursor
from PyQt6.QtCore import Qt, QPointF

from ..utils.chart_data import ChartStore, series_label, _group_key, GroupKey
from .chart_legend import ChartLegend


class LineChartWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._chart = QChart()
        self._chart.setTitle("Масштабируемость методов")
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

    def refresh(self, store: ChartStore):
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

        if not store:
            return

        groups: dict[GroupKey, list] = {}
        for run in store:
            groups.setdefault(_group_key(run), []).append(run)

        if not groups:
            return

        axis_x = QValueAxis()
        axis_x.setTitleText("Количество строк")
        axis_x.setLabelFormat("%d")
        axis_x.setMin(0)

        axis_y = QValueAxis()
        axis_y.setTitleText("Время вставки (сек)")
        axis_y.setMin(0)

        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        all_series = []

        for key, runs in groups.items():
            representative = runs[0]

            qt_series = QLineSeries()
            qt_series.setName(series_label(representative))
            qt_series.append(0, 0)

            for run in sorted(runs, key=lambda r: r.rows):
                qt_series.append(run.rows, run.elapsed)

            qt_series.hovered.connect(
                lambda point, state, name=qt_series.name(): self._on_hovered(
                    point, state, name
                )
            )

            all_series.append(qt_series)

        all_points = [p for s in all_series for p in s.points() if p.x() > 0]
        if all_points:
            axis_x.setMax(max(p.x() for p in all_points) * 1.1)
            axis_y.setMax(max(p.y() for p in all_points) * 1.1)

        for qt_series in all_series:
            self._chart.addSeries(qt_series)
            qt_series.attachAxis(axis_x)
            qt_series.attachAxis(axis_y)

        self._legend.rebuild(self._chart)

    def _on_hovered(self, point: QPointF, state: bool, name: str):
        if not state:
            QToolTip.hideText()
            return

        QToolTip.showText(
            QCursor.pos(),
            f"<b>{name}</b><br>"
            f"Строк: {int(point.x()):,}<br>"
            f"Время: {point.y():.3f} сек",
            self._view,
        )

    def clear(self):
        self._chart.removeAllSeries()
        self._legend.rebuild(self._chart)
