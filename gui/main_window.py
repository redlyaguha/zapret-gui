from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QLabel, QApplication, QFileDialog, QMessageBox,
    QDialog, QProgressBar, QSystemTrayIcon
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon

from pathlib import Path
import json
import sys

from core.app_info import APP_NAME, get_display_name
from core.assets import get_asset_path
from core.zapret_manager import ZapretManager
from core.service_controller import ServiceController

from gui.log_widget import LogWidget
from gui.tray_manager import TrayManager
from gui.strategy_widget import StrategyWidget
from gui.update_widget import UpdateWidget
from gui.tools_widget import ToolsWidget

from updater.installer import install_zapret


def get_config_file() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


CONFIG_FILE = get_config_file()


class InstallWorker(QThread):
    progress = Signal(int)
    log_msg = Signal(str, str)
    finished_signal = Signal(bool, str)

    def __init__(self, target_path: Path):
        super().__init__()
        self.target_path = target_path

    def run(self):
        try:
            install_zapret(self.target_path, self.progress.emit, lambda m: self.log_msg.emit(m, "info"))
            self.finished_signal.emit(True, "Installation complete!")
        except Exception as e:
            self.finished_signal.emit(False, f"Installation failed: {e}")


class InstallDialog(QDialog):
    SUBDIR = "zapret"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{get_display_name()} - First Setup")
        self.setFixedSize(550, 350)
        self.parent_path = Path.home() / "Documents"
        self._manual_path = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(f"Welcome to {get_display_name()}!\nzapret needs to be downloaded and installed.")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Parent folder:"))
        self.path_label = QLabel(str(self.parent_path))
        self.path_label.setStyleSheet("padding: 4px; border: 1px solid #555;")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_label, 1)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        self.lbl_final = QLabel(f"Will install to: {self.parent_path / self.SUBDIR}")
        self.lbl_final.setStyleSheet("color: #888; font-style: italic; padding-left: 4px;")
        layout.addWidget(self.lbl_final)

        self.btn_install = QPushButton("Download & Install zapret")
        self.btn_install.clicked.connect(self._install)
        layout.addWidget(self.btn_install)

        self.btn_manual = QPushButton("I already have zapret installed — point to folder")
        self.btn_manual.clicked.connect(self._manual)
        layout.addWidget(self.btn_manual)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        layout.addWidget(self.status)

        layout.addStretch()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select parent folder")
        if folder:
            self.parent_path = Path(folder)
            self.path_label.setText(str(self.parent_path))
            self.lbl_final.setText(f"Will install to: {self.get_path()}")

    def _install(self):
        self.btn_install.setEnabled(False)
        self.btn_manual.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText("Downloading...")

        target = self.get_path()
        target.mkdir(parents=True, exist_ok=True)
        self._worker = InstallWorker(target)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.log_msg.connect(lambda m, l: self.status.setText(m))
        self._worker.finished_signal.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, msg: str):
        self.status.setText(msg)
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Error", msg)
            self.btn_install.setEnabled(True)
            self.btn_manual.setEnabled(True)

    def _manual(self):
        folder = QFileDialog.getExistingDirectory(self, "Select zapret folder (with service.bat)")
        if folder:
            path = Path(folder)
            if (path / "service.bat").exists():
                self._manual_path = path
                self.accept()
            else:
                QMessageBox.warning(self, "Warning", "service.bat not found in selected folder.\nSelect the zapret subfolder directly.")
                return

    def get_path(self) -> Path:
        if self._manual_path:
            return self._manual_path
        return self.parent_path / self.SUBDIR


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(get_display_name())
        self.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))
        self.setMinimumSize(850, 600)

        self.zapret_path = self._load_config()
        if not self.zapret_path or not (self.zapret_path / "service.bat").exists():
            self._run_first_setup()

        self.zm = ZapretManager(self.zapret_path)
        self.sc = ServiceController(self.zapret_path)

        self._build_ui()
        self._setup_tray()

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_tray_status)
        self._status_timer.start(5000)

    def _load_config(self) -> Path:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text("utf-8"))
                return Path(data["zapret_path"])
            except Exception:
                pass
        return None

    def _save_config(self):
        CONFIG_FILE.write_text(json.dumps({"zapret_path": str(self.zapret_path)}, indent=2), encoding="utf-8")

    def _run_first_setup(self):
        dlg = InstallDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.zapret_path = dlg.get_path()
            self._save_config()
        else:
            sys.exit(0)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        # nav panel
        nav = QHBoxLayout()
        nav.setSpacing(2)
        self.nav_buttons = {}
        sections = [
            ("strategy", "Strategies"),
            ("updates", "Updates"),
            ("tools", "Tools"),
        ]
        for key, label in sections:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self._switch_section(k))
            nav.addWidget(btn)
            self.nav_buttons[key] = btn

        # log toggle
        self.btn_toggle_log = QPushButton("Log")
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setChecked(True)
        self.btn_toggle_log.clicked.connect(self._toggle_log)
        nav.addWidget(self.btn_toggle_log)

        layout.addLayout(nav)

        # content
        content = QHBoxLayout()

        self.stack = QStackedWidget()

        self.log_widget = LogWidget()
        self.strategy_widget = StrategyWidget(self.zm, self.sc, self.log_widget)
        self.update_widget = UpdateWidget(self.zm, self.log_widget)
        self.tools_widget = ToolsWidget(self.sc, self.zm, self.log_widget)

        self.stack.addWidget(self.strategy_widget)
        self.stack.addWidget(self.update_widget)
        self.stack.addWidget(self.tools_widget)

        content.addWidget(self.stack, 2)

        self.log_widget.setMinimumWidth(280)
        self.log_widget.setMaximumWidth(450)
        content.addWidget(self.log_widget, 1)

        layout.addLayout(content, 1)

        self._switch_section("strategy")

        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("zapret.gui")

    def _switch_section(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
        mapping = {"strategy": 0, "updates": 1, "tools": 2}
        if key in mapping:
            self.stack.setCurrentIndex(mapping[key])

    def _toggle_log(self, checked: bool):
        self.log_widget.setVisible(checked)

    def _setup_tray(self):
        self.tray = TrayManager(self)
        self.tray.show_window.connect(self._toggle_visible)
        self.tray.quit_app.connect(self._quit)
        self.tray.show()

    def _toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()
            self.raise_()

    def _update_tray_status(self):
        if hasattr(self, "zm"):
            self.tray.set_status(self.zm.is_running())

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.tray.showMessage(APP_NAME, "Still running in system tray", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _quit(self):
        self.tray.hide()
        QApplication.quit()
