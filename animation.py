from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from dijkstra import Kind, SearchEvent


class AnimationController(QObject):
    step_shown = pyqtSignal(object)   # SearchEvent
    finished = pyqtSignal(bool)       # True if target was found

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.steps: list[SearchEvent] = []
        self.index = -1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.setInterval(500)

    def load(self, steps: list[SearchEvent]) -> None:
        self.timer.stop()
        self.steps = steps
        self.index = -1

    def clear(self) -> None:
        """Drops the recorded frames, e.g. after the graph was edited."""
        self.load([])

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def set_speed(self, interval_ms: int) -> None:
        self.timer.setInterval(interval_ms)

    def play(self) -> None:
        if self.steps and self.index < len(self.steps) - 1:
            self.timer.start()

    def pause(self) -> None:
        self.timer.stop()

    def is_playing(self) -> bool:
        return self.timer.isActive()

    def step_forward(self) -> None:
        self.advance()

    def step_back(self) -> None:
        if self.index >= 0:
            self.index -= 1
            self.timer.stop()
            self.emit_current()

    def reset(self) -> None:
        self.timer.stop()
        self.index = -1
        self.emit_current()

    def goto(self, index: int) -> None:
        if -1 <= index < len(self.steps):
            self.index = index
            self.timer.stop()
            self.emit_current()

    def advance(self) -> None:
        if self.index >= len(self.steps) - 1:
            self.timer.stop()
            found = bool(self.steps) and self.steps[-1].kind == Kind.FOUND
            self.finished.emit(found)
            return
        self.index += 1
        self.emit_current()

    def emit_current(self) -> None:
        if 0 <= self.index < len(self.steps):
            self.step_shown.emit(self.steps[self.index])
