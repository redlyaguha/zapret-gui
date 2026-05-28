from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QTextEdit, QGroupBox, QMessageBox
)
from PySide6.QtCore import QThread, Signal
from updater.auto_updater import get_latest_version, get_release_info, download_release, install_update
from pathlib import Path


class UpdateWorker(QThread):
    progress = Signal(int)
    log_msg = Signal(str, str)
    finished_signal = Signal(bool, str)

    def __init__(self, mode: str, install_path: Path, current_version: str):
        super().__init__()
        self.mode = mode
        self.install_path = install_path
        self.current_version = current_version

    def run(self):
        try:
            if self.mode == "check":
                self.log_msg.emit("Checking for updates...", "system")
                latest = get_latest_version()
                self.log_msg.emit(f"Current: {self.current_version}  Latest: {latest}", "info")
                if latest == self.current_version:
                    self.finished_signal.emit(True, f"Latest version installed: {latest}")
                else:
                    info = get_release_info()
                    self.finished_signal.emit(False, f"New version {latest} available")
                    self._release_info = info

            elif self.mode == "download":
                self.log_msg.emit("Fetching release info...", "system")
                info = get_release_info()
                if not info["zip_url"]:
                    self.finished_signal.emit(False, "No .zip asset found")
                    return

                self.log_msg.emit(f"Downloading {info['zip_name']}...", "system")
                data = download_release(info["zip_url"], self.progress.emit)
                self.log_msg.emit(f"Downloaded {len(data)} bytes", "ok")

                self.log_msg.emit("Installing update...", "system")
                install_update(data, self.install_path, self.progress.emit, lambda m: self.log_msg.emit(m, "info"))
                self.finished_signal.emit(True, f"Update to {info['tag_name']} complete")

        except Exception as e:
            self.finished_signal.emit(False, f"Error: {e}")


class UpdateWidget(QWidget):
    def __init__(self, zapret_manager, log_widget, parent=None):
        super().__init__(parent)
        self.zm = zapret_manager
        self.log = log_widget
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info_group = QGroupBox("Version Info")
        info = QVBoxLayout(info_group)
        self.lbl_current = QLabel("Current: —")
        self.lbl_latest = QLabel("Latest: —")
        info.addWidget(self.lbl_current)
        info.addWidget(self.lbl_latest)
        layout.addWidget(info_group)

        actions = QHBoxLayout()
        self.btn_check = QPushButton("Check for Updates")
        self.btn_check.clicked.connect(self._check)
        self.btn_update = QPushButton("Download & Install")
        self.btn_update.clicked.connect(self._update)
        self.btn_update.setEnabled(False)
        actions.addWidget(self.btn_check)
        actions.addWidget(self.btn_update)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumHeight(150)
        self.status_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.status_log)

        layout.addStretch()

        self.refresh()

    def refresh(self):
        ver = self.zm.get_local_version()
        self.lbl_current.setText(f"Current: {ver}")

    def _check(self):
        self.btn_check.setEnabled(False)
        self.btn_update.setEnabled(False)
        self.status_log.clear()
        self._worker = UpdateWorker("check", self.zm.zapret_path, self.zm.get_local_version())
        self._worker.log_msg.connect(self._on_log)
        self._worker.finished_signal.connect(self._on_check_done)
        self._worker.start()

    def _on_check_done(self, is_current: bool, msg: str):
        self.status_log.append(msg)
        self.btn_check.setEnabled(True)
        if not is_current and hasattr(self._worker, "_release_info"):
            self.lbl_latest.setText(f"Latest: {self._worker._release_info['tag_name']}")
            self._release_info = self._worker._release_info
            self._changelog = self._worker._release_info.get("body", "")
            self.btn_update.setEnabled(True)
            if self._changelog:
                self.status_log.append("--- Changelog ---")
                self.status_log.append(self._changelog[:2000])
        elif is_current:
            self.lbl_latest.setText(f"Latest: {self.zm.get_local_version()}")

    def _update(self):
        reply = QMessageBox.warning(
            self,
            "Stop zapret before update",
            "Download & Install will stop all running zapret methods before replacing files.\n\n"
            "winws.exe and the zapret service will be stopped. After the update, start your method again manually.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            self.log.log("Update cancelled by user", "warn")
            return

        self.btn_update.setEnabled(False)
        self.btn_check.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status_log.append("Preparing zapret for update...")
        self.status_log.append("Stopping zapret, winws.exe and WinDivert drivers...")
        self.status_log.append("Removing WinDivert services...")
        self.log.log("Preparing zapret for update...", "system")
        self.log.log("Stopping WinDivert driver before update...", "system")
        self.log.log("Removing WinDivert services before update...", "system")
        try:
            self.zm.prepare_for_update()
        except Exception as e:
            msg = f"Could not stop zapret before update: {e}"
            self.progress.setVisible(False)
            self.btn_check.setEnabled(True)
            self.btn_update.setEnabled(True)
            self.status_log.append(msg)
            self.log.log(msg, "error")
            QMessageBox.critical(self, "Update blocked", msg)
            return

        self._worker = UpdateWorker("download", self.zm.zapret_path, self.zm.get_local_version())
        self._worker.progress.connect(self.progress.setValue)
        self._worker.log_msg.connect(self._on_log)
        self._worker.finished_signal.connect(self._on_update_done)
        self._worker.start()

    def _on_update_done(self, success: bool, msg: str):
        self.progress.setVisible(False)
        self.status_log.append(msg)
        self.btn_check.setEnabled(True)
        self.btn_update.setEnabled(False)
        self.refresh()
        self.log.log(msg, "ok" if success else "error")

    def _on_log(self, msg: str, level: str):
        self.status_log.append(msg)
        self.log.log(msg, level)
