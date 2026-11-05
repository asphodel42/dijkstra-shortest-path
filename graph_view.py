import math

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from dijkstra import Kind, SearchEvent
from graph import Graph

EDGE_COLOR = QColor("#b0bec5")
TREE_COLOR = QColor("#81c784")       # prev[] edge of a permanent label
TEMP_TREE_COLOR = QColor("#ffb74d")  # prev[] edge of a temporary label
RELAX_COLOR = QColor("#e65100")      # edges relaxed on the current step
PATH_COLOR = QColor("#1e88e5")
NODE_COLOR = QColor("#ffffff")
QUEUED_COLOR = QColor("#fff176")
SETTLED_COLOR = QColor("#66bb6a")
CURRENT_COLOR = QColor("#ff9800")
START_COLOR = QColor("#2e7d32")
TARGET_COLOR = QColor("#c62828")
TEXT_COLOR = QColor("#263238")

# map frame that is always visible, so adding a city does not rescale everything (lat, lon)
UKRAINE_BOX = (44.4, 52.2, 22.0, 41.2)
COS_LAT = math.cos(math.radians(48.5))  # equirectangular projection around the middle of Ukraine
MARGIN = 45
NODE_R = 8


def fmt(d: float) -> str:
    return "inf" if d == math.inf else f"{d:g}"


class GraphView(QWidget):
    """Draws the cities at their map coordinates, the roads with km and the state of the search."""

    node_clicked = pyqtSignal(str)
    node_moved = pyqtSignal(str)
    edge_double_clicked = pyqtSignal(str, str)
    context_requested = pyqtSignal(str, object, QPoint, tuple)  # kind ("node"/"edge"/"empty"), item, global pos, (lat, lon)

    def __init__(self, graph: Graph, parent=None) -> None:
        super().__init__(parent)
        self.graph = graph
        self.event: SearchEvent | None = None
        self.start: str | None = None
        self.target: str | None = None
        self.show_labels = True
        self.connect_from: str | None = None  # pending "connect with..." from the context menu
        self.dragging: str | None = None
        self.mouse = QPointF()
        self.setMouseTracking(True)
        self.setMinimumSize(500, 400)

    def set_graph(self, graph: Graph) -> None:
        self.graph = graph
        self.event = None
        self.update()

    def show_event(self, event: SearchEvent | None) -> None:
        self.event = event
        self.update()

    def set_ends(self, start: str | None, target: str | None) -> None:
        self.start, self.target = start, target
        self.update()

    def set_show_labels(self, on: bool) -> None:
        self.show_labels = on
        self.update()

    # ---------- projection ----------

    def bounds(self) -> tuple[float, float, float, float]:
        lat0, lat1, lon0, lon1 = UKRAINE_BOX
        for lat, lon in self.graph.nodes.values():
            lat0, lat1, lon0, lon1 = min(lat0, lat), max(lat1, lat), min(lon0, lon), max(lon1, lon)
        return lat0, lat1, lon0, lon1

    def transform(self) -> tuple[float, float, float]:
        """(scale, x offset, y offset): x = ox + scale * lon * cos, y = oy - scale * lat."""
        lat0, lat1, lon0, lon1 = self.bounds()
        w, h = (lon1 - lon0) * COS_LAT, lat1 - lat0
        scale = min((self.width() - 2 * MARGIN) / w, (self.height() - 2 * MARGIN) / h)
        ox = (self.width() - w * scale) / 2 - lon0 * COS_LAT * scale
        oy = (self.height() + h * scale) / 2 + lat0 * scale
        return scale, ox, oy

    def to_screen(self, name: str) -> QPointF:
        lat, lon = self.graph.nodes[name]
        s, ox, oy = self.transform()
        return QPointF(ox + s * lon * COS_LAT, oy - s * lat)

    def to_geo(self, p: QPointF) -> tuple[float, float]:
        s, ox, oy = self.transform()
        return round((oy - p.y()) / s, 3), round((p.x() - ox) / (s * COS_LAT), 3)

    # ---------- hit testing ----------

    def node_at(self, p: QPointF) -> str | None:
        best, best_d = None, NODE_R + 6
        for name in self.graph.nodes:
            d = math.dist((p.x(), p.y()), (self.to_screen(name).x(), self.to_screen(name).y()))
            if d < best_d:
                best, best_d = name, d
        return best

    def edge_at(self, p: QPointF) -> tuple[str, str] | None:
        for a, b, _ in self.graph.edges():
            pa, pb = self.to_screen(a), self.to_screen(b)
            dx, dy = pb.x() - pa.x(), pb.y() - pa.y()
            length2 = dx * dx + dy * dy or 1
            t = max(0.0, min(1.0, ((p.x() - pa.x()) * dx + (p.y() - pa.y()) * dy) / length2))
            if math.dist((p.x(), p.y()), (pa.x() + t * dx, pa.y() + t * dy)) < 6:
                return a, b
        return None

    # ---------- mouse ----------

    def mousePressEvent(self, e) -> None:
        p = e.position()
        node = self.node_at(p)
        if e.button() == Qt.MouseButton.RightButton:
            if self.connect_from:
                self.connect_from = None
                self.update()
                return
            if node:
                self.context_requested.emit("node", node, e.globalPosition().toPoint(), self.to_geo(p))
            elif edge := self.edge_at(p):
                self.context_requested.emit("edge", edge, e.globalPosition().toPoint(), self.to_geo(p))
            else:
                self.context_requested.emit("empty", None, e.globalPosition().toPoint(), self.to_geo(p))
        elif e.button() == Qt.MouseButton.LeftButton and node:
            if self.connect_from:
                self.node_clicked.emit(node)
            else:
                self.dragging = node

    def mouseMoveEvent(self, e) -> None:
        self.mouse = e.position()
        if self.dragging:
            self.graph.move_node(self.dragging, *self.to_geo(e.position()))
            self.update()
        elif self.connect_from:
            self.update()
        name = self.node_at(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if name else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, _) -> None:
        if self.dragging:
            self.node_moved.emit(self.dragging)
            self.dragging = None

    def mouseDoubleClickEvent(self, e) -> None:
        if not self.node_at(e.position()) and (edge := self.edge_at(e.position())):
            self.edge_double_clicked.emit(*edge)

    # ---------- painting ----------

    def edge_style(self, a: str, b: str) -> tuple[QColor, float, Qt.PenStyle]:
        ev = self.event
        if ev:
            on_path = any({a, b} == {x, y} for x, y in zip(ev.path, ev.path[1:]))
            if on_path:
                return PATH_COLOR, 5, Qt.PenStyle.SolidLine
            if any({a, b} == {u, v} for u, v, *_ in ev.relaxed):
                return RELAX_COLOR, 3.5, Qt.PenStyle.SolidLine
            for v, u in ((a, b), (b, a)):
                if ev.prev.get(v) == u:
                    if v in ev.settled:
                        return TREE_COLOR, 3.5, Qt.PenStyle.SolidLine
                    return TEMP_TREE_COLOR, 2.5, Qt.PenStyle.DashLine
        return EDGE_COLOR, 2, Qt.PenStyle.SolidLine

    def node_fill(self, name: str) -> QColor:
        ev = self.event
        if not ev:
            return NODE_COLOR
        if name == ev.current and ev.kind != Kind.FOUND:
            return CURRENT_COLOR
        if name in ev.path:
            return PATH_COLOR.lighter(150)
        if name in ev.settled:
            return SETTLED_COLOR
        if name in ev.dist:
            return QUEUED_COLOR
        return NODE_COLOR

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#fafafa"))
        small = QFont(self.font())
        small.setPointSizeF(8)
        name_font = QFont(self.font())
        name_font.setPointSizeF(9)
        name_font.setBold(True)

        # roads, then their km on top, so labels are not crossed by other roads
        edges = self.graph.edges()
        for a, b, _ in edges:
            color, width, style = self.edge_style(a, b)
            p.setPen(QPen(color, width, style, Qt.PenCapStyle.RoundCap))
            p.drawLine(self.to_screen(a), self.to_screen(b))
        p.setFont(small)
        fm = QFontMetricsF(small)
        for a, b, km in edges:
            mid = (self.to_screen(a) + self.to_screen(b)) / 2
            text = str(km)
            r = QRectF(0, 0, fm.horizontalAdvance(text) + 6, fm.height() + 1)
            r.moveCenter(mid)
            color = self.edge_style(a, b)[0]
            p.setPen(QPen(color.darker(130) if color != EDGE_COLOR else QColor("#78909c"), 1))
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawRoundedRect(r, 3, 3)
            p.setPen(TEXT_COLOR)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

        if self.connect_from and self.connect_from in self.graph.nodes:
            p.setPen(QPen(RELAX_COLOR, 2, Qt.PenStyle.DashLine))
            p.drawLine(self.to_screen(self.connect_from), self.mouse)

        # cities
        ev = self.event
        for name in self.graph.nodes:
            c = self.to_screen(name)
            border, width = QColor("#455a64"), 1.5
            if name == self.start:
                border, width = START_COLOR, 3.5
            elif name == self.target:
                border, width = TARGET_COLOR, 3.5
            radius = NODE_R + (2 if ev and name == ev.current else 0)
            p.setPen(QPen(border, width))
            p.setBrush(self.node_fill(name))
            p.drawEllipse(c, radius, radius)
            self.draw_name(p, name_font, c, radius, name)
            if ev and self.show_labels and name in ev.dist:
                self.draw_label(p, small, c, radius, name)
        self.draw_legend(p, small)

    @staticmethod
    def draw_name(p: QPainter, font: QFont, c: QPointF, radius: float, name: str) -> None:
        """Name centred above the city, with a white halo so roads under it do not hide it."""
        fm = QFontMetricsF(font)
        path = QPainterPath()
        path.addText(QPointF(c.x() - fm.horizontalAdvance(name) / 2, c.y() - radius - 4), font, name)
        p.setPen(QPen(QColor(255, 255, 255, 235), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(TEXT_COLOR)
        p.drawPath(path)

    def draw_label(self, p: QPainter, font: QFont, c: QPointF, radius: float, name: str) -> None:
        ev = self.event
        text = fmt(ev.dist[name])
        if ev.kind != Kind.INIT and name in ev.settled:
            text += " *"
        fm = QFontMetricsF(font)
        r = QRectF(0, 0, fm.horizontalAdvance(text) + 8, fm.height() + 1)
        r.moveCenter(QPointF(c.x(), c.y() + radius + 4 + r.height() / 2))  # under the city
        p.setFont(font)
        p.setPen(QPen(QColor("#616161"), 1))
        p.setBrush(SETTLED_COLOR.lighter(140) if name in ev.settled else QUEUED_COLOR.lighter(115))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(TEXT_COLOR)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def draw_legend(self, p: QPainter, font: QFont) -> None:
        items = [
            (NODE_COLOR, "не досягнута"), (QUEUED_COLOR, "тимчасова мітка"), (SETTLED_COLOR, "постійна мітка"),
            (CURRENT_COLOR, "поточна вершина"), (PATH_COLOR.lighter(150), "найкоротший шлях"),
        ]
        lines = [(TREE_COLOR, "дерево шляхів"), (RELAX_COLOR, "релаксація"), (PATH_COLOR, "шлях")]
        p.setFont(font)
        fm = QFontMetricsF(font)
        row = fm.height() + 4
        x0, y0 = 10, self.height() - 10 - row * (len(items) + len(lines) + 1)
        box = QRectF(x0 - 4, y0 - 4, 150, row * (len(items) + len(lines) + 1) + 6)
        p.setPen(QPen(QColor("#cfd8dc"), 1))
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRoundedRect(box, 4, 4)
        y = y0 + row / 2
        for color, text in [(None, "")] + items:
            if color is None:  # start/target rings first
                p.setBrush(NODE_COLOR)
                p.setPen(QPen(START_COLOR, 3))
                p.drawEllipse(QPointF(x0 + 7, y), 5.5, 5.5)
                p.setPen(QPen(TARGET_COLOR, 3))
                p.drawEllipse(QPointF(x0 + 22, y), 5.5, 5.5)
                p.setPen(TEXT_COLOR)
                p.drawText(QPointF(x0 + 34, y + fm.ascent() / 2 - 1), "старт / ціль")
            else:
                p.setPen(QPen(QColor("#455a64"), 1))
                p.setBrush(color)
                p.drawEllipse(QPointF(x0 + 7, y), 5.5, 5.5)
                p.setPen(TEXT_COLOR)
                p.drawText(QPointF(x0 + 20, y + fm.ascent() / 2 - 1), text)
            y += row
        for color, text in lines:
            p.setPen(QPen(color, 3.5))
            p.drawLine(QPointF(x0, y), QPointF(x0 + 14, y))
            p.setPen(TEXT_COLOR)
            p.drawText(QPointF(x0 + 20, y + fm.ascent() / 2 - 1), text)
            y += row
