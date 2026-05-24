from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QGroupBox, QCheckBox
)
from core.strategy_parser import find_strategies


class ServiceWidget(QWidget):
    def __init__(self, service_controller, zapret_manager, strategy_path, log_widget, parent=None):
        super().__init__(parent)
        self.sc = service_controller
        self.zm = zapret_manager
        self.strategy_path = strategy_path
        self.log = log_widget
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        service_group = QGroupBox("Windows Service")
        srv = QVBoxLayout(service_group)

        self.lbl_status = QLabel("Status: checking...")
        self.lbl_strategy = QLabel("Installed strategy: —")
        srv.addWidget(self.lbl_status)
        srv.addWidget(self.lbl_strategy)

        srv_btn = QHBoxLayout()
        self.cmb_strategy = QComboBox()
        self.btn_install = QPushButton("Install Service")
        self.btn_install.clicked.connect(self._install)
        self.btn_remove = QPushButton("Remove Services")
        self.btn_remove.clicked.connect(self._remove)
        self.btn_refresh = QPushButton("Refresh Status")
        self.btn_refresh.clicked.connect(self.refresh)
        srv_btn.addWidget(QLabel("Strategy:"))
        srv_btn.addWidget(self.cmb_strategy, 1)
        srv_btn.addWidget(self.btn_install)
        srv_btn.addWidget(self.btn_remove)
        srv.addLayout(srv_btn)
        srv.addWidget(self.btn_refresh)
        layout.addWidget(service_group)

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
        layout.addStretch()

    def refresh(self):
        self._refresh_strategies()
        self._refresh_status()
        self._refresh_filters()

    def _refresh_strategies(self):
        self.cmb_strategy.blockSignals(True)
        self.cmb_strategy.clear()
        for s in find_strategies(self.strategy_path):
            self.cmb_strategy.addItem(s.stem)
        self.cmb_strategy.blockSignals(False)

    def _refresh_status(self):
        zapret = self.sc.service_status("zapret")
        divert = self.sc.service_status("WinDivert")
        strat = self.sc.get_installed_strategy()
        self.lbl_status.setText(f"zapret: {zapret.upper()}  |  WinDivert: {divert.upper()}")
        self.lbl_strategy.setText(f"Installed strategy: {strat if strat else '—'}")

    def _refresh_filters(self):
        self.lbl_game.setText(f"Game Filter: {self.sc.game_filter_status()}")
        self.lbl_ipset.setText(f"IPSet Filter: {self.sc.ipset_filter_status()}")
        self.chk_autoupdate.setChecked(self.sc.auto_update_status())

    def _install(self):
        name = self.cmb_strategy.currentText()
        if name:
            ok, msg = self.sc.install_service(name)
            self.log.log(msg, "system" if ok else "error")
            self._refresh_status()

    def _remove(self):
        self.sc.remove_services()
        self.log.log("Services removed", "system")
        self._refresh_status()

    def _set_game(self, mode: str):
        self.sc.set_game_filter(mode)
        self.log.log(f"Game Filter set to: {mode}", "system")

    def _set_ipset(self, mode: str):
        self.sc.set_ipset_filter(mode)
        self.log.log(f"IPSet Filter set to: {mode}", "system")

    def _toggle_autoupdate(self, checked: bool):
        self.sc.set_auto_update(checked)
        self.log.log(f"Auto-Update: {'enabled' if checked else 'disabled'}", "system")
