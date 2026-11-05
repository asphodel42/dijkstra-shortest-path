import json
from pathlib import Path

Edge = frozenset  # frozenset({a, b}): the road is two-way, so a-b and b-a are the same edge


class Graph:
    """Undirected weighted graph: cities with map coordinates and roads with lengths in km."""

    def __init__(self) -> None:
        self.nodes: dict[str, tuple[float, float]] = {}  # name -> (latitude, longitude)
        self.adj: dict[str, dict[str, int]] = {}          # name -> {neighbour: km}

    # Vertices

    def add_node(self, name: str, lat: float, lon: float) -> None:
        name = name.strip()
        if not name:
            raise ValueError("порожня назва міста")
        if name in self.nodes:
            raise ValueError(f"місто '{name}' вже є в графі")
        self.nodes[name] = (lat, lon)
        self.adj[name] = {}

    def remove_node(self, name: str) -> None:
        for other in self.adj.pop(name):
            del self.adj[other][name]
        del self.nodes[name]

    def move_node(self, name: str, lat: float, lon: float) -> None:
        self.nodes[name] = (lat, lon)

    # Edges

    def add_edge(self, a: str, b: str, km: int) -> None:
        if a == b:
            raise ValueError("ребро-петля не має сенсу для пошуку шляху")
        if a not in self.nodes or b not in self.nodes:
            raise ValueError("обидва міста мають бути в графі")
        if km <= 0:
            raise ValueError("віддаль має бути додатною (Дейкстра не працює з від'ємними вагами)")
        self.adj[a][b] = self.adj[b][a] = int(km)  # also used to change the length of an existing road

    def remove_edge(self, a: str, b: str) -> None:
        del self.adj[a][b]
        del self.adj[b][a]

    def has_edge(self, a: str, b: str) -> bool:
        return b in self.adj.get(a, {})

    def weight(self, a: str, b: str) -> int:
        return self.adj[a][b]

    def edges(self) -> list[tuple[str, str, int]]:
        """Each road once, as (a, b, km)."""
        seen: set[Edge] = set()
        out = []
        for a, neighbours in self.adj.items():
            for b, km in neighbours.items():
                if Edge((a, b)) not in seen:
                    seen.add(Edge((a, b)))
                    out.append((a, b, km))
        return out

    @property
    def order(self) -> int:
        return len(self.nodes)

    @property
    def size(self) -> int:
        return sum(len(n) for n in self.adj.values()) // 2

    def path_km(self, path: list[str]) -> int:
        return sum(self.adj[a][b] for a, b in zip(path, path[1:]))

    def copy(self) -> "Graph":
        g = Graph()
        g.nodes = dict(self.nodes)
        g.adj = {k: dict(v) for k, v in self.adj.items()}
        return g

    # ---------- files ----------

    def to_json(self, path: str | Path) -> None:
        data = {
            "nodes": [{"name": n, "lat": lat, "lon": lon} for n, (lat, lon) in self.nodes.items()],
            "edges": [{"a": a, "b": b, "km": km} for a, b, km in self.edges()],
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "Graph":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        g = cls()
        for n in data["nodes"]:
            g.add_node(n["name"], float(n["lat"]), float(n["lon"]))
        for e in data["edges"]:
            g.add_edge(e["a"], e["b"], int(e["km"]))
        return g


# Table 1 of the task: 50 roads between 29 cities, km
UKRAINE_ROADS = """
Вінниця Житомир 127; Вінниця Київ 267; Вінниця Кропивницький 320; Вінниця Миколаїв 428; Вінниця Одеса 423;
Вінниця Черкаси 341; Вінниця Чернівці 276; Дніпро Донецьк 248; Дніпро Запоріжжя 85; Дніпро Кропивницький 244;
Дніпро Кривий_Ріг 146; Дніпро Полтава 160; Дніпро Харків 218; Донецьк Луганськ 156; Донецьк Маріуполь 113;
Донецьк Харків 294; Запоріжжя Мелітополь 125; Івано-Франківськ Тернопіль 133; Івано-Франківськ Ужгород 293;
Київ Житомир 140; Київ Полтава 340; Київ Суми 333; Київ Черкаси 189; Київ Чернігів 148; Кропивницький Полтава 246;
Луганськ Харків 325; Львів Івано-Франківськ 134; Львів Луцьк 151; Львів Рівне 211; Львів Тернопіль 127;
Львів Ужгород 268; Львів Чернівці 268; Мелітополь Маріуполь 192; Мелітополь Сімферополь 250; Миколаїв Херсон 69;
Рівне Житомир 188; Рівне Луцьк 73; Рівне Тернопіль 155; Харків Полтава 143; Херсон Мелітополь 231;
Хмельницький Вінниця 119; Хмельницький Житомир 183; Хмельницький Рівне 194; Хмельницький Тернопіль 112;
Хмельницький Чернівці 187; Суми Харків 184; Черкаси Полтава 233; Полтава Суми 175; Чернігів Суми 306;
Сімферополь Севастополь 81
"""

UKRAINE_CITIES = {
    "Ужгород": (48.3, 22.3), "Львів": (49.9, 23.9), "Луцьк": (51.4, 25.0), "Рівне": (51.1, 26.9),
    "Тернопіль": (49.4, 25.8), "Івано-Франківськ": (48.55, 24.1), "Чернівці": (47.4, 26.6),
    "Хмельницький": (49.6, 27.6), "Житомир": (50.6, 28.9), "Вінниця": (48.9, 29.0), "Київ": (50.7, 31.0),
    "Чернігів": (51.9, 31.6), "Черкаси": (49.4, 32.4), "Кропивницький": (48.2, 32.4), "Одеса": (46.2, 30.4),
    "Миколаїв": (46.9, 31.6), "Херсон": (46.3, 33.0), "Кривий Ріг": (47.4, 33.6), "Дніпро": (48.3, 35.2),
    "Запоріжжя": (47.4, 35.7), "Полтава": (49.7, 34.6), "Суми": (51.2, 35.0), "Харків": (50.1, 36.9),
    "Донецьк": (48.0, 38.2), "Луганськ": (48.8, 39.6), "Маріуполь": (46.9, 37.8), "Мелітополь": (46.6, 35.6),
    "Сімферополь": (45.2, 34.2), "Севастополь": (45.0, 32.3),
}


def ukraine() -> Graph:
    g = Graph()
    for name, (lat, lon) in UKRAINE_CITIES.items():
        g.add_node(name, lat, lon)
    for item in UKRAINE_ROADS.split(";"):
        a, b, km = item.split()
        g.add_edge(a.replace("_", " "), b.replace("_", " "), int(km))
    return g


if __name__ == "__main__":
    g = ukraine()
    g.to_json(Path(__file__).parent / "data" / "ukraine.json")
    print("ok", g.order, "міст,", g.size, "доріг")
