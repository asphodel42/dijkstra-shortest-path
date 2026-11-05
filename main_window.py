from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from animation import AnimationController
from dijkstra import ALGORITHMS, Kind, SearchEvent, solve
from graph import Graph, ukraine
from graph_view import CURRENT_COLOR, QUEUED_COLOR, RELAX_COLOR, SETTLED_COLOR, TEXT_COLOR, GraphView, fmt
from results_window import ResultsWindow, RunRecord

DATA_DIR = Path(__file__).parent / "data"
ALPHABET = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
DEFAULT_START, DEFAULT_TARGET = "Львів", "Кропивницький"


def ua_key(name: str) -> list[int]:
    """Ukrainian alphabetical order (plain sorted() puts І, Є, Ї before А)."""
    return [ALPHABET.find(ch) if ch in ALPHABET else ord(ch) for ch in name.lower()]


class RoadDialog(QDialog):
    """Add a road, change its length or delete it, choosing both cities from lists."""

    def __init__(self, graph: Graph, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Дорога між містами")
        self.graph = graph
        names = sorted(graph.nodes, key=ua_key)
        self.a, self.b = QComboBox(), QComboBox()
        self.a.addItems(names)
        self.b.addItems(names)
        if len(names) > 1:
            self.b.setCurrentIndex(1)
        self.km = QSpinBox()
        self.km.setRange(1, 5000)
        self.km.setSuffix(" км")
        self.state = QLabel()
        form = QFormLayout(self)
        form.addRow("Місто A:", self.a)
        form.addRow("Місто B:", self.b)
        form.addRow("Віддаль:", self.km)
        form.addRow(self.state)
        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton("Додати", QDialogButtonBox.ButtonRole.AcceptRole)
        self.delete_button = buttons.addButton("Видалити дорогу", QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton("Закрити", QDialogButtonBox.ButtonRole.RejectRole)
        self.save_button.clicked.connect(self.save)
        self.delete_button.clicked.connect(self.delete)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.a.currentTextChanged.connect(self.refresh)
        self.b.currentTextChanged.connect(self.refresh)
        self.changed = False
        self.refresh()

    def refresh(self) -> None:
        a, b = self.a.currentText(), self.b.currentText()
        exists = a != b and self.graph.has_edge(a, b)
        self.save_button.setText("Змінити віддаль" if exists else "Додати")
        self.delete_button.setEnabled(exists)
        self.save_button.setEnabled(a != b)
        if exists:
            self.km.setValue(self.graph.weight(a, b))
            self.state.setText("Дорога вже є в графі")
        elif a != b:
            self.km.setValue(self.km.minimum())
            self.state.setText("Нова дорога: введіть віддаль")
        else:
            self.state.setText("Виберіть два різні міста")

    def save(self) -> None:
        self.graph.add_edge(self.a.currentText(), self.b.currentText(), self.km.value())
        self.changed = True
        self.refresh()

    def delete(self) -> None:
        self.graph.remove_edge(self.a.currentText(), self.b.currentText())
        self.changed = True
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self, graph: Graph) -> None:
        super().__init__()
        self.setWindowTitle("Пошук найкоротшого шляху за алгоритмом Дейкстри")
        self.resize(1400, 860)
        self.graph = graph

        self.view = GraphView(graph)
        self.view.context_requested.connect(self.on_context)
        self.view.node_clicked.connect(self.finish_connect)
        self.view.edge_double_clicked.connect(self.change_km)
        self.setCentralWidget(self.view)

        self.animation = AnimationController(self)
        self.animation.step_shown.connect(self.on_step)
        self.animation.finished.connect(self.on_finished)
        self.pending_record: RunRecord | None = None

        self.results = ResultsWindow(self)
        self.setStatusBar(QStatusBar())
        self.build_side_panel()
        self.build_labels_panel()
        self.graph_changed()
        self.select_ends(DEFAULT_START, DEFAULT_TARGET)

    # ---------- panels ----------

    def build_side_panel(self) -> None:
        dock = QDockWidget("Керування", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.build_graph_box())
        layout.addWidget(self.build_edit_box())
        layout.addWidget(self.build_search_box())
        layout.addWidget(self.build_playback_box())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setMinimumWidth(280)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def build_graph_box(self) -> QGroupBox:
        box = QGroupBox("Граф")
        layout = QVBoxLayout(box)
        self.info = QLabel()
        layout.addWidget(self.info)
        grid = QGridLayout()
        for i, (text, slot) in enumerate((("Відкрити...", self.load_graph), ("Зберегти...", self.save_graph),
                                          ("Карта України", self.reset_graph), ("Очистити", self.clear_graph))):
            button = QPushButton(text)
            button.clicked.connect(slot)
            grid.addWidget(button, i // 2, i % 2)
        layout.addLayout(grid)
        return box

    def build_edit_box(self) -> QGroupBox:
        box = QGroupBox("Редагування")
        layout = QVBoxLayout(box)
        hint = QLabel("Права кнопка миші на карті: додати місто, з'єднати міста, змінити віддаль, видалити. "
                      "Ліва кнопка: перетягнути місто. Подвійний клік по дорозі: змінити віддаль.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        grid = QGridLayout()
        for i, (text, slot) in enumerate((("Додати місто...", self.add_city_dialog), ("Дорога...", self.road_dialog),
                                          ("Видалити місто...", self.remove_city_dialog))):
            button = QPushButton(text)
            button.clicked.connect(slot)
            grid.addWidget(button, i // 2, i % 2)
        layout.addLayout(grid)
        return box

    def build_search_box(self) -> QGroupBox:
        box = QGroupBox("Пошук")
        layout = QVBoxLayout(box)
        self.start_input, self.target_input = QComboBox(), QComboBox()
        self.algorithm_input = QComboBox()
        for key, (label, _) in ALGORITHMS.items():
            self.algorithm_input.addItem(label, key)
        form = QFormLayout()
        form.addRow("Звідки:", self.start_input)
        form.addRow("Куди:", self.target_input)
        form.addRow("Алгоритм:", self.algorithm_input)
        layout.addLayout(form)
        for combo in (self.start_input, self.target_input, self.algorithm_input):
            combo.currentIndexChanged.connect(self.search_changed)
        swap = QPushButton("Поміняти місцями")
        swap.clicked.connect(lambda: self.select_ends(self.target_input.currentText(), self.start_input.currentText()))
        layout.addWidget(swap)
        labels = QCheckBox("Показувати мітки d на карті")
        labels.setChecked(True)
        labels.toggled.connect(self.view.set_show_labels)
        layout.addWidget(labels)
        run_button = QPushButton("Пошук")
        run_button.clicked.connect(self.run_search)
        layout.addWidget(run_button)
        results_button = QPushButton("Вікно результатів")
        results_button.clicked.connect(lambda: (self.results.show(), self.results.raise_()))
        layout.addWidget(results_button)
        return box

    def build_playback_box(self) -> QGroupBox:
        box = QGroupBox("Програвання")
        layout = QVBoxLayout(box)
        grid = QGridLayout()
        self.play_button = QPushButton("Пуск")
        self.play_button.clicked.connect(self.toggle_play)
        buttons = [(self.play_button, self.toggle_play), (QPushButton("До кінця"), self.skip_to_end),
                   (QPushButton("Крок назад"), self.animation.step_back),
                   (QPushButton("Крок вперед"), self.animation.step_forward),
                   (QPushButton("Скинути"), self.reset_animation)]
        for i, (button, slot) in enumerate(buttons):
            if button is not self.play_button:
                button.clicked.connect(slot)
            grid.addWidget(button, i // 2, i % 2)
        layout.addLayout(grid)
        self.delay_label = QLabel()
        layout.addWidget(self.delay_label)
        self.delay_input = QSlider(Qt.Orientation.Horizontal)
        self.delay_input.setRange(0, 2000)
        self.delay_input.setSingleStep(100)
        self.delay_input.setPageStep(250)
        self.delay_input.valueChanged.connect(self.set_delay)
        self.delay_input.setValue(700)
        layout.addWidget(self.delay_input)
        return box

    def build_labels_panel(self) -> None:
        dock = QDockWidget("Мітки вершин", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.queue_label = QLabel()
        self.queue_label.setWordWrap(True)
        layout.addWidget(self.queue_label)
        self.labels = QTableWidget(0, 4)
        self.labels.setHorizontalHeaderLabels(["Місто", "d", "Попередня", "Мітка"])
        self.labels.verticalHeader().setVisible(False)
        self.labels.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.labels.horizontalHeader().setStretchLastSection(True)
        self.labels.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.labels)
        body.setMinimumWidth(330)
        dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    # ---------- graph editing ----------

    def graph_changed(self) -> None:
        """Any edit makes the recorded search stale, so it is dropped."""
        start, target = self.start_input.currentText(), self.target_input.currentText()
        names = sorted(self.graph.nodes, key=ua_key)
        for combo in (self.start_input, self.target_input):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.blockSignals(False)
        self.select_ends(start or DEFAULT_START, target or DEFAULT_TARGET)
        self.info.setText(f"Вершин (порядок): {self.graph.order}\nРебер (розмір): {self.graph.size}")
        self.view.set_graph(self.graph)
        self.search_changed()

    def search_changed(self) -> None:
        self.animation.clear()
        self.pending_record = None
        self.play_button.setText("Пуск")
        self.view.show_event(None)
        self.view.set_ends(self.start_input.currentText() or None, self.target_input.currentText() or None)
        self.fill_labels(None)
        self.statusBar().showMessage(f"Граф: {self.graph.order} міст, {self.graph.size} доріг. "
                                     f"Маршрут {self.start_input.currentText()} -> {self.target_input.currentText()}")

    def select_ends(self, start: str, target: str) -> None:
        for combo, name in ((self.start_input, start), (self.target_input, target)):
            i = combo.findText(name)
            combo.setCurrentIndex(i if i >= 0 else min(combo.count() - 1, 0 if combo is self.start_input else 1))

    def on_context(self, kind: str, item, pos, geo: tuple[float, float]) -> None:
        menu = QMenu(self)
        if kind == "empty":
            menu.addAction("Додати місто тут...", lambda: self.add_city(*geo))
        elif kind == "node":
            menu.addAction(f"Звідки: {item}", lambda: self.select_ends(item, self.target_input.currentText()))
            menu.addAction(f"Куди: {item}", lambda: self.select_ends(self.start_input.currentText(), item))
            menu.addSeparator()
            menu.addAction("З'єднати дорогою з...", lambda: self.start_connect(item))
            menu.addAction("Видалити місто", lambda: self.remove_city(item))
        else:
            a, b = item
            menu.addAction(f"Змінити віддаль {a} - {b}...", lambda: self.change_km(a, b))
            menu.addAction("Видалити дорогу", lambda: self.remove_road(a, b))
        menu.exec(pos)

    def add_city(self, lat: float, lon: float) -> None:
        name, ok = QInputDialog.getText(self, "Нове місто", "Назва міста:")
        if not ok:
            return
        try:
            self.graph.add_node(name, lat, lon)
        except ValueError as e:
            QMessageBox.warning(self, "Помилка", str(e))
            return
        self.graph_changed()
        self.statusBar().showMessage(f"Додано місто {name.strip()}. З'єднайте його дорогами (права кнопка -> "
                                     f"\"З'єднати дорогою з...\").")

    def add_city_dialog(self) -> None:
        lat0, lat1, lon0, lon1 = self.view.bounds()
        self.add_city(round((lat0 + lat1) / 2, 3), round((lon0 + lon1) / 2, 3))  # centre; drag it into place

    def remove_city(self, name: str) -> None:
        self.graph.remove_node(name)
        self.graph_changed()

    def remove_city_dialog(self) -> None:
        names = sorted(self.graph.nodes, key=ua_key)
        if names:
            name, ok = QInputDialog.getItem(self, "Видалити місто", "Місто (разом з його дорогами):", names, 0, False)
            if ok:
                self.remove_city(name)

    def start_connect(self, name: str) -> None:
        self.view.connect_from = name
        self.statusBar().showMessage(f"Клацніть місто, яке з'єднати з '{name}' (права кнопка - скасувати)")

    def finish_connect(self, other: str) -> None:
        a, self.view.connect_from = self.view.connect_from, None
        if not a or a == other:
            self.view.update()
            return
        default = self.graph.weight(a, other) if self.graph.has_edge(a, other) else 1
        km, ok = QInputDialog.getInt(self, "Нова дорога", f"Віддаль {a} - {other}, км:", default, 1, 5000)
        if ok:
            self.graph.add_edge(a, other, km)
            self.graph_changed()
        self.view.update()

    def change_km(self, a: str, b: str) -> None:
        km, ok = QInputDialog.getInt(self, "Віддаль", f"Віддаль {a} - {b}, км:", self.graph.weight(a, b), 1, 5000)
        if ok:
            self.graph.add_edge(a, b, km)
            self.graph_changed()

    def remove_road(self, a: str, b: str) -> None:
        self.graph.remove_edge(a, b)
        self.graph_changed()

    def road_dialog(self) -> None:
        if self.graph.order < 2:
            return
        dialog = RoadDialog(self.graph, self)
        dialog.exec()
        if dialog.changed:
            self.graph_changed()

    def load_graph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Відкрити граф", str(DATA_DIR), "JSON (*.json)")
        if not path:
            return
        try:
            self.graph = Graph.from_json(path)
        except (OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(self, "Помилка", f"Не вдалося прочитати файл:\n{e}")
            return
        self.graph_changed()

    def save_graph(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти граф", str(DATA_DIR / "graph.json"), "JSON (*.json)")
        if path:
            self.graph.to_json(path)

    def reset_graph(self) -> None:
        self.graph = ukraine()
        self.graph_changed()

    def clear_graph(self) -> None:
        self.graph = Graph()
        self.graph_changed()

    # ---------- search and playback ----------

    def run_search(self) -> None:
        start, target = self.start_input.currentText(), self.target_input.currentText()
        if not start or not target:
            QMessageBox.information(self, "Пошук", "Додайте до графу хоча б одне місто.")
            return
        algorithm = self.algorithm_input.currentData()
        result = solve(self.graph, start, target, algorithm)  # timed without building animation frames
        self.animation.load(list(ALGORITHMS[algorithm][1](self.graph, start, target)))
        legs = [(a, b, self.graph.weight(a, b)) for a, b in zip(result.path, result.path[1:])]
        self.pending_record = RunRecord(f"{self.graph.order} / {self.graph.size}", start, target, result, legs)
        self.animation.play()
        self.play_button.setText("Пауза")

    def unit(self) -> str:
        return "км" if self.algorithm_input.currentData() == "dijkstra" else "доріг"

    def on_step(self, ev: SearchEvent) -> None:
        self.view.show_event(ev)
        self.fill_labels(ev)
        self.statusBar().showMessage(self.describe(ev))

    def describe(self, ev: SearchEvent) -> str:
        u = self.unit()
        if ev.kind == Kind.INIT:
            return f"Ініціалізація: d({self.start_input.currentText()}) = 0, для решти міст d = inf"
        if ev.kind == Kind.DONE:
            return f"Ітерацій {ev.step}: черга порожня - ціль недосяжна з початкової вершини"
        if ev.kind == Kind.FOUND:
            return (f"Ітерація {ev.step}: ціль {ev.path[-1]} отримала постійну мітку - шлях знайдено, "
                    f"{ev.km} км, {len(ev.path) - 1} доріг")
        changes = ", ".join(f"{v} {fmt(old)}->{fmt(new)}" for _, v, old, new in ev.relaxed) or "жодна мітка не зменшилась"
        return f"Ітерація {ev.step}: з черги взято {ev.current} (d = {fmt(ev.dist[ev.current])} {u}); релаксація: {changes}"

    def fill_labels(self, ev: SearchEvent | None) -> None:
        names = sorted(self.graph.nodes, key=ua_key)
        if ev:
            order = {n: i for i, n in enumerate(ev.settled)}
            names.sort(key=lambda n: (0, order[n]) if n in order else (1, ev.dist[n]) if n in ev.dist else (2, 0))
            queue = ", ".join(f"{v}({fmt(d)})" for d, v in ev.queue) or "порожня"
            self.queue_label.setText(f"<b>Черга</b> ({'пріоритетна, за d' if self.unit() == 'км' else 'FIFO'}): {queue}")
        else:
            self.queue_label.setText("<b>Черга</b>: пошук ще не запущено")
        relaxed = {v for _, v, *_ in ev.relaxed} if ev else set()
        self.labels.setRowCount(len(names))
        bold = QFont(self.font())
        bold.setBold(True)
        for row, name in enumerate(names):
            d = ev.dist.get(name, float("inf")) if ev else float("inf")
            if ev and name in ev.settled:
                state, color = f"постійна ({ev.settled.index(name) + 1})", SETTLED_COLOR.lighter(150)
            elif ev and name in ev.dist:
                state, color = "тимчасова", QUEUED_COLOR.lighter(120)
            else:
                state, color = "-", None
            if ev and name == ev.current and ev.kind == Kind.SETTLE:
                color = CURRENT_COLOR.lighter(140)
            prev = ev.prev.get(name, "-") if ev else "-"
            for col, text in enumerate((name, fmt(d), prev, state)):
                item = QTableWidgetItem(text)
                if color:
                    item.setBackground(QBrush(color))
                    item.setForeground(QBrush(TEXT_COLOR))  # light fills need dark text in the dark theme too
                if name in relaxed and col in (1, 2):
                    item.setForeground(QBrush(RELAX_COLOR))
                    item.setFont(bold)
                self.labels.setItem(row, col, item)

    def on_finished(self, _found: bool) -> None:
        self.play_button.setText("Пуск")
        if self.pending_record:
            self.results.add(self.pending_record)
            self.pending_record = None

    def toggle_play(self) -> None:
        if self.animation.is_playing():
            self.animation.pause()
            self.play_button.setText("Пуск")
        elif self.animation.total_steps:
            if self.animation.index >= self.animation.total_steps - 1:
                self.animation.reset()
            self.animation.play()
            self.play_button.setText("Пауза")
        else:
            self.run_search()

    def skip_to_end(self) -> None:
        if self.animation.total_steps:
            self.animation.goto(self.animation.total_steps - 1)
            self.animation.advance()  # past the last frame -> emits finished

    def reset_animation(self) -> None:
        self.animation.reset()
        self.view.show_event(None)
        self.fill_labels(None)
        self.play_button.setText("Пуск")

    def set_delay(self, ms: int) -> None:
        self.animation.set_speed(ms)
        self.delay_label.setText(f"Затримка між ітераціями: {ms} мс")
