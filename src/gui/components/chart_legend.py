from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from PyQt6.QtCharts import QChart


class ChartLegend(QScrollArea):
    """Легенда диаграммы со скроллом"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(2)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.setWidget(self._container)

    def rebuild(self, chart: QChart):
        """Обновление легенды диаграммы"""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for series in chart.series():
            for marker in chart.legend().markers(series):
                color = marker.brush().color()
                label = marker.label()
                self._layout.addWidget(_LegendItem(label, color))

        self._layout.addStretch()


class _LegendItem(QWidget):
    """Элемент легенды диаграммы"""

    def __init__(self, label: str, color: QColor, parent=None):
        super().__init__(parent)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color.name()}; font-size: 14px;")
        dot.setFixedWidth(16)

        text = QLabel(label)
        text.setWordWrap(True)  # перенос длинных названий

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 8, 2)
        layout.setSpacing(4)
        layout.addWidget(dot)
        layout.addWidget(text, stretch=1)
        self.setLayout(layout)
