from PyQt6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QButtonGroup,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSlot

from ..utils.chart_data import ChartStore, MethodRun, add_run, filter_runs
from ..utils.results_storage import save_results, load_results, clear_results_file
from ..components.bar_chart import BarChartWidget
from ..components.line_chart import LineChartWidget
from ..components.results_table import ResultsTableWidget
from ..components.box_plot import BoxPlotWidget
from ..components.multi_filter_bar import MultiFilterBar, FilterSelection

VIEWS = ["Bar Chart", "Line Chart", "Box plot", "Таблица"]


class ResultsWidget(QGroupBox):
    """Блок с графиками и таблицей"""

    def __init__(self):
        super().__init__("Результаты")

        self._store: ChartStore = load_results()

        self._bar = BarChartWidget()
        self._line = LineChartWidget()
        self._box = BoxPlotWidget()
        self._table = ResultsTableWidget()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._bar)
        self._stack.addWidget(self._line)
        self._stack.addWidget(self._box)
        self._stack.addWidget(self._table)

        self._filter = MultiFilterBar()
        self._filter.changed.connect(self._on_filter_changed)

        self._view_group = QButtonGroup()
        view_btn_layout = QHBoxLayout()
        for i, label in enumerate(VIEWS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda _, idx=i: self._switch_view(idx))
            self._view_group.addButton(btn, i)
            view_btn_layout.addWidget(btn)

        clear_view_btn = QPushButton("Скрыть результаты")
        clear_file_btn = QPushButton("Очистить файл результатов")
        clear_view_btn.clicked.connect(self._clear_view)
        clear_file_btn.clicked.connect(self._clear_file)

        top_layout = QHBoxLayout()
        top_layout.addLayout(view_btn_layout)
        top_layout.addStretch()
        top_layout.addWidget(clear_view_btn)
        top_layout.addWidget(clear_file_btn)

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self._filter)
        layout.addWidget(self._stack)
        self.setLayout(layout)

        self._sync_filter_options()
        self._refresh()

    @pyqtSlot(dict)
    def update_results(self, result: dict):
        run = MethodRun.from_dict(result)
        add_run(self._store, run)
        save_results(self._store)
        self._sync_filter_options()
        self._refresh()

    def _sync_filter_options(self) -> None:
        """Обновляет списки доступных значений в фильтре по текущему стору."""
        engines = sorted({r.engine for r in self._store})
        db_types = sorted({r.db_type for r in self._store})
        methods_order = ["default_insert", "bulk_insert", "file_insert"]
        present = {r.method for r in self._store}
        methods = [m for m in methods_order if m in present] + sorted(
            present - set(methods_order)
        )
        self._filter.set_options(engines, db_types, methods)

    def _active_store(self) -> ChartStore:
        sel: FilterSelection = self._filter.selection()
        return filter_runs(
            self._store,
            engines=sel.engines,
            db_types=sel.db_types,
            methods=sel.methods,
        )

    def _switch_view(self, index: int):
        self._stack.setCurrentIndex(index)
        self._refresh()

    def _on_filter_changed(self, _selection: FilterSelection) -> None:
        self._refresh()

    def _refresh(self):
        store = self._active_store()
        index = self._stack.currentIndex()
        widgets = [self._bar, self._line, self._box, self._table]
        widgets[index].refresh(store)

    def _clear_view(self):
        """Очищает только отображение — файл не трогает."""
        self._store.clear()
        self._sync_filter_options()
        self._bar.clear()
        self._line.clear()
        self._box.clear()
        self._table.clear()

    def _clear_file(self):
        """Удаляет файл результатов с подтверждением."""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Удалить файл результатов? Это действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_results_file()
            self._clear_view()
