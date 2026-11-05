"""Dijkstra's shortest path search and plain breadth-first search for comparison.

Both are generators of SearchEvent so the GUI can replay every iteration; solve() runs them
without intermediate snapshots and measures the time.
"""
import heapq
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from graph import Graph

INF = float("inf")


class Kind(Enum):
    INIT = "init"       # start labelled 0, nothing settled yet
    SETTLE = "settle"   # one vertex took a permanent label and relaxed its roads
    FOUND = "found"     # the target got a permanent label
    DONE = "done"       # queue empty, target unreachable


@dataclass
class SearchEvent:
    kind: Kind
    step: int                                   # iteration number (vertices taken from the queue)
    current: str | None                         # vertex taken from the queue on this step
    dist: dict[str, float]                      # temporary + permanent labels (km, or roads for BFS)
    prev: dict[str, str]                        # previous vertex on the best known route
    settled: list[str]                          # permanent labels, in the order they were fixed
    queue: list[tuple[float, str]]              # open vertices with their labels (heap: smallest first)
    relaxed: list[tuple[str, str, float, float]] = field(default_factory=list)  # (u, v, old, new)
    path: list[str] = field(default_factory=list)
    km: int = 0
    relaxations: int = 0                        # successful label decreases so far
    checks: int = 0                             # roads examined so far


@dataclass
class SearchResult:
    algorithm: str
    found: bool
    path: list[str]
    km: int
    iterations: int
    relaxations: int
    checks: int
    seconds: float = 0.0

    @property
    def roads(self) -> int:
        return len(self.path) - 1 if self.found else 0


def backtrace(prev: dict[str, str], start: str, target: str) -> list[str]:
    path = [target]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1]


class Recorder:
    """Builds events from the live search state; skips intermediate ones when timing."""

    def __init__(self, graph: Graph, snapshots: bool) -> None:
        self.graph, self.snapshots = graph, snapshots
        self.dist: dict[str, float] = {}
        self.prev: dict[str, str] = {}
        self.settled: list[str] = []
        self.step = self.relaxations = self.checks = 0

    def event(self, kind: Kind, current=None, queue=(), relaxed=(), path=()) -> SearchEvent | None:
        final = kind in (Kind.FOUND, Kind.DONE)
        if not (self.snapshots or final):
            return None
        path = list(path)
        return SearchEvent(kind, self.step, current, dict(self.dist), dict(self.prev), list(self.settled),
                           list(queue), list(relaxed), path, self.graph.path_km(path),
                           self.relaxations, self.checks)


def dijkstra_search(graph: Graph, start: str, target: str, snapshots: bool = True):
    """Yields INIT, then one SETTLE per permanent label, then FOUND or DONE.

    Modified breadth-first search: the FIFO queue becomes a priority queue ordered by the
    accumulated distance d; a label stays temporary (can still decrease) until its vertex is
    the minimum of the queue, and only then becomes permanent.
    """
    r = Recorder(graph, snapshots)
    dist, prev = r.dist, r.prev
    dist[start] = 0
    done: set[str] = set()
    heap = [(0, start)]

    def live_queue():
        return sorted((d, v) for d, v in heap if v not in done and dist[v] == d)

    if ev := r.event(Kind.INIT, queue=live_queue()):
        yield ev
    while heap:
        d, u = heapq.heappop(heap)
        if u in done:  # stale entry: u was pushed again later with a smaller label
            continue
        r.step += 1
        done.add(u)
        r.settled.append(u)
        if u == target:
            yield r.event(Kind.FOUND, u, path=backtrace(prev, start, target))
            return
        relaxed = []
        for v, w in graph.adj[u].items():
            if v in done:
                continue
            r.checks += 1
            if d + w < dist.get(v, INF):  # relaxation: a shorter route to v goes through u
                relaxed.append((u, v, dist.get(v, INF), d + w))
                dist[v] = d + w
                prev[v] = u
                r.relaxations += 1
                heapq.heappush(heap, (d + w, v))  # lazy deletion: heapq has no decrease-key
        if ev := r.event(Kind.SETTLE, u, live_queue(), relaxed):
            yield ev
    yield r.event(Kind.DONE)


def bfs_search(graph: Graph, start: str, target: str, snapshots: bool = True):
    """Breadth-first search: FIFO queue, a vertex is final the first time it is reached.

    Labels count roads, not km, so the route has the fewest roads but not always the fewest km.
    """
    r = Recorder(graph, snapshots)
    dist, prev = r.dist, r.prev
    dist[start] = 0
    fifo = deque([start])

    def queue():
        return [(dist[v], v) for v in fifo]

    if ev := r.event(Kind.INIT, queue=queue()):
        yield ev
    if start == target:
        yield r.event(Kind.FOUND, start, path=[start])
        return
    while fifo:
        u = fifo.popleft()
        r.step += 1
        r.settled.append(u)
        relaxed = []
        for v in graph.adj[u]:
            r.checks += 1
            if v not in dist:  # the first visit fixes the label
                dist[v] = dist[u] + 1
                prev[v] = u
                r.relaxations += 1
                relaxed.append((u, v, INF, dist[v]))
                if v == target:
                    yield r.event(Kind.FOUND, u, queue(), relaxed, backtrace(prev, start, target))
                    return
                fifo.append(v)
        if ev := r.event(Kind.SETTLE, u, queue(), relaxed):
            yield ev
    yield r.event(Kind.DONE)


ALGORITHMS = {"dijkstra": ("Дейкстра", dijkstra_search), "bfs": ("Пошук в ширину", bfs_search)}


def solve(graph: Graph, start: str, target: str, algorithm: str = "dijkstra") -> SearchResult:
    search = ALGORITHMS[algorithm][1]
    t0 = time.perf_counter()
    *_, last = search(graph, start, target, snapshots=False)
    seconds = time.perf_counter() - t0
    return SearchResult(algorithm, last.kind == Kind.FOUND, last.path, last.km, last.step,
                        last.relaxations, last.checks, seconds)
