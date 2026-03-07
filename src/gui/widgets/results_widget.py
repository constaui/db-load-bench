from PyQt6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QLabel,
    QStackedWidget,
    QButtonGroup,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSlot

from ..utils.chart_data import ChartStore, MethodRun, add_run
from ..utils.results_storage import save_results, load_results, clear_results_file
from ..components.bar_chart import BarChartWidget
from ..components.line_chart import LineChartWidget
from ..components.results_table import ResultsTableWidget

VIEWS = ["Bar Chart", "Line Chart", "Таблица"]


class ResultsWidget(QGroupBox):
    """Блок с графиками и таблицей"""

    def __init__(self):
        super().__init__("Результаты")

        self._store: ChartStore = load_results()

        self._bar = BarChartWidget()
        self._line = LineChartWidget()
        self._table = ResultsTableWidget()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._bar)
        self._stack.addWidget(self._line)
        self._stack.addWidget(self._table)

        self._db_selector = QComboBox()
        self._db_selector.addItem("Все СУБД")
        self._db_selector.currentTextChanged.connect(self._refresh)

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
        top_layout.addWidget(QLabel("СУБД:"))
        top_layout.addWidget(self._db_selector)
        top_layout.addStretch()
        top_layout.addLayout(view_btn_layout)
        top_layout.addWidget(clear_view_btn)
        top_layout.addWidget(clear_file_btn)

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self._stack)
        self.setLayout(layout)

        self._restore_selector()
        self._refresh()

    @pyqtSlot(dict)
    def update_results(self, result: dict):
        run = MethodRun.from_dict(result)
        add_run(self._store, run)
        save_results(self._store)
        self._sync_selector(run.db_type)
        self._refresh()

    def _restore_selector(self):
        """Восстанавливает список СУБД из загруженных данных."""
        for run in self._store:
            self._sync_selector(run.db_type)

    def _sync_selector(self, db_type: str):
        items = [
            self._db_selector.itemText(i) for i in range(self._db_selector.count())
        ]
        if db_type not in items:
            self._db_selector.addItem(db_type)

    def _active_store(self) -> ChartStore:
        selected = self._db_selector.currentText()
        if selected == "Все СУБД":
            return self._store
        return [r for r in self._store if r.db_type == selected]

    def _switch_view(self, index: int):
        self._stack.setCurrentIndex(index)
        self._refresh()

    def _refresh(self):
        store = self._active_store()
        index = self._stack.currentIndex()
        widgets = [self._bar, self._line, self._table]
        widgets[index].refresh(store)

    def _clear_view(self):
        """Очищает только отображение — файл не трогает."""
        self._store.clear()
        self._db_selector.clear()
        self._db_selector.addItem("Все СУБД")
        self._bar.clear()
        self._line.clear()
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
