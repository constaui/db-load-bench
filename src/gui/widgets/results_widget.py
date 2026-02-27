from PyQt6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QLabel,
)
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtCharts import (
    QChart,
    QChartView,
    QBarSeries,
    QBarSet,
    QBarCategoryAxis,
    QLineSeries,
    QValueAxis,
)
from PyQt6.QtGui import QPainter

from ..utils.chart_data import ChartStore, add_run, get_latest, series_label

ALL_DBS = "Все СУБД"


class ResultsWidget(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Результаты", parent)

        self._store: ChartStore = {}

        # Селектор СУБД
        self._db_selector = QComboBox()
        self._db_selector.addItem(ALL_DBS)
        self._db_selector.currentTextChanged.connect(self._on_db_filter_changed)

        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self._clear)

        self._bar_chart_view = self._build_bar_chart()
        self._line_chart_view = self._build_line_chart()

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QLabel("СУБД:"))
        btn_layout.addWidget(self._db_selector)
        btn_layout.addStretch()
        btn_layout.addWidget(clear_btn)

        charts_layout = QHBoxLayout()
        charts_layout.addWidget(self._bar_chart_view)
        charts_layout.addWidget(self._line_chart_view)

        layout = QVBoxLayout()
        layout.addLayout(btn_layout)
        layout.addLayout(charts_layout)
        self.setLayout(layout)

    @pyqtSlot(dict)
    def update_results(self, result: dict):
        add_run(
            self._store,
            result["db_type"],
            result["method"],
            result["rows"],
            result["elapsed"],
            result.get("batch_size"),  # ← передаём batch_size
        )
        self._sync_selector(result["db_type"])
        self._refresh_charts()

    def _sync_selector(self, db_type: str):
        """Добавляет новую СУБД в селектор, если её там ещё нет."""
        items = [
            self._db_selector.itemText(i) for i in range(self._db_selector.count())
        ]
        if db_type not in items:
            self._db_selector.addItem(db_type)

    def _on_db_filter_changed(self, _: str):
        self._refresh_charts()

    def _active_store(self) -> ChartStore:
        """Возвращает срез хранилища по выбранной СУБД."""
        selected = self._db_selector.currentText()
        if selected == ALL_DBS:
            return self._store
        return {selected: self._store[selected]} if selected in self._store else {}

    def _refresh_charts(self):
        self._refresh_bar_chart()
        self._refresh_line_chart()

    # ──────────────────────────────────────────────
    # Bar Chart
    # ──────────────────────────────────────────────

    def _build_bar_chart(self) -> QChartView:
        self._bar_chart = QChart()
        self._bar_chart.setTitle("Сравнение методов")
        self._bar_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self._bar_chart.legend().setVisible(True)
        self._bar_chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        view = QChartView(self._bar_chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        return view

    def _refresh_bar_chart(self):
        self._bar_chart.removeAllSeries()
        for ax in self._bar_chart.axes():
            self._bar_chart.removeAxis(ax)

        latest = get_latest(self._active_store())
        if not latest:
            return

        categories = []
        rps_values = []
        elapsed_values = []

        for db_type, methods in latest.items():
            for method, run in methods.items():
                categories.append(series_label(db_type, method, run))
                rps_values.append(run.rps)
                elapsed_values.append(run.elapsed)

        rps_set = QBarSet("Строк/сек")
        elapsed_set = QBarSet("Время (сек)")
        rps_set.append(rps_values)
        elapsed_set.append(elapsed_values)

        rps_series = QBarSeries()
        elapsed_series = QBarSeries()
        rps_series.append(rps_set)
        elapsed_series.append(elapsed_set)

        self._bar_chart.addSeries(rps_series)
        self._bar_chart.addSeries(elapsed_series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        self._bar_chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        rps_series.attachAxis(axis_x)
        elapsed_series.attachAxis(axis_x)

        axis_y_rps = QValueAxis()
        axis_y_rps.setTitleText("Строк/сек")
        self._bar_chart.addAxis(axis_y_rps, Qt.AlignmentFlag.AlignLeft)
        rps_series.attachAxis(axis_y_rps)

        axis_y_elapsed = QValueAxis()
        axis_y_elapsed.setTitleText("Время (сек)")
        self._bar_chart.addAxis(axis_y_elapsed, Qt.AlignmentFlag.AlignRight)
        elapsed_series.attachAxis(axis_y_elapsed)

    # ──────────────────────────────────────────────
    # Line Chart
    # ──────────────────────────────────────────────

    def _build_line_chart(self) -> QChartView:
        self._line_chart = QChart()
        self._line_chart.setTitle("Масштабируемость методов")
        self._line_chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        self._line_chart.legend().setVisible(True)
        self._line_chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        view = QChartView(self._line_chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        return view

    def _refresh_line_chart(self):
        self._line_chart.removeAllSeries()
        for ax in self._line_chart.axes():
            self._line_chart.removeAxis(ax)

        store = self._active_store()
        if not store:
            return

        axis_x = QValueAxis()
        axis_x.setTitleText("Количество строк")
        axis_x.setLabelFormat("%d")

        axis_y = QValueAxis()
        axis_y.setTitleText("Время вставки (сек)")

        self._line_chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self._line_chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

        for db_type, methods in store.items():
            for method, runs in methods.items():
                if not runs:
                    continue

                if method == "bulk_insert":
                    # Группируем прогоны по batch_size — каждый batch_size = отдельная линия
                    by_batch: dict[int | None, list] = {}
                    for run in runs:
                        by_batch.setdefault(run.batch_size, []).append(run)

                    for batch_size, batch_runs in by_batch.items():
                        series = QLineSeries()
                        series.setName(series_label(db_type, method, batch_runs[0]))
                        for run in sorted(batch_runs, key=lambda r: r.rows):
                            series.append(run.rows, run.elapsed)
                        self._line_chart.addSeries(series)
                        series.attachAxis(axis_x)
                        series.attachAxis(axis_y)
                else:
                    series = QLineSeries()
                    series.setName(f"{db_type} / {method}")
                    for run in sorted(runs, key=lambda r: r.rows):
                        series.append(run.rows, run.elapsed)
                    self._line_chart.addSeries(series)
                    series.attachAxis(axis_x)
                    series.attachAxis(axis_y)

    # ──────────────────────────────────────────────

    def _clear(self):
        self._store.clear()
        self._db_selector.clear()
        self._db_selector.addItem(ALL_DBS)
        self._bar_chart.removeAllSeries()
        self._line_chart.removeAllSeries()
