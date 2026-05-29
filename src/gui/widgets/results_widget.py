import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtGui import QAction

from ..utils.chart_data import ChartStore, MethodRun, add_run, filter_runs
from ..utils.results_storage import (
    clear_results_file,
    default_path,
    get_results_path,
    load_results,
    load_results_from,
    reset_results_path,
    save_results,
    set_results_path,
)
from ..components.bar_chart import BarChartWidget
from ..components.line_chart import LineChartWidget
from ..components.results_table import ResultsTableWidget
from ..components.box_plot import BoxPlotWidget
from ..components.multi_filter_bar import MultiFilterBar, FilterSelection
from .delete_by_params_dialog import DeleteByParamsDialog

VIEWS = ["Bar Chart", "Line Chart", "Box-plot", "Таблица"]

MAX_PATH_LEN_IN_BTN = 32  # длина текста кнопки «Файл: ...»


class ResultsWidget(QGroupBox):
    """Блок с графиками и таблицей"""

    def __init__(self):
        super().__init__("Результаты")

        self._store: ChartStore = load_results()
        self._buffering: bool = False

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

        # Меню «Файл ▾» с операциями над файлом результатов
        self._file_btn = QPushButton()
        self._file_btn.setToolTip("Управление файлом результатов")
        self._file_menu = QMenu(self._file_btn)
        self._file_btn.setMenu(self._file_menu)

        clear_view_btn = QPushButton("Скрыть результаты")
        clear_view_btn.clicked.connect(self._clear_view)

        top_layout = QHBoxLayout()
        top_layout.addLayout(view_btn_layout)
        top_layout.addStretch()
        top_layout.addWidget(clear_view_btn)
        top_layout.addWidget(self._file_btn)

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self._filter)
        layout.addWidget(self._stack)
        self.setLayout(layout)

        self._rebuild_file_menu()
        self._sync_filter_options()
        self._refresh()

    # ────────────── публичные слоты ──────────────

    @pyqtSlot(dict)
    def update_results(self, result: dict):
        run = MethodRun.from_dict(result)
        add_run(self._store, run)
        save_results(self._store)
        if self._buffering:
            # Во время серии не перерисовываем графики — это дорого
            # и подвешивает GUI. Перерисуем один раз в конце сессии.
            return
        self._sync_filter_options()
        self._refresh()

    def start_session(self, _session_id: str = "", _total: int = 0):
        """Начало серии прогонов: буферизуем результаты, не перерисовывая графики."""
        self._buffering = True

    def end_session(self, _session_id: str = ""):
        """Окончание серии (нормальное или по Stop): однократный refresh."""
        self._buffering = False
        self._sync_filter_options()
        self._refresh()

    # ────────────── фильтрация / отрисовка ──────────────

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

    # ────────────── работа с файлом результатов ──────────────

    def _rebuild_file_menu(self) -> None:
        """Перестраивает меню «Файл ▾» и обновляет текст кнопки с текущим путём."""
        path = get_results_path()
        self._file_btn.setText(f"Файл: {self._compact_path(path)} ▾")
        self._file_btn.setToolTip(f"Текущий файл результатов:\n{path}")

        self._file_menu.clear()

        # Информационный пункт (текущий путь)
        info = QAction(f"Текущий путь: {path}", self._file_menu)
        info.setEnabled(False)
        self._file_menu.addAction(info)
        self._file_menu.addSeparator()

        act_open = QAction("Открыть из файла…", self._file_menu)
        act_open.triggered.connect(self._on_open_from)
        self._file_menu.addAction(act_open)

        act_save_as = QAction("Сохранить в другое место…", self._file_menu)
        act_save_as.triggered.connect(self._on_save_as)
        self._file_menu.addAction(act_save_as)

        act_reset = QAction("Восстановить путь по умолчанию", self._file_menu)
        act_reset.triggered.connect(self._on_reset_path)
        self._file_menu.addAction(act_reset)

        self._file_menu.addSeparator()
        act_delete_by = QAction("Удалить записи по параметрам…", self._file_menu)
        act_delete_by.setEnabled(bool(self._store))
        act_delete_by.triggered.connect(self._on_delete_by_params)
        self._file_menu.addAction(act_delete_by)

        act_clear = QAction("Очистить файл результатов", self._file_menu)
        act_clear.triggered.connect(self._on_clear_file)
        self._file_menu.addAction(act_clear)

    def _compact_path(self, path: Path) -> str:
        """Сокращённое представление пути для кнопки."""
        s = str(path)
        if len(s) <= MAX_PATH_LEN_IN_BTN:
            return s
        return "…" + s[-(MAX_PATH_LEN_IN_BTN - 1):]

    def _on_open_from(self):
        """Открыть results.json из другого места. Активный путь переключается на него."""
        current = get_results_path()
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть файл результатов",
            str(current.parent if current.exists() else Path.home()),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path_str:
            return
        new_path = Path(path_str)

        try:
            new_store = load_results_from(new_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка чтения",
                f"Не удалось прочитать файл:\n{new_path}\n\n{e}",
            )
            return

        set_results_path(new_path)
        self._store = new_store
        self._rebuild_file_menu()
        self._sync_filter_options()
        self._refresh()

    def _on_save_as(self):
        """Выбрать новый путь для сохранения. Текущие данные опционально копируются."""
        current = get_results_path()
        default_name = current.name or "results.json"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить файл результатов как…",
            str(
                (current.parent if current.exists() else Path.home()) / default_name
            ),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path_str:
            return
        new_path = Path(path_str)

        copy_existing = False
        if current.exists() and current.resolve() != new_path.resolve():
            reply = QMessageBox.question(
                self,
                "Копирование данных",
                f"Скопировать текущие данные ({len(self._store)} записей) "
                f"в новое местоположение?\n\n"
                f"Из: {current}\n"
                f"В:  {new_path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            copy_existing = reply == QMessageBox.StandardButton.Yes

        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            if copy_existing:
                shutil.copy2(current, new_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка записи",
                f"Не удалось подготовить файл:\n{new_path}\n\n{e}",
            )
            return

        set_results_path(new_path)
        # Если копировали — содержимое уже там, _store не трогаем.
        # Если не копировали — в новой папке создастся пустой/новый файл при
        # следующем save_results(); текущий store остаётся в памяти.
        self._rebuild_file_menu()

    def _on_reset_path(self):
        """Возврат к пути по умолчанию (корень проекта)."""
        default = default_path()
        current = get_results_path()
        if current.resolve() == default.resolve():
            return
        reset_results_path()
        try:
            self._store = load_results()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка чтения",
                f"Не удалось прочитать файл по умолчанию:\n{default}\n\n{e}",
            )
            self._store = []
        self._rebuild_file_menu()
        self._sync_filter_options()
        self._refresh()

    def _on_clear_file(self):
        """Удаляет текущий файл результатов с подтверждением."""
        path = get_results_path()
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить файл результатов?\n\n{path}\n\nЭто действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_results_file()
            self._clear_view()

    def _on_delete_by_params(self):
        """Удаление записей из results.json по параметрам через диалог."""
        if not self._store:
            QMessageBox.information(
                self,
                "Нет данных",
                "В файле результатов нет записей для удаления.",
            )
            return

        dialog = DeleteByParamsDialog(self._store, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        indices = set(dialog.matching_indices())
        if not indices:
            return

        # Применяем удаление: оставляем только те записи, которых нет в indices.
        kept = [r for i, r in enumerate(self._store) if i not in indices]
        n_removed = len(self._store) - len(kept)
        self._store = kept

        try:
            save_results(self._store)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка сохранения",
                f"Не удалось сохранить файл результатов:\n{e}",
            )
            # Перечитываем из файла, чтобы UI отражал реальное состояние диска
            self._store = load_results()
            self._sync_filter_options()
            self._refresh()
            return

        # Перестроим фильтр и графики
        self._sync_filter_options()
        self._refresh()
        self._rebuild_file_menu()

        QMessageBox.information(
            self,
            "Готово",
            f"Удалено записей: {n_removed}.\nОсталось: {len(self._store)}.",
        )
