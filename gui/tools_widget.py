from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit
)
from pathlib import Path
from core.diagnostics import run_diagnostics


class ToolsWidget(QWidget):
    def __init__(self, service_controller, zapret_manager, log_widget, parent=None):
        super().__init__(parent)
        self.sc = service_controller
        self.zm = zapret_manager
        self.log = log_widget
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        updates = QGroupBox("Updates")
        upd = QVBoxLayout(updates)
        self.btn_ipset = QPushButton("Update IPSet List")
        self.btn_ipset.clicked.connect(self._update_ipset)
        self.btn_hosts = QPushButton("Update Hosts File")
        self.btn_hosts.clicked.connect(self._update_hosts)
        upd.addWidget(self.btn_ipset)
        upd.addWidget(self.btn_hosts)
        layout.addWidget(updates)

        diag = QGroupBox("Diagnostics")
        diag_layout = QVBoxLayout(diag)
        self.btn_diag = QPushButton("Run Diagnostics")
        self.btn_diag.clicked.connect(self._run_diag)
        self.diag_output = QTextEdit()
        self.diag_output.setReadOnly(True)
        self.diag_output.setMaximumHeight(200)
        self.diag_output.setStyleSheet("font-family: Consolas; font-size: 11px;")
        diag_layout.addWidget(self.btn_diag)
        diag_layout.addWidget(self.diag_output)
        layout.addWidget(diag)

        discord = QGroupBox("Discord")
        dc = QVBoxLayout(discord)
        self.btn_clear_cache = QPushButton("Clear Discord Cache")
        self.btn_clear_cache.clicked.connect(self._clear_discord_cache)
        dc.addWidget(self.btn_clear_cache)

        tests = QGroupBox("Tests")
        tst = QVBoxLayout(tests)
        self.btn_tests = QPushButton("Run Tests")
        self.btn_tests.clicked.connect(self._run_tests)
        tst.addWidget(self.btn_tests)

        layout.addWidget(discord)
        layout.addWidget(tests)
        layout.addStretch()

    def _update_ipset(self):
        self.sc.update_ipset()
        self.log.log("IPSet update launched", "system")

    def _update_hosts(self):
        self.sc.update_hosts()
        self.log.log("Hosts update launched (check notepad)", "system")

    def _run_diag(self):
        self.diag_output.clear()
        self.log.log("Running diagnostics...", "system")
        results = run_diagnostics(self.zm.zapret_path)
        for name, status in results:
            self.diag_output.append(f"[{status.upper():6s}] {name}")
            self.log.log(f"{name}: {status}", "ok" if status == "pass"
                         else ("warn" if status.startswith("warn") else "error"))

    def _clear_discord_cache(self):
        import subprocess, shutil
        appdata = Path.home() / "AppData" / "Roaming" / "discord"
        for folder in ["Cache", "Code Cache", "GPUCache"]:
            target = appdata / folder
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                self.log.log(f"Deleted {target}", "ok")

    def _run_tests(self):
        test_ps = self.zm.zapret_path / "utils" / "test zapret.ps1"
        if test_ps.exists():
            import subprocess
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(test_ps)],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.log.log("Tests launched in PowerShell window", "system")
        else:
            self.log.log("test zapret.ps1 not found", "error")
