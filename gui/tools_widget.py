from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit, QDialog, QRadioButton, QListWidget,
    QListWidgetItem, QDialogButtonBox, QMessageBox, QApplication
)
from PySide6.QtCore import QThread, Signal
from pathlib import Path
import ctypes
import re
import subprocess
import tempfile
import sys
from core.diagnostics import run_diagnostics


class TestOptionsDialog(QDialog):
    def __init__(self, zapret_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run Tests")
        self.zapret_path = zapret_path
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        type_group = QGroupBox("Test type")
        type_layout = QVBoxLayout(type_group)
        self.rb_standard = QRadioButton("Standard tests (HTTP/ping)")
        self.rb_dpi = QRadioButton("DPI checkers (TCP 16-20 freeze)")
        self.rb_standard.setChecked(True)
        type_layout.addWidget(self.rb_standard)
        type_layout.addWidget(self.rb_dpi)
        layout.addWidget(type_group)

        mode_group = QGroupBox("Configs")
        mode_layout = QVBoxLayout(mode_group)
        self.rb_all = QRadioButton("All configs")
        self.rb_selected = QRadioButton("Selected configs")
        self.rb_all.setChecked(True)
        self.rb_all.toggled.connect(self._sync_selection)
        mode_layout.addWidget(self.rb_all)
        mode_layout.addWidget(self.rb_selected)

        self.config_list = QListWidget()
        self.config_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.config_files = self._find_test_configs()
        for file in self.config_files:
            item = QListWidgetItem(file.name)
            self.config_list.addItem(item)
        mode_layout.addWidget(self.config_list)
        layout.addWidget(mode_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._sync_selection()

    def _find_test_configs(self):
        def natural_key(path: Path):
            return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]

        return sorted(
            [p for p in self.zapret_path.glob("*.bat") if not p.name.lower().startswith("service")],
            key=natural_key,
        )

    def _sync_selection(self):
        self.config_list.setEnabled(self.rb_selected.isChecked())

    def options(self):
        selected_rows = [
            self.config_list.row(item) + 1
            for item in self.config_list.selectedItems()
        ]
        return {
            "test_type": "1" if self.rb_standard.isChecked() else "2",
            "mode": "1" if self.rb_all.isChecked() else "2",
            "selection": ",".join(str(row) for row in sorted(selected_rows)),
        }

    def accept(self):
        if self.rb_selected.isChecked() and not self.config_list.selectedItems():
            QMessageBox.warning(self, "Run Tests", "Select at least one config or choose All configs.")
            return
        super().accept()


class TestWorker(QThread):
    output = Signal(str)
    finished_signal = Signal(int, str, str)

    def __init__(self, zapret_path: Path, options: dict):
        super().__init__()
        self.zapret_path = zapret_path
        self.options = options

    def run(self):
        test_ps = self.zapret_path / "utils" / "test zapret.ps1"
        if not test_ps.exists():
            self.finished_signal.emit(1, "test zapret.ps1 not found", "")
            return

        try:
            source = test_ps.read_text("utf-8", errors="ignore")
            source = re.sub(
                r'(?m)^\s*\[void\]\[System\.Console\]::ReadKey\(\$true\)\s*$',
                "",
                source,
            )
            temp_script = Path(tempfile.gettempdir()) / "zapret-gui-test-runner.ps1"
            temp_script.write_text(source, encoding="utf-8")

            stdin_lines = [
                self.options["test_type"],
                self.options["mode"],
            ]
            if self.options["mode"] == "2":
                stdin_lines.append(self.options["selection"])
            stdin_text = "\n".join(stdin_lines) + "\n"

            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(temp_script)],
                cwd=self.zapret_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            proc.stdin.write(stdin_text)
            proc.stdin.close()

            for line in proc.stdout:
                self.output.emit(line.rstrip())

            exit_code = proc.wait()
            result_file = self._latest_result_file()
            best = self._read_best_strategy(result_file)
            self.finished_signal.emit(exit_code, str(result_file) if result_file else "", best)
        except Exception as e:
            self.finished_signal.emit(1, "", str(e))

    def _latest_result_file(self):
        results_dir = self.zapret_path / "utils" / "test results"
        if not results_dir.exists():
            return None
        files = sorted(results_dir.glob("test_results_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def _read_best_strategy(self, result_file):
        if not result_file:
            return ""
        for line in result_file.read_text("utf-8", errors="ignore").splitlines():
            if line.lower().startswith("best strategy:"):
                return line
        return ""


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
        self.log.log("Updating hosts file...", "system")
        success, msg = self.sc.update_hosts()
        level = "ok" if success else "error"
        for line in msg.splitlines():
            self.log.log(line, level if line.startswith("ERROR:") else "info")
        if success:
            self.log.log("Hosts file updated successfully", "ok")
        else:
            QMessageBox.critical(self, "Hosts update failed", msg)

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
        if not self._is_admin():
            reply = QMessageBox.warning(
                self,
                "Run Tests",
                "Tests require administrator rights.\n\nRestart zapret-gui as Administrator now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            self.log.log("Run Tests requires administrator rights", "error")
            if reply == QMessageBox.StandardButton.Yes:
                self._restart_as_admin()
            return

        dlg = TestOptionsDialog(self.zm.zapret_path, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self.diag_output.clear()
        self.btn_tests.setEnabled(False)
        self.log.log("Running zapret tests...", "system")
        self._test_worker = TestWorker(self.zm.zapret_path, dlg.options())
        self._test_worker.output.connect(self._on_test_output)
        self._test_worker.finished_signal.connect(self._on_tests_done)
        self._test_worker.start()

    def _on_test_output(self, line: str):
        if line:
            self.diag_output.append(line)

    def _on_tests_done(self, exit_code: int, result_file: str, best: str):
        self.btn_tests.setEnabled(True)
        msg = f"Tests finished with exit code {exit_code}"
        self.diag_output.append(msg)
        self.log.log(msg, "ok" if exit_code == 0 else "error")
        if result_file:
            self.diag_output.append(f"Results: {result_file}")
            self.log.log(f"Test results saved to: {result_file}", "system")
        if best:
            self.diag_output.append(best)
            self.log.log(best, "ok")

    def _is_admin(self):
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _restart_as_admin(self):
        args = " ".join(f'"{arg}"' for arg in sys.argv)
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
        if result > 32:
            QApplication.quit()
        else:
            self.log.log("Administrator restart was cancelled or failed", "error")
