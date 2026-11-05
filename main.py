from pathlib import Path

from PyQt6.QtWidgets import QApplication

from graph import Graph, ukraine
from main_window import MainWindow

DEFAULT_GRAPH_PATH = Path(__file__).parent / "data" / "ukraine.json"


def main() -> None:
    app = QApplication([])
    graph = Graph.from_json(DEFAULT_GRAPH_PATH) if DEFAULT_GRAPH_PATH.exists() else ukraine()
    window = MainWindow(graph)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
