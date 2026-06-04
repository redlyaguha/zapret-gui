from pathlib import Path
import ctypes
from datetime import date
import math
import sys
import webbrowser

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QThread, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QGraphicsOpacityEffect, QProgressBar, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
    QSystemTrayIcon,
)

from core.app_info import APP_NAME, APP_VERSION, GITHUB_REPO, get_display_name
from core.assets import get_asset_path
from core.service_controller import ServiceController
from core.zapret_manager import ZapretManager
from gui.app_update import (
    AppUpdateInfo, check_app_update, download_and_verify_update, extract_app_exe,
    launch_update_helper, open_releases,
)
from gui.app_logger import log_app_event, reload_app_logger
from gui.config import (
    DATA_DIR_NAME, change_data_parent, clear_logs, data_dir_from_parent,
    format_size, get_data_dir, get_gui_logs_dir, load_config, logs_size_bytes, save_config,
)
from gui.effects import add_press_effect
from gui.log_widget import LogWidget
from gui.strategy_widget import DropdownSelect, SegmentedSwitch, StrategyWidget
from gui.theme import apply_app_theme, app_stylesheet
from gui.tray_manager import TrayManager
from updater.installer import install_zapret


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
            self.finished_signal.emit(True, "Установка завершена.")
        except Exception as e:
            self.finished_signal.emit(False, f"Не удалось установить zapret: {e}")


class InstallDialog(QDialog):
    SUBDIR = "zapret"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{get_display_name()} - первая настройка")
        self.setFixedSize(590, 380)
        self.parent_path = Path.home() / "Documents"
        self._manual_path = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Добро пожаловать в zapret-gui")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("Для работы нужно скачать zapret или выбрать уже установленную папку.")
        subtitle.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Папка установки:"))
        self.path_label = QLabel(str(self.parent_path))
        self.path_label.setObjectName("Pill")
        btn_browse = QPushButton("Выбрать")
        add_press_effect(btn_browse)
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_label, 1)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        self.lbl_final = QLabel(f"Итоговый путь: {self.parent_path / self.SUBDIR}")
        self.lbl_final.setObjectName("Muted")
        layout.addWidget(self.lbl_final)

        self.btn_install = QPushButton("Скачать и установить zapret")
        self.btn_install.setObjectName("PrimaryButton")
        add_press_effect(self.btn_install)
        self.btn_install.clicked.connect(self._install)
        layout.addWidget(self.btn_install)

        self.btn_manual = QPushButton("У меня уже есть zapret")
        add_press_effect(self.btn_manual)
        self.btn_manual.clicked.connect(self._manual)
        layout.addWidget(self.btn_manual)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)
        layout.addStretch()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите родительскую папку")
        if folder:
            self.parent_path = Path(folder)
            self.path_label.setText(str(self.parent_path))
            self.lbl_final.setText(f"Итоговый путь: {self.get_path()}")

    def _install(self):
        self.btn_install.setEnabled(False)
        self.btn_manual.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText("Загрузка...")

        target = self.get_path()
        target.mkdir(parents=True, exist_ok=True)
        self._worker = InstallWorker(target)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.log_msg.connect(lambda m, _level: self.status.setText(m))
        self._worker.finished_signal.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, msg: str):
        self.status.setText(msg)
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Ошибка", msg)
            self.btn_install.setEnabled(True)
            self.btn_manual.setEnabled(True)

    def _manual(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку zapret с service.bat")
        if folder:
            path = Path(folder)
            if (path / "service.bat").exists():
                self._manual_path = path
                self.accept()
            else:
                QMessageBox.warning(self, "Папка не подходит", "В выбранной папке не найден service.bat.")

    def get_path(self) -> Path:
        return self._manual_path if self._manual_path else self.parent_path / self.SUBDIR


class AppUpdateWorker(QThread):
    finished_signal = Signal(object, str)

    def __init__(self, include_prerelease: bool, require_assets: bool):
        super().__init__()
        self.include_prerelease = include_prerelease
        self.require_assets = require_assets

    def run(self):
        try:
            info = check_app_update(self.include_prerelease, self.require_assets)
            self.finished_signal.emit(info, "")
        except Exception as e:
            self.finished_signal.emit(None, str(e))


class AppUpdateInstallWorker(QThread):
    progress = Signal(int)
    finished_signal = Signal(object, str)

    def __init__(self, info: AppUpdateInfo, updates_dir: Path):
        super().__init__()
        self.info = info
        self.updates_dir = updates_dir

    def run(self):
        try:
            zip_path = download_and_verify_update(self.info, self.updates_dir, self.progress.emit)
            exe_path = extract_app_exe(zip_path, zip_path.parent)
            self.finished_signal.emit(exe_path, "")
        except Exception as e:
            self.finished_signal.emit(None, str(e))


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    config_changed = Signal()
    check_updates_requested = Signal()
    install_update_requested = Signal()
    skip_update_requested = Signal()
    zapret_path_changed = Signal(Path)
    data_dir_changed = Signal()

    def __init__(self, config: dict, zapret_path: Path, parent=None):
        super().__init__(parent)
        self.config = config
        self.zapret_path = zapret_path
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(16)

        title = QLabel("Настройки")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.update_banner = QFrame()
        self.update_banner.setObjectName("GlassPanel")
        banner = QHBoxLayout(self.update_banner)
        banner.setContentsMargins(16, 12, 16, 12)
        self.update_text = QLabel("")
        self.update_text.setWordWrap(True)
        btn_release = QPushButton("Открыть релиз")
        add_press_effect(btn_release)
        btn_release.clicked.connect(open_releases)
        btn_hide = QPushButton("Скрыть")
        add_press_effect(btn_hide)
        btn_hide.clicked.connect(self._clear_deferred_update)
        banner.addWidget(self.update_text, 1)
        banner.addWidget(btn_release)
        banner.addWidget(btn_hide)
        root.addWidget(self.update_banner)

        appearance = self._panel("Внешний вид")
        app_l = appearance.layout()
        theme_row = QWidget()
        theme_row.setFixedHeight(46)
        row = QHBoxLayout(theme_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        theme_label = QLabel("Тема")
        theme_label.setObjectName("SettingLabel")
        row.addWidget(theme_label, 1, Qt.AlignmentFlag.AlignVCenter)
        self.theme_values = ["system", "light", "dark"]
        self.theme_switch = SegmentedSwitch(["Системная", "Светлая", "Темная"])
        self.theme_switch.setFixedSize(330, 42)
        current_theme = self.config.get("theme", "system")
        self.theme_switch.set_index(self.theme_values.index(current_theme) if current_theme in self.theme_values else 0, emit=False)
        self.theme_switch.changed.connect(self._on_theme_change)
        row.addWidget(self.theme_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        app_l.addWidget(theme_row)

        behavior = self._panel("Поведение")
        behavior.setMinimumHeight(150)
        beh_l = behavior.layout()
        beh_l.setContentsMargins(18, 18, 18, 18)
        beh_l.setSpacing(12)
        self.chk_no_tray = QCheckBox("Не сворачивать в трей при закрытии окна")
        self.chk_no_tray.setChecked(not self.config.get("stay_open_on_close", True))
        self.chk_no_tray.toggled.connect(self._save_behavior)
        self.chk_startup = QCheckBox("Запускать вместе с Windows")
        self.chk_startup.setChecked(self.config.get("launch_on_startup", False))
        self.chk_startup.toggled.connect(self._save_behavior)
        self.startup_mode_values = ["window", "tray"]
        self.startup_mode_select = DropdownSelect(["В окне", "В трее"])
        self.startup_mode_select.changed.connect(lambda _idx: self._save_behavior())
        self.chk_admin = QCheckBox("Всегда запускать от имени администратора")
        self.chk_admin.setChecked(self.config.get("always_run_as_admin", False))
        self.chk_admin.toggled.connect(self._save_behavior)
        beh_l.addWidget(self._behavior_row(self.chk_no_tray))
        beh_l.addWidget(self._behavior_row(self.chk_startup, self.startup_mode_select))
        beh_l.addWidget(self._behavior_row(self.chk_admin))
        self._sync_behavior_controls()

        updates = self._panel("Обновления zapret-gui")
        upd_l = updates.layout()
        self.chk_app_auto_update = QCheckBox("Автоматически проверять обновления")
        self.chk_app_auto_update.setChecked(self.config.get("app_auto_update_enabled", True))
        self.chk_app_auto_update.toggled.connect(self._save_update_settings)
        self.chk_app_prerelease = QCheckBox("Получать beta/prerelease")
        self.chk_app_prerelease.setChecked(self.config.get("app_update_include_prerelease", False))
        self.chk_app_prerelease.toggled.connect(self._save_update_settings)
        upd_l.addWidget(self._behavior_row(self.chk_app_auto_update))
        upd_l.addWidget(self._behavior_row(self.chk_app_prerelease))

        upd_row = QHBoxLayout()
        self.lbl_update_status = QLabel("Проверка выполняется только для приложения, не для zapret.")
        self.lbl_update_status.setObjectName("Muted")
        self.btn_check_app_update = QPushButton("Проверить обновления")
        add_press_effect(self.btn_check_app_update)
        self.btn_check_app_update.clicked.connect(lambda _checked=False: self.check_updates_requested.emit())
        upd_row.addWidget(self.lbl_update_status, 1)
        upd_row.addWidget(self.btn_check_app_update)
        upd_l.addLayout(upd_row)

        self.app_update_progress = QProgressBar()
        self.app_update_progress.setVisible(False)
        upd_l.addWidget(self.app_update_progress)

        update_actions = QHBoxLayout()
        self.btn_install_app_update = QPushButton("Обновить")
        self.btn_install_app_update.setObjectName("PrimaryButton")
        add_press_effect(self.btn_install_app_update)
        self.btn_install_app_update.clicked.connect(lambda _checked=False: self.install_update_requested.emit())
        self.btn_later_app_update = QPushButton("Позже")
        add_press_effect(self.btn_later_app_update)
        self.btn_later_app_update.clicked.connect(self._hide_update_actions)
        self.btn_skip_app_update = QPushButton("Пропустить версию")
        add_press_effect(self.btn_skip_app_update)
        self.btn_skip_app_update.clicked.connect(lambda _checked=False: self.skip_update_requested.emit())
        update_actions.addWidget(self.btn_install_app_update)
        update_actions.addWidget(self.btn_later_app_update)
        update_actions.addWidget(self.btn_skip_app_update)
        update_actions.addStretch()
        upd_l.addLayout(update_actions)
        self._set_update_actions_visible(False)

        path_panel = self._panel("Папка zapret")
        path_l = path_panel.layout()
        path_row = QHBoxLayout()
        self.lbl_path = QLabel(str(self.zapret_path))
        self.lbl_path.setObjectName("Pill")
        btn_path = QPushButton("Изменить")
        add_press_effect(btn_path)
        btn_path.clicked.connect(self._change_path)
        path_row.addWidget(self.lbl_path, 1)
        path_row.addWidget(btn_path)
        path_l.addLayout(path_row)

        data_panel = self._panel("Папка данных")
        data_l = data_panel.layout()
        data_row = QHBoxLayout()
        self.lbl_data_path = QLabel(str(get_data_dir()))
        self.lbl_data_path.setObjectName("Pill")
        btn_data_path = QPushButton("Изменить")
        add_press_effect(btn_data_path)
        btn_data_path.clicked.connect(self._change_data_path)
        data_row.addWidget(self.lbl_data_path, 1)
        data_row.addWidget(btn_data_path)
        data_l.addLayout(data_row)

        logs_row = QHBoxLayout()
        self.lbl_logs_size = QLabel("")
        self.lbl_logs_size.setObjectName("Muted")
        btn_clear_logs = QPushButton("Очистить логи")
        btn_clear_logs.setObjectName("DangerButton")
        add_press_effect(btn_clear_logs)
        btn_clear_logs.clicked.connect(self._clear_log_files)
        logs_row.addWidget(self.lbl_logs_size, 1)
        logs_row.addWidget(btn_clear_logs)
        data_l.addLayout(logs_row)

        tools = self._panel("Сервис")
        tools_l = tools.layout()
        tools_row = QHBoxLayout()
        btn_reset = QPushButton("Сбросить настройки")
        btn_reset.setObjectName("DangerButton")
        add_press_effect(btn_reset)
        btn_reset.clicked.connect(self._reset_settings)
        tools_row.addWidget(btn_reset)
        tools_row.addStretch()
        tools_l.addLayout(tools_row)

        root.addWidget(appearance)
        root.addWidget(behavior)
        root.addWidget(updates)
        root.addWidget(path_panel)
        root.addWidget(data_panel)
        root.addWidget(tools)
        root.addStretch()
        self.refresh_storage_info()
        self.refresh_banner()

    def _panel(self, title: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("GlassPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        return panel

    def _behavior_row(self, checkbox: QCheckBox, trailing: QWidget | None = None) -> QWidget:
        row = QWidget()
        row.setObjectName("BehaviorRow")
        row.setFixedHeight(38)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        checkbox.setFixedHeight(30)
        checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(checkbox, 1, Qt.AlignmentFlag.AlignVCenter)
        if trailing:
            row_layout.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)
        row_layout.addStretch()
        return row

    def refresh_banner(self):
        info = self.config.get("deferred_app_update")
        self.update_banner.setVisible(bool(info))
        if info:
            label = "beta" if info.get("is_prerelease") else "stable"
            self.update_text.setText(f"Доступно обновление zapret-gui: {info.get('latest_version', '')} ({label})")

    def _sync_behavior_controls(self):
        controls = (
            self.chk_no_tray,
            self.chk_startup,
            self.chk_admin,
            self.startup_mode_select,
        )
        for control in controls:
            control.blockSignals(True)
        self.chk_no_tray.setChecked(not self.config.get("stay_open_on_close", True))
        self.chk_startup.setChecked(self.config.get("launch_on_startup", False))
        self.chk_admin.setChecked(self.config.get("always_run_as_admin", False))
        startup_mode = self.config.get("startup_mode", "window")
        idx = self.startup_mode_values.index(startup_mode) if startup_mode in self.startup_mode_values else 0
        self.startup_mode_select.set_index(idx, emit=False)
        self.startup_mode_select.setEnabled(self.chk_startup.isChecked())
        for control in controls:
            control.blockSignals(False)

    def _sync_update_controls(self):
        controls = (
            self.chk_app_auto_update,
            self.chk_app_prerelease,
        )
        for control in controls:
            control.blockSignals(True)
        self.chk_app_auto_update.setChecked(self.config.get("app_auto_update_enabled", True))
        self.chk_app_prerelease.setChecked(self.config.get("app_update_include_prerelease", False))
        for control in controls:
            control.blockSignals(False)

    def _save_update_settings(self):
        self.config["app_auto_update_enabled"] = self.chk_app_auto_update.isChecked()
        self.config["app_update_include_prerelease"] = self.chk_app_prerelease.isChecked()
        save_config(self.config)
        self.config_changed.emit()

    def _set_update_actions_visible(self, visible: bool):
        for button in (
            self.btn_install_app_update,
            self.btn_later_app_update,
            self.btn_skip_app_update,
        ):
            button.setVisible(visible)

    def _hide_update_actions(self):
        self._set_update_actions_visible(False)

    def set_update_checking(self, checking: bool):
        self.btn_check_app_update.setEnabled(not checking)
        self.btn_install_app_update.setEnabled(not checking)

    def show_update_available(self, info: AppUpdateInfo):
        label = "beta" if info.is_prerelease else "stable"
        self.lbl_update_status.setText(f"Доступна версия {info.latest_version} ({label}).")
        self._set_update_actions_visible(True)

    def show_no_update(self):
        self.lbl_update_status.setText("Установлена актуальная версия.")
        self._set_update_actions_visible(False)

    def show_update_error(self, error: str):
        self.lbl_update_status.setText(f"Не удалось проверить: {error}")
        self._set_update_actions_visible(False)

    def set_update_progress(self, visible: bool, value: int = 0):
        self.app_update_progress.setVisible(visible)
        self.app_update_progress.setValue(value)

    def refresh_storage_info(self):
        self.lbl_data_path.setText(str(get_data_dir()))
        self.lbl_logs_size.setText(f"Логи занимают: {format_size(logs_size_bytes())}")

    def _clear_deferred_update(self):
        self.config["deferred_app_update"] = None
        save_config(self.config)
        self.refresh_banner()
        self.config_changed.emit()

    def _on_theme_change(self, idx: int):
        theme = self.theme_values[idx]
        self.config["theme"] = theme
        save_config(self.config)
        self.theme_changed.emit(theme)

    def _save_behavior(self):
        previous_admin_startup = (
            self.config.get("launch_on_startup", False)
            and self.config.get("always_run_as_admin", False)
        )
        self.config["stay_open_on_close"] = not self.chk_no_tray.isChecked()
        self.config["launch_on_startup"] = self.chk_startup.isChecked()
        self.config["startup_mode"] = self.startup_mode_values[self.startup_mode_select.current_index()]
        self.config["always_run_as_admin"] = self.chk_admin.isChecked()
        self.startup_mode_select.setEnabled(self.chk_startup.isChecked())
        self._set_startup(
            self.chk_startup.isChecked(),
            self.config["startup_mode"],
            self.chk_admin.isChecked(),
            previous_admin_startup,
        )
        save_config(self.config)
        self.config_changed.emit()

    def _startup_command(self, mode: str) -> str:
        args = ["--startup-tray"] if mode == "tray" else []
        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}"'
        else:
            script = Path(sys.argv[0]).resolve()
            command = f'"{sys.executable}" "{script}"'
        if args:
            command += " " + " ".join(args)
        return command

    def _set_startup(self, enabled: bool, mode: str, run_as_admin: bool, cleanup_elevated: bool = False):
        try:
            self._delete_startup_registry()
            self._run_schtasks_delete(elevated=cleanup_elevated and not run_as_admin)
            if not enabled:
                return
            command = self._startup_command(mode)
            if run_as_admin:
                self._run_schtasks_create(command)
            else:
                self._write_startup_registry(command)
        except Exception as e:
            log_app_event("error", "startup", f"Could not update startup settings: {e}")
            QMessageBox.warning(self, "Автозапуск", f"Не удалось изменить автозапуск: {e}")

    def _delete_startup_registry(self):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass

    def _write_startup_registry(self, command: str):
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)

    def _run_schtasks_delete(self, elevated: bool):
        command = f'schtasks /Delete /TN "{APP_NAME}" /F'
        if elevated:
            self._run_elevated_cmd(f'{command} >nul 2>&1 & exit /b 0')
            return
        try:
            import subprocess
            subprocess.run(
                ["schtasks", "/Delete", "/TN", APP_NAME, "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    def _run_schtasks_create(self, command: str):
        quoted_command = command.replace('"', r'\"')
        create = (
            f'schtasks /Create /TN "{APP_NAME}" /SC ONLOGON '
            f'/TR "{quoted_command}" /RL HIGHEST /F'
        )
        self._run_elevated_cmd(f'schtasks /Delete /TN "{APP_NAME}" /F >nul 2>&1 & {create}')

    def _run_elevated_cmd(self, command: str):
        import subprocess
        ps_command = (
            "$p = Start-Process -FilePath cmd.exe "
            f"-ArgumentList @('/c', {self._ps_quote(command)}) "
            "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "UAC был отменён или schtasks завершился с ошибкой").strip()
            raise RuntimeError(details)

    def _ps_quote(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _change_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку zapret с service.bat", str(self.zapret_path))
        if not folder:
            return
        path = Path(folder)
        if not (path / "service.bat").exists():
            QMessageBox.warning(self, "Папка не подходит", "В выбранной папке не найден service.bat.")
            return
        self.zapret_path = path
        self.config["zapret_path"] = str(path)
        save_config(self.config)
        self.lbl_path.setText(str(path))
        self.zapret_path_changed.emit(path)

    def _change_data_path(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            f"Выберите родительскую папку для {DATA_DIR_NAME}",
            str(get_data_dir().parent),
        )
        if not folder:
            return
        target = data_dir_from_parent(Path(folder))
        reply = QMessageBox.information(
            self,
            "Папка данных",
            f"Будет создана или использована папка:\n{target}\n\nТекущие настройки и логи будут перенесены.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return
        try:
            change_data_parent(Path(folder))
        except Exception as e:
            log_app_event("error", "data-dir", f"Could not move data directory: {e}")
            QMessageBox.critical(self, "Папка данных", f"Не удалось перенести данные:\n{e}")
            return
        save_config(self.config)
        self.refresh_storage_info()
        self.data_dir_changed.emit()

    def _clear_log_files(self):
        reply = QMessageBox.warning(
            self,
            "Очистить логи",
            "Удалить все сохраненные файлы логов?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return
        clear_logs()
        self.refresh_storage_info()
        self.data_dir_changed.emit()

    def _reset_settings(self):
        reply = QMessageBox.warning(
            self,
            "Сброс настроек",
            "Сбросить тему, поведение окна и отложенные уведомления? Путь к zapret сохранится.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return
        zapret_path = self.config.get("zapret_path", "")
        self.config.clear()
        self.config.update(load_config())
        self.config.update({
            "zapret_path": zapret_path,
            "theme": "system",
            "stay_open_on_close": True,
            "launch_on_startup": False,
            "startup_mode": "window",
            "always_run_as_admin": False,
            "deferred_app_update": None,
            "last_strategy": self.config.get("last_strategy", ""),
            "last_strategy_mode": self.config.get("last_strategy_mode", "process"),
            "app_auto_update_enabled": True,
            "app_update_include_prerelease": False,
            "last_app_update_check": "",
            "skipped_app_version": "",
        })
        save_config(self.config)
        self.theme_switch.set_index(0, emit=False)
        self._sync_behavior_controls()
        self._sync_update_controls()
        self.refresh_banner()
        self.theme_changed.emit("system")
        self.config_changed.emit()


class TelegramPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addStretch()
        panel = QFrame()
        panel.setObjectName("GlassPanel")
        panel_l = QVBoxLayout(panel)
        panel_l.setContentsMargins(28, 28, 28, 28)
        title = QLabel("Telegram")
        title.setObjectName("HeroTitle")
        text = QLabel("Раздел для обхода Telegram появится позже. Навигация уже готова, чтобы функция подключилась без переделки интерфейса.")
        text.setObjectName("Muted")
        text.setWordWrap(True)
        panel_l.addWidget(title)
        panel_l.addWidget(text)
        layout.addWidget(panel)
        layout.addStretch()


class AboutPage(QWidget):
    def __init__(self, zapret_manager: ZapretManager, parent=None):
        super().__init__(parent)
        self.zm = zapret_manager
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)
        title = QLabel("О приложении")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        panel = QFrame()
        panel.setObjectName("GlassPanel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(18, 16, 18, 16)
        rows = [
            ("zapret-gui", APP_VERSION),
            ("zapret", self.zm.get_local_version()),
            ("Репозиторий", GITHUB_REPO),
            ("Telegram", "https://t.me/lyaguha_logs"),
            ("Сборка", "Portable Windows / исходники Python"),
        ]
        for row, (name, value) in enumerate(rows):
            label = QLabel(name)
            label.setObjectName("Muted")
            grid.addWidget(label, row, 0)
            grid.addWidget(QLabel(value), row, 1)
        layout.addWidget(panel)

        licenses = QFrame()
        licenses.setObjectName("GlassPanel")
        licenses_layout = QVBoxLayout(licenses)
        licenses_layout.setContentsMargins(18, 16, 18, 16)
        licenses_layout.setSpacing(8)
        licenses_title = QLabel("Сторонние компоненты")
        licenses_title.setObjectName("SectionTitle")
        licenses_text = QLabel(
            "Flowseal/zapret-discord-youtube - MIT, Copyright (c) 2024-2026 Flowseal\n"
            "bol-van/zapret - MIT, Copyright (c) 2016-2026 bol-van\n"
            "WinDivert - LGPLv3 или GPLv2 на выбор: https://github.com/basil00/WinDivert"
        )
        licenses_text.setWordWrap(True)
        licenses_text.setObjectName("Muted")
        licenses_layout.addWidget(licenses_title)
        licenses_layout.addWidget(licenses_text)
        layout.addWidget(licenses)

        actions = QHBoxLayout()
        btn_github = QPushButton("GitHub")
        add_press_effect(btn_github)
        btn_github.clicked.connect(lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        btn_releases = QPushButton("Releases")
        add_press_effect(btn_releases)
        btn_releases.clicked.connect(open_releases)
        btn_telegram = QPushButton("Telegram")
        add_press_effect(btn_telegram)
        btn_telegram.clicked.connect(lambda: webbrowser.open("https://t.me/lyaguha_logs"))
        btn_zapret = QPushButton("Открыть папку zapret")
        add_press_effect(btn_zapret)
        btn_zapret.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.zm.zapret_path))))
        btn_config = QPushButton("Открыть папку данных")
        add_press_effect(btn_config)
        btn_config.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_data_dir()))))
        actions.addWidget(btn_github)
        actions.addWidget(btn_releases)
        actions.addWidget(btn_telegram)
        actions.addWidget(btn_zapret)
        actions.addWidget(btn_config)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self, initial_update: AppUpdateInfo | None = None):
        super().__init__()
        self.config = load_config()
        self.initial_update = initial_update
        self.pending_app_update: AppUpdateInfo | None = None
        self._manual_update_check = False
        self.sidebar_expanded = False
        self.nav_specs = {
            "dpi": ("asset:assets/zapret_winws_icon.png", "DPI"),
            "telegram": ("asset:assets/tg_ws_proxy_icon.ico", "Telegram"),
            "settings": ("settings", "Настройки"),
            "about": ("about", "О приложении"),
        }

        app = QApplication.instance()
        apply_app_theme(app, self.config.get("theme", "system"))
        app.setStyleSheet(app_stylesheet(self.config.get("theme", "system")))

        self.setWindowTitle(get_display_name())
        self.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))
        self.setMinimumSize(980, 660)

        self.zapret_path = self._load_zapret_path()
        if not self.zapret_path or not (self.zapret_path / "service.bat").exists():
            self._run_first_setup()

        self.zm = ZapretManager(self.zapret_path)
        self.sc = ServiceController(self.zapret_path)
        self._build_ui()
        self._setup_tray()

        if initial_update and initial_update.is_newer:
            self._defer_update(initial_update)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_tray_status)
        self._status_timer.start(5000)

    def _load_zapret_path(self) -> Path | None:
        raw = self.config.get("zapret_path")
        return Path(raw) if raw else None

    def _save_config(self):
        self.config["zapret_path"] = str(self.zapret_path)
        save_config(self.config)

    def _run_first_setup(self):
        dlg = InstallDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.zapret_path = dlg.get_path()
            self._save_config()
        else:
            sys.exit(0)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(12, 10, 12, 10)
        self.sidebar_layout.setSpacing(8)
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.log_widget = LogWidget()
        self.strategy_widget = StrategyWidget(self.zm, self.sc, self.log_widget)
        self.telegram_page = TelegramPage()
        self.settings_page = SettingsPage(self.config, self.zapret_path)
        self.about_page = AboutPage(self.zm)
        self.strategy_widget.strategy_started.connect(self._remember_strategy)
        self.strategy_widget.status_changed.connect(self._on_strategy_status_changed)

        self.stack.addWidget(self.strategy_widget)
        self.stack.addWidget(self.telegram_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.about_page)

        self.settings_page.theme_changed.connect(self._apply_theme)
        self.settings_page.config_changed.connect(self._on_config_changed)
        self.settings_page.check_updates_requested.connect(self._check_app_updates)
        self.settings_page.install_update_requested.connect(self._install_app_update)
        self.settings_page.skip_update_requested.connect(self._skip_app_update)
        self.settings_page.zapret_path_changed.connect(self._change_zapret_path)
        self.settings_page.data_dir_changed.connect(self._on_data_dir_changed)

        self._build_sidebar()
        self._switch_page("dpi")
        self._on_config_changed()

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("zapret.gui")
        except Exception:
            pass

    def _build_sidebar(self):
        self._clear_layout(self.sidebar_layout)
        width = 232 if self.sidebar_expanded else 74
        self._set_sidebar_width(width)

        top = QHBoxLayout()
        btn_menu = QPushButton("☰")
        btn_menu.setObjectName("IconButton")
        btn_menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(btn_menu)
        btn_menu.clicked.connect(self._toggle_sidebar)
        top.addWidget(btn_menu)
        self.menu_label = QLabel("Меню")
        self.menu_label.setObjectName("SectionTitle")
        self.menu_label.setVisible(self.sidebar_expanded)
        top.addWidget(self.menu_label)
        top.addStretch()
        self.sidebar_layout.addLayout(top)

        self.nav_buttons = {}
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for key in ["dpi", "telegram"]:
            icon_key, text = self.nav_specs[key]
            btn = self._nav_button(icon_key, text)
            btn.clicked.connect(lambda _=False, k=key: self._switch_page(k))
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            self.sidebar_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        self.sidebar_layout.addStretch()
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)
        for key in ["settings", "about"]:
            icon_key, text = self.nav_specs[key]
            btn = self._nav_button(icon_key, text)
            btn.clicked.connect(lambda _=False, k=key: self._switch_page(k))
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            bottom_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.sidebar_layout.addWidget(bottom)

    def _nav_button(self, icon_key: str, text: str) -> QPushButton:
        label = text if self.sidebar_expanded else ""
        btn = QPushButton(label)
        btn.setObjectName("NavButton")
        btn.setIcon(self._nav_icon(icon_key))
        btn.setIconSize(QSize(24, 24))
        btn.setCheckable(True)
        btn.setToolTip(text)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setProperty("expanded", self.sidebar_expanded)
        btn.setFixedHeight(48)
        if self.sidebar_expanded:
            btn.setMinimumWidth(196)
            btn.setMaximumWidth(196)
        else:
            btn.setFixedWidth(48)
        add_press_effect(btn)
        return btn

    def _nav_icon(self, icon_key: str) -> QIcon:
        if icon_key.startswith("asset:"):
            return QIcon(str(get_asset_path(icon_key.removeprefix("asset:"))))
        if icon_key == "settings":
            return self._settings_icon()
        if icon_key == "about":
            return self._about_icon()
        return QIcon()

    def _settings_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#111111"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        center = 32
        for index in range(8):
            angle = math.radians(index * 45)
            inner = 21
            outer = 27
            painter.drawLine(
                int(center + math.cos(angle) * inner),
                int(center + math.sin(angle) * inner),
                int(center + math.cos(angle) * outer),
                int(center + math.sin(angle) * outer),
            )
        painter.drawEllipse(17, 17, 30, 30)
        painter.drawEllipse(27, 27, 10, 10)
        painter.end()
        return QIcon(pixmap)

    def _about_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#111111"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(13, 13, 38, 38)
        painter.drawPoint(32, 25)
        painter.drawLine(32, 32, 32, 42)
        painter.end()
        return QIcon(pixmap)

    def _toggle_sidebar(self):
        current = self._current_key()
        start_width = self.sidebar.width()
        self.sidebar_expanded = not self.sidebar_expanded
        end_width = 232 if self.sidebar_expanded else 74
        self._sync_sidebar_labels()

        self._sidebar_animation = QVariantAnimation(self)
        self._sidebar_animation.setStartValue(start_width)
        self._sidebar_animation.setEndValue(end_width)
        self._sidebar_animation.setDuration(210)
        self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sidebar_animation.valueChanged.connect(lambda value: self._set_sidebar_width(int(value)))
        self._sidebar_animation.finished.connect(lambda: self._mark_nav(current))
        self._sidebar_animation.start()

    def _sync_sidebar_labels(self):
        if hasattr(self, "menu_label"):
            self.menu_label.setVisible(self.sidebar_expanded)
        for key, btn in getattr(self, "nav_buttons", {}).items():
            icon_key, text = self.nav_specs[key]
            btn.setIcon(self._nav_icon(icon_key))
            btn.setIconSize(QSize(24, 24))
            btn.setText(text if self.sidebar_expanded else "")
            btn.setProperty("expanded", self.sidebar_expanded)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            if self.sidebar_expanded:
                btn.setMinimumWidth(196)
                btn.setMaximumWidth(196)
            else:
                btn.setMinimumWidth(48)
                btn.setMaximumWidth(48)

    def _set_sidebar_width(self, width: int):
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)

    def _current_key(self) -> str:
        idx = self.stack.currentIndex()
        return ["dpi", "telegram", "settings", "about"][idx] if 0 <= idx < 4 else "dpi"

    def _switch_page(self, key: str):
        mapping = {"dpi": 0, "telegram": 1, "settings": 2, "about": 3}
        self.stack.setCurrentIndex(mapping.get(key, 0))
        self._mark_nav(key)
        self._fade_current_page()

    def _mark_nav(self, key: str):
        for nav_key, btn in self.nav_buttons.items():
            btn.setChecked(nav_key == key)

    def _fade_current_page(self):
        widget = self.stack.currentWidget()
        if not widget:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        self._page_animation = QPropertyAnimation(effect, b"opacity", self)
        self._page_animation.setStartValue(0.0)
        self._page_animation.setEndValue(1.0)
        self._page_animation.setDuration(150)
        self._page_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._page_animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._page_animation.start()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _apply_theme(self, theme_name: str):
        app = QApplication.instance()
        apply_app_theme(app, theme_name)
        app.setStyleSheet(app_stylesheet(theme_name))

    def _on_config_changed(self):
        self.settings_page.refresh_banner()
        self.settings_page.refresh_storage_info()

    def _on_data_dir_changed(self):
        self.log_widget.reload_file_writer()
        reload_app_logger()
        self.settings_page.refresh_storage_info()

    def _setup_tray(self):
        self.tray = TrayManager(self)
        self.tray.show_window.connect(self._toggle_visible)
        self.tray.toggle_strategy.connect(self._toggle_strategy_from_tray)
        self.tray.quit_app.connect(self._quit)
        self.tray.show()
        self._update_tray_status()

    def _toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            if self.isMinimized() or self.isHidden():
                self.showNormal()
            else:
                self.show()
            if self.centralWidget():
                self.centralWidget().updateGeometry()
            self.activateWindow()
            self.raise_()

    def _update_tray_status(self):
        if hasattr(self, "zm"):
            self.strategy_widget._update_status(auto_detect=True)

    def _on_strategy_status_changed(self, title: str, detail: str, color: str, button: str, busy: bool):
        if hasattr(self, "tray"):
            self.tray.set_state(title, detail, color, button, busy)

    def _remember_strategy(self, strategy_name: str, mode: str):
        self.config["last_strategy"] = strategy_name
        self.config["last_strategy_mode"] = "service" if mode == "service" else "process"
        save_config(self.config)

    def _toggle_strategy_from_tray(self):
        if self.zm.is_running():
            self.strategy_widget.stop_current_strategy()
            self._update_tray_status()
            return

        strategy_name = self.config.get("last_strategy", "")
        mode = self.config.get("last_strategy_mode", "process")
        if self.strategy_widget.start_last_strategy(strategy_name, mode):
            self._switch_page("dpi")
        else:
            self._switch_page("dpi")
            self._show_window()
        self._update_tray_status()

    def _show_window(self):
        if self.isMinimized() or self.isHidden():
            self.showNormal()
        else:
            self.show()
        if self.centralWidget():
            self.centralWidget().updateGeometry()
        self.activateWindow()
        self.raise_()

    def maybe_check_app_updates(self):
        if not self.config.get("app_auto_update_enabled", True):
            return
        today = date.today().isoformat()
        if self.config.get("last_app_update_check") == today:
            return
        self.config["last_app_update_check"] = today
        save_config(self.config)
        self._check_app_updates(manual=False)

    def _check_app_updates(self, manual: bool = True):
        self._manual_update_check = manual
        include_prerelease = self.config.get("app_update_include_prerelease", False)
        require_assets = bool(getattr(sys, "frozen", False))
        self.settings_page.lbl_update_status.setText("Проверяем обновления...")
        self.settings_page.set_update_checking(True)
        self.settings_page.set_update_progress(False)
        self._app_update_worker = AppUpdateWorker(include_prerelease, require_assets)
        self._app_update_worker.finished_signal.connect(self._on_app_update_checked)
        self._app_update_worker.start()

    def _on_app_update_checked(self, info, error: str):
        self.settings_page.set_update_checking(False)
        if error:
            self.settings_page.show_update_error(error)
            log_app_event("error", "app-update", f"Update check failed: {error}")
            return
        if info and info.is_newer:
            if (
                not self._manual_update_check
                and self.config.get("skipped_app_version") == info.latest_version
            ):
                self.settings_page.lbl_update_status.setText("Найденная версия пропущена.")
                return
            self.pending_app_update = info
            self._defer_update(info)
            self.settings_page.show_update_available(info)
        else:
            self.pending_app_update = None
            if self.config.get("deferred_app_update"):
                self.config["deferred_app_update"] = None
                save_config(self.config)
                self.settings_page.refresh_banner()
            self.settings_page.show_no_update()

    def _install_app_update(self):
        if not self.pending_app_update:
            return

        if not getattr(sys, "frozen", False):
            webbrowser.open(self.pending_app_update.release_url)
            self.settings_page.lbl_update_status.setText("Автоустановка доступна только для portable .exe.")
            return

        reply = QMessageBox.warning(
            self,
            "Обновить zapret-gui",
            "Приложение скачает обновление, проверит SHA256, закроется, заменит exe и перезапустится.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return

        self.settings_page.set_update_checking(True)
        self.settings_page.set_update_progress(True, 0)
        updates_dir = get_data_dir() / "updates"
        self._app_update_install_worker = AppUpdateInstallWorker(self.pending_app_update, updates_dir)
        self._app_update_install_worker.progress.connect(lambda value: self.settings_page.set_update_progress(True, value))
        self._app_update_install_worker.finished_signal.connect(self._on_app_update_downloaded)
        self._app_update_install_worker.start()

    def _on_app_update_downloaded(self, new_exe, error: str):
        self.settings_page.set_update_checking(False)
        if error:
            self.settings_page.set_update_progress(False)
            self.settings_page.lbl_update_status.setText(f"Не удалось установить: {error}")
            log_app_event("error", "app-update", f"Update install failed: {error}")
            return
        try:
            launch_update_helper(Path(new_exe), get_gui_logs_dir())
        except Exception as e:
            self.settings_page.set_update_progress(False)
            self.settings_page.lbl_update_status.setText(f"Не удалось запустить установщик: {e}")
            log_app_event("error", "app-update", f"Could not launch update helper: {e}")
            return
        log_app_event("info", "app-update", "Update helper launched")
        self.tray.hide()
        QApplication.quit()

    def _skip_app_update(self):
        if not self.pending_app_update:
            return
        self.config["skipped_app_version"] = self.pending_app_update.latest_version
        self.config["deferred_app_update"] = None
        save_config(self.config)
        self.pending_app_update = None
        self.settings_page._set_update_actions_visible(False)
        self.settings_page.refresh_banner()
        self.settings_page.lbl_update_status.setText("Версия пропущена.")

    def _defer_update(self, info: AppUpdateInfo):
        self.config["deferred_app_update"] = {
            "latest_version": info.latest_version,
            "release_url": info.release_url,
            "is_prerelease": info.is_prerelease,
        }
        save_config(self.config)
        self.settings_page.refresh_banner()

    def _change_zapret_path(self, path: Path):
        self.zapret_path = path
        self.zm = ZapretManager(path)
        self.sc = ServiceController(path)
        self.strategy_widget.rebind(self.zm, self.sc)

    def closeEvent(self, event):
        if self.config.get("stay_open_on_close", True):
            event.ignore()
            self.hide()
            self.tray.tray.showMessage(APP_NAME, "Приложение осталось в трее", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self.tray.hide()
            QApplication.quit()
            event.accept()

    def _quit(self):
        self.tray.hide()
        QApplication.quit()
