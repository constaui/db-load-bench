from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QLineSeries,
    QLogValueAxis,
    QValueAxis,
)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QBrush, QColor, QCursor, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .chart_legend import ChartLegend
from ..utils.chart_data import (
    ChartStore,
    GroupKey,
    _group_key,
    series_label,
    stats_for,
)


PALETTE = [
    QColor("#1f77b4"),
    QColor("#ff7f0e"),
    QColor("#2ca02c"),
    QColor("#d62728"),
    QColor("#9467bd"),
    QColor("#8c564b"),
    QColor("#e377c2"),
    QColor("#7f7f7f"),
    QColor("#bcbd22"),
    QColor("#17becf"),
]


class LineChartWidget(QWidget):
    """
    График масштабируемости: время вставки vs. количество строк.

    Внутри каждой связки (engine, db, method, batch_size) повторы агрегируются
    по `rows`: точка на линии — среднее по повторам, тень вокруг — ±std.
    Доступна log-log шкала.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._store: ChartStore = []
        self._log_scale: bool = False

        self._chart = QChart()
        self._chart.setTitle("Время вставки vs. количество строк")
        self._chart.legend().setVisible(False)
        # Анимация при переключении log/linear выглядит дёргано — отключаем.
        self._chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._legend = ChartLegend()

        self._log_cb = QCheckBox("Log-Log")
        self._log_cb.toggled.connect(self._on_log_toggled)

        top = QHBoxLayout()
        top.addWidget(self._log_cb)
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

    def refresh(self, store: ChartStore):
        self._store = store
        self._rebuild()

    def clear(self):
        self._store = []
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)
        self._legend.rebuild(self._chart)

    def _on_log_toggled(self, checked: bool):
        self._log_scale = checked
        self._rebuild()

    def _rebuild(self):
        self._chart.removeAllSeries()
        for ax in self._chart.axes():
            self._chart.removeAxis(ax)

        if not self._store:
            self._legend.rebuild(self._chart)
            return

        groups: dict[GroupKey, list] = {}
        for run in self._store:
            if run.rows <= 0 or run.elapsed <= 0:
                continue
            groups.setdefault(_group_key(run), []).append(run)

        if not groups:
            self._legend.rebuild(self._chart)
            return

        sorted_keys = sorted(
            groups.keys(),
            key=lambda k: (k[0], k[1], k[2], k[3] if k[3] is not None else -1),
        )

        all_x: list[int] = []
        all_y: list[float] = []
        series_to_add: list[tuple[QAreaSeries, QLineSeries]] = []

        for i, key in enumerate(sorted_keys):
            runs = groups[key]
            by_rows: dict[int, list[float]] = defaultdict(list)
            for r in runs:
                by_rows[r.rows].append(r.elapsed)

            xs = sorted(by_rows.keys())
            if not xs:
                continue

            color = PALETTE[i % len(PALETTE)]
            name = series_label(runs[0])

            line = QLineSeries()
            line.setName(name)
            pen = QPen(color)
            pen.setWidth(2)
            line.setPen(pen)
            line.setPointsVisible(True)

            upper = QLineSeries()
            lower = QLineSeries()

            for x in xs:
                s = stats_for(by_rows[x])
                mean = s["mean"]
                std = s["std"]

                lo = mean - std
                if self._log_scale:
                    lo = max(lo, mean * 0.05)
                else:
                    lo = max(lo, 0.0)
                hi = mean + std

                line.append(float(x), mean)
                upper.append(float(x), hi)
                lower.append(float(x), lo)

                all_x.append(x)
                all_y.append(hi)
                all_y.append(lo if lo > 0 else mean)

            area = QAreaSeries(upper, lower)
            # QAreaSeries хранит C++ указатели на upper/lower; Python-обёртки
                # должны остаться живыми, иначе GC уничтожит и саму area.
            area._upper_ref = upper
            area._lower_ref = lower
            area.setName("")  # скрыто из легенды
            area.setPen(QPen(Qt.PenStyle.NoPen))
            band_color = QColor(color.red(), color.green(), color.blue(), 50)
            area.setBrush(QBrush(band_color))
            area.setColor(band_color)

            line.hovered.connect(
                lambda point, state, n=name: self._on_hovered(point, state, n)
            )

            series_to_add.append((area, line))

        # Сначала области (под линиями), потом линии поверх
        for area, _ in series_to_add:
            self._chart.addSeries(area)
        for _, line in series_to_add:
            self._chart.addSeries(line)

        if self._log_scale:
            axis_x = QLogValueAxis()
            axis_x.setBase(10.0)
            axis_x.setLabelFormat("%g")
            axis_x.setMinorTickCount(8)
            axis_x.setMin(min(all_x) / 2)
            axis_x.setMax(max(all_x) * 2)

            axis_y = QLogValueAxis()
            axis_y.setBase(10.0)
            axis_y.setLabelFormat("%g")
            axis_y.setMinorTickCount(8)
            positive_y = [v for v in all_y if v > 0]
            if positive_y:
                axis_y.setMin(min(positive_y) / 2)
                axis_y.setMax(max(positive_y) * 2)
        else:
            axis_x = QValueAxis()
            axis_x.setLabelFormat("%d")
            axis_x.setMin(0)
            axis_x.setMax(max(all_x) * 1.05 if all_x else 1)

            axis_y = QValueAxis()
            axis_y.setLabelFormat("%.3f")
            axis_y.setMin(0)
            axis_y.setMax(max(all_y) * 1.1 if all_y else 1.0)

        axis_x.setTitleText("Количество строк")
        axis_y.setTitleText("Время вставки (сек)")
        self._chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        for area, line in series_to_add:
            area.attachAxis(axis_x)
            area.attachAxis(axis_y)
            line.attachAxis(axis_x)
            line.attachAxis(axis_y)

        self._legend.rebuild(self._chart)

    def _on_hovered(self, point: QPointF, state: bool, name: str):
        if not state:
            QToolTip.hideText()
            return
        QToolTip.showText(
            QCursor.pos(),
            f"<b>{name}</b><br>"
            f"Строк: {int(point.x()):,}<br>"
            f"Среднее время: {point.y():.4f} сек",
            self._view,
        )
