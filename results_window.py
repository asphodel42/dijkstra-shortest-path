import csv
from dataclasses import dataclass, field
from datetime import datetime

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt

from dijkstra import ALGORITHMS, SearchResult

COLUMNS = ["Час", "Алгоритм", "Граф (V / E)", "Старт", "Ціль", "Знайдено", "Віддаль, км", "Міст", "Доріг",
           "Ітерацій", "Релаксацій", "Перевірено ребер", "Час пошуку, мс"]
LEG_COLUMNS = ["N", "Звідки", "Куди", "Км", "Від старту, км"]


@dataclass
class RunRecord:
    graph: str           # "29 / 50"
    start: str
    target: str
    result: SearchResult
    legs: list[tuple[str, str, int]]  # roads of the path with their km, fixed at run time
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    @property
    def algorithm(self) -> str:
        return ALGORITHMS[self.result.algorithm][0]

    def values(self) -> list[str]:
        r = self.result
        return [
            self.timestamp, self.algorithm, self.graph, self.start, self.target,
            "так" if r.found else "ні",
            str(r.km) if r.found else "-",
            str(len(r.path)) if r.found else "-",
            str(r.roads) if r.found else "-",
            str(r.iterations), str(r.relaxations), str(r.checks),
            f"{r.seconds * 1000:.3f}",
        ]

    def path_label(self) -> str:
        return " -> ".join(self.result.path) if self.result.found else "шлях не знайдено"


class ResultsWindow(QDialog):
    """Separate window: the found route (cities + km) and the history of runs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Найкоротший шлях")
        self.resize(1100, 640)
        self.records: list[RunRecord] = []
        layout = QVBoxLayout(self)

        route_box = QGroupBox("Маршрут")
        route_layout = QVBoxLayout(route_box)
        self.title = QLabel("Пошук ще не виконувався")
        self.path_text = QLabel()
        self.path_text.setWordWrap(True)
        self.path_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        big = QFont(self.font())
        big.setPointSizeF(big.pointSizeF() * 1.35)
        self.path_text.setFont(big)
        self.distance = QLabel()
        bold = QFont(big)
        bold.setBold(True)
        self.distance.setFont(bold)
        self.legs = QTableWidget(0, len(LEG_COLUMNS))
        self.legs.setHorizontalHeaderLabels(LEG_COLUMNS)
        self.legs.verticalHeader().setVisible(False)
        self.legs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.legs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for w in (self.title, self.path_text, self.distance, self.legs):
            route_layout.addWidget(w)

        history_box = QGroupBox("Історія запусків (виберіть рядок, щоб побачити маршрут)")
        history_layout = QVBoxLayout(history_box)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.currentCellChanged.connect(lambda row, *_: self.show_route(row))
        history_layout.addWidget(self.table)
        export_button = QPushButton("Експорт CSV...")
        export_button.clicked.connect(self.export_csv)
        history_layout.addWidget(export_button)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(route_box)
        splitter.addWidget(history_box)
        splitter.setSizes([360, 260])
        layout.addWidget(splitter)

    def add(self, record: RunRecord) -> None:
        self.records.append(record)
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, value in enumerate(record.values()):
            self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.setCurrentCell(row, 0)
        self.show_route(row)
        self.show()
        self.raise_()

    def clear(self) -> None:
        self.records.clear()
        self.table.setRowCount(0)

    def show_route(self, row: int) -> None:
        if not 0 <= row < len(self.records):
            return
        rec = self.records[row]
        r = rec.result
        self.title.setText(f"{rec.algorithm}: {rec.start} -> {rec.target} (запуск {rec.timestamp}, граф {rec.graph})")
        self.path_text.setText(rec.path_label())
        self.distance.setText(f"Віддаль: {r.km} км, міст на шляху: {len(r.path)}, доріг: {r.roads}"
                              if r.found else "Ціль недосяжна з початкової вершини")
        self.legs.setRowCount(len(rec.legs))
        total = 0
        for i, (a, b, km) in enumerate(rec.legs):
            total += km
            for col, value in enumerate((i + 1, a, b, km, total)):
                item = QTableWidgetItem(str(value))
                if col in (0, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.legs.setItem(i, col, item)

    def export_csv(self) -> None:
        if not self.records:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Експорт результатів", "dijkstra_log.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads Cyrillic
            writer = csv.writer(f)
            writer.writerow(COLUMNS + ["Шлях"])
            for r in self.records:
                writer.writerow(r.values() + [r.path_label()])
