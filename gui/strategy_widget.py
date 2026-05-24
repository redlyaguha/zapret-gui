from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QLabel, QTextEdit, QSplitter
)
from PySide6.QtCore import Qt
from core.strategy_parser import find_strategies, parse_strategy


class StrategyWidget(QWidget):
    def __init__(self, zapret_manager, log_widget, parent=None):
        super().__init__(parent)
        self.zm = zapret_manager
        self.log = log_widget
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Available Strategies")
        header.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_refresh)
        left_layout.addLayout(btn_layout)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Arguments:"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setStyleSheet("font-family: Consolas; font-size: 11px;")
        right_layout.addWidget(self.details)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def refresh(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self.strategies = find_strategies(self.zm.zapret_path)
        for s in self.strategies:
            self.list_widget.addItem(s.stem)
        self.list_widget.blockSignals(False)
        if self.strategies:
            self.list_widget.setCurrentRow(0)
        self._update_status()

    def _on_select(self, idx: int):
        if 0 <= idx < len(self.strategies):
            info = parse_strategy(self.strategies[idx])
            args_text = "\n".join(info["args"]) if info["args"] else "No arguments found"
            self.details.setPlainText(args_text)

    def _start(self):
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.strategies):
            bat = self.strategies[idx]
            self.zm.start_strategy(bat)
            self.log.log(f"Started strategy: {bat.stem}", "system")
            self._update_status()

    def _stop(self):
        self.zm.stop()
        self.log.log("Stopped winws.exe", "system")
        self._update_status()

    def _update_status(self):
        running = self.zm.is_running()
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
