from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QLabel, QTextEdit, QSplitter, QComboBox, QGroupBox, QCheckBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from core.strategy_parser import find_strategies, parse_strategy

POLL_INTERVAL_MS = 1500
POLL_MAX_ATTEMPTS = 15


class StrategyWidget(QWidget):
    def __init__(self, zapret_manager, service_controller, log_widget, parent=None):
        super().__init__(parent)
        self.zm = zapret_manager
        self.sc = service_controller
        self.log = log_widget
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._on_poll_tick)
        self._poll_attempts = 0
        self._poll_target = None  # "start" or "stop"
        self._state = "idle"  # idle | starting | stopping | error
        self._pending_strategy_name = None
        self._last_error = None
        self._build_ui()
        self.refresh()
        self._auto_set_mode()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("Available Strategies")
        header.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Run mode:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Run as process", "Install as service"])
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_change)
        mode_row.addWidget(self.cmb_mode, 1)
        layout.addLayout(mode_row)

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

        self.lbl_running = QLabel("")
        self.lbl_running.setStyleSheet("font-weight: bold; color: #2a6; padding: 4px;")
        left_layout.addWidget(self.lbl_running)

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

        filter_group = QGroupBox("Filters")
        flt = QVBoxLayout(filter_group)

        self.lbl_game = QLabel("Game Filter: —")
        self.cmb_game = QComboBox()
        self.cmb_game.addItems(["disabled", "all", "tcp", "udp"])
        self.cmb_game.currentTextChanged.connect(self._set_game)
        game_row = QHBoxLayout()
        game_row.addWidget(self.lbl_game, 1)
        game_row.addWidget(self.cmb_game)
        flt.addLayout(game_row)

        self.lbl_ipset = QLabel("IPSet Filter: —")
        self.cmb_ipset = QComboBox()
        self.cmb_ipset.addItems(["loaded", "none", "any"])
        self.cmb_ipset.currentTextChanged.connect(self._set_ipset)
        ipset_row = QHBoxLayout()
        ipset_row.addWidget(self.lbl_ipset, 1)
        ipset_row.addWidget(self.cmb_ipset)
        flt.addLayout(ipset_row)

        self.chk_autoupdate = QCheckBox("Auto-Update Check")
        self.chk_autoupdate.toggled.connect(self._toggle_autoupdate)
        flt.addWidget(self.chk_autoupdate)

        layout.addWidget(filter_group)

    def _on_mode_change(self, idx: int):
        self.zm.is_service_mode = (idx == 1)

    def refresh(self):
        self._state = "idle"
        self._last_error = None
        self._pending_strategy_name = None
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self.strategies = find_strategies(self.zm.zapret_path)
        for s in self.strategies:
            self.list_widget.addItem(s.stem)
        self.list_widget.blockSignals(False)
        if self.strategies:
            self.list_widget.setCurrentRow(0)
        self._refresh_filters()
        self._update_status(auto_detect=True)

    def _auto_set_mode(self):
        if self.zm._is_service_running():
            self.cmb_mode.setCurrentIndex(1)

    def _refresh_filters(self):
        self.cmb_game.blockSignals(True)
        self.cmb_ipset.blockSignals(True)
        self.chk_autoupdate.blockSignals(True)

        self.lbl_game.setText(f"Game Filter: {self.sc.game_filter_status()}")
        self.lbl_ipset.setText(f"IPSet Filter: {self.sc.ipset_filter_status()}")
        self.chk_autoupdate.setChecked(self.sc.auto_update_status())

        self.cmb_game.blockSignals(False)
        self.cmb_ipset.blockSignals(False)
        self.chk_autoupdate.blockSignals(False)

    def _on_select(self, idx: int):
        if self._state == "error":
            self._state = "idle"
            self._last_error = None
        if 0 <= idx < len(self.strategies):
            info = parse_strategy(self.strategies[idx])
            args_text = "\n".join(info["args"]) if info["args"] else "No arguments found"
            self.details.setPlainText(args_text)
        self._update_status()

    def _start(self):
        idx = self.list_widget.currentRow()
        if 0 <= idx < len(self.strategies):
            bat = self.strategies[idx]
            self._state = "starting"
            self._pending_strategy_name = bat.stem
            self._last_error = None
            self._update_status()
            mode = "service" if self.zm.is_service_mode else "process"
            self.log.log(f"Starting strategy: {bat.stem} ({mode})", "system")
            try:
                self.zm.start_strategy(bat)
            except Exception as e:
                self._state = "error"
                self._last_error = str(e) or "Start failed"
                self._poll_timer.stop()
                self._poll_target = None
                self.log.log(f"Start failed: {self._last_error}", "error")
                self._update_status()
                return
            self._start_poll("start")

    def _stop(self):
        self._state = "stopping"
        self._last_error = None
        self._pending_strategy_name = self.zm.current_strategy
        self.log.log("Stopping winws.exe...", "system")
        try:
            self.zm.stop()
        except Exception as e:
            self._state = "error"
            self._last_error = str(e) or "Stop failed"
            self._poll_timer.stop()
            self._poll_target = None
            self.log.log(f"Stop failed: {self._last_error}", "error")
            self._update_status()
            return
        self._start_poll("stop")

    def _start_poll(self, target: str):
        self._poll_target = target
        self._poll_attempts = 0
        self._update_status()
        self._poll_timer.start(POLL_INTERVAL_MS)

    def _on_poll_tick(self):
        self._poll_attempts += 1
        running = self._update_status()
        target = self._poll_target

        if target == "start" and running:
            self._poll_timer.stop()
            self._poll_target = None
            self._state = "idle"
            self._pending_strategy_name = None
            self.log.log("Strategy started successfully", "ok")
            self._update_status()
        elif target == "stop" and not running:
            self._poll_timer.stop()
            self._poll_target = None
            self._state = "idle"
            self._pending_strategy_name = None
            self.log.log("Stopped successfully", "ok")
            self._update_status()
        elif self._poll_attempts >= POLL_MAX_ATTEMPTS:
            self._poll_timer.stop()
            self._poll_target = None
            if target == "start":
                self.log.log("Start timeout — check if winws.exe started", "error")
                self._last_error = "Start timeout"
            else:
                self.log.log("Stop timeout — process may still be running", "error")
                self._last_error = "Stop timeout"
            self._state = "error"
            self._update_status()

    def _update_status(self, auto_detect=False):
        running = self.zm.is_running()
        if auto_detect and running and not self.zm.current_strategy:
            self.zm.detect_strategy()

        if self._state in ("starting", "stopping"):
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
        else:
            self.btn_start.setEnabled(not running)
            self.btn_stop.setEnabled(running)

        if self._state == "starting":
            name = self._pending_strategy_name or self.zm.current_strategy or "selected strategy"
            self.lbl_running.setText(f"Starting: {name}")
            self.lbl_running.setStyleSheet("font-weight: bold; color: #2196F3; padding: 4px;")
        elif self._state == "stopping":
            self.lbl_running.setText("Stopping...")
            self.lbl_running.setStyleSheet("font-weight: bold; color: #2196F3; padding: 4px;")
        elif self._state == "error":
            msg = self._last_error or "Operation failed"
            self.lbl_running.setText(f"Error: {msg}")
            self.lbl_running.setStyleSheet("font-weight: bold; color: #f44336; padding: 4px;")
        elif running:
            cs = self.zm.current_strategy
            if cs == "__service__":
                self.lbl_running.setText("Running as Windows service")
                self.lbl_running.setStyleSheet("font-weight: bold; color: #28a; padding: 4px;")
            elif cs:
                self.lbl_running.setText(f"Running: {cs}")
                self.lbl_running.setStyleSheet("font-weight: bold; color: #2a6; padding: 4px;")
            else:
                self.lbl_running.setText("Running (unknown)")
                self.lbl_running.setStyleSheet("font-weight: bold; color: #284; padding: 4px;")
        else:
            cs = self.zm.current_strategy
            if cs and cs != "__service__":
                self.lbl_running.setText(f"Starting: {cs}")
                self.lbl_running.setStyleSheet("font-weight: bold; color: #284; padding: 4px;")
            else:
                self.lbl_running.setText("")
        self._highlight_current()
        return running

    def _highlight_current(self):
        current = self.zm.current_strategy
        if self._state in ("starting", "stopping", "error"):
            current = self._pending_strategy_name or current

        color = None
        if self._state in ("starting", "stopping"):
            color = QColor("#2196F3")
        elif self._state == "error":
            color = QColor("#f44336")
        elif current and current != "__service__" and self.zm.is_running():
            color = QColor("#4caf50")

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if current and current != "__service__" and item.text() == current and color is not None:
                item.setBackground(color)
            else:
                item.setBackground(Qt.GlobalColor.transparent)

    def _set_game(self, mode: str):
        self.sc.set_game_filter(mode)
        self.log.log(f"Game Filter set to: {mode}", "system")

    def _set_ipset(self, mode: str):
        self.sc.set_ipset_filter(mode)
        self.log.log(f"IPSet Filter set to: {mode}", "system")

    def _toggle_autoupdate(self, checked: bool):
        self.sc.set_auto_update(checked)
        self.log.log(f"Auto-Update: {'enabled' if checked else 'disabled'}", "system")
