from pathlib import Path
import ctypes
import sys
import webbrowser

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QGraphicsOpacityEffect, QProgressBar, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
    QSystemTrayIcon,
)

from core.app_info import APP_NAME, APP_VERSION, GITHUB_REPO, get_display_name
from core.assets import get_asset_path
from core.service_controller import ServiceController
from core.zapret_manager import ZapretManager
from gui.app_update import AppUpdateInfo, check_app_update, open_releases
from gui.config import load_config, save_config
from gui.effects import add_press_effect
from gui.log_widget import LogWidget
from gui.strategy_widget import SegmentedSwitch, StrategyWidget
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

    def run(self):
        try:
            info = check_app_update()
            self.finished_signal.emit(info, "")
        except Exception as e:
            self.finished_signal.emit(None, str(e))


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    config_changed = Signal()
    check_updates_requested = Signal()
    zapret_path_changed = Signal(Path)

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
        row.addWidget(QLabel("Тема"), 1, Qt.AlignmentFlag.AlignVCenter)
        self.theme_values = ["system", "light", "dark"]
        self.theme_switch = SegmentedSwitch(["Системная", "Светлая", "Темная"])
        self.theme_switch.setFixedSize(330, 42)
        current_theme = self.config.get("theme", "system")
        self.theme_switch.set_index(self.theme_values.index(current_theme) if current_theme in self.theme_values else 0, emit=False)
        self.theme_switch.changed.connect(self._on_theme_change)
        row.addWidget(self.theme_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        app_l.addWidget(theme_row)

        behavior = self._panel("Поведение")
        behavior.setMinimumHeight(168)
        beh_l = behavior.layout()
        beh_l.setContentsMargins(18, 18, 18, 18)
        beh_l.setSpacing(7)
        self.chk_no_tray = QCheckBox("Не сворачивать в трей при закрытии окна")
        self.chk_no_tray.setChecked(not self.config.get("stay_open_on_close", True))
        self.chk_no_tray.toggled.connect(self._save_behavior)
        self.chk_startup = QCheckBox("Запускать вместе с Windows")
        self.chk_startup.setChecked(self.config.get("launch_on_startup", False))
        self.chk_startup.toggled.connect(self._save_behavior)
        self.chk_logs = QCheckBox("Показывать расширенные логи")
        self.chk_logs.toggled.connect(self._save_behavior)
        beh_l.addWidget(self._behavior_row(self.chk_no_tray))
        beh_l.addWidget(self._behavior_row(self.chk_startup))
        beh_l.addWidget(self._behavior_row(self.chk_logs))
        self._sync_behavior_controls()

        updates = self._panel("Обновления zapret-gui")
        upd_l = updates.layout()
        upd_row = QHBoxLayout()
        self.lbl_update_status = QLabel("Проверка выполняется только для приложения, не для zapret.")
        self.lbl_update_status.setObjectName("Muted")
        btn_check = QPushButton("Проверить обновления")
        add_press_effect(btn_check)
        btn_check.clicked.connect(self.check_updates_requested.emit)
        upd_row.addWidget(self.lbl_update_status, 1)
        upd_row.addWidget(btn_check)
        upd_l.addLayout(upd_row)

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
        root.addWidget(tools)
        root.addStretch()
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

    def _behavior_row(self, checkbox: QCheckBox) -> QWidget:
        row = QWidget()
        row.setObjectName("BehaviorRow")
        row.setFixedHeight(34)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        checkbox.setFixedHeight(30)
        checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(checkbox, 1, Qt.AlignmentFlag.AlignVCenter)
        row_layout.addStretch()
        return row

    def refresh_banner(self):
        info = self.config.get("deferred_app_update")
        self.update_banner.setVisible(bool(info))
        if info:
            self.update_text.setText(f"Доступно обновление zapret-gui: {info.get('latest_version', '')}")

    def _sync_behavior_controls(self):
        controls = (
            self.chk_no_tray,
            self.chk_startup,
            self.chk_logs,
        )
        for control in controls:
            control.blockSignals(True)
        self.chk_no_tray.setChecked(not self.config.get("stay_open_on_close", True))
        self.chk_startup.setChecked(self.config.get("launch_on_startup", False))
        self.chk_logs.setChecked(self.config.get("advanced_logs", True))
        for control in controls:
            control.blockSignals(False)

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
        self.config["stay_open_on_close"] = not self.chk_no_tray.isChecked()
        self.config["launch_on_startup"] = self.chk_startup.isChecked()
        self.config["advanced_logs"] = self.chk_logs.isChecked()
        self._set_startup(self.chk_startup.isChecked())
        save_config(self.config)
        self.config_changed.emit()

    def _set_startup(self, enabled: bool):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}"'
                else:
                    script = Path(sys.argv[0]).resolve()
                    command = f'"{sys.executable}" "{script}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.warning(self, "Автозапуск", f"Не удалось изменить автозапуск: {e}")

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
            "advanced_logs": True,
            "deferred_app_update": None,
        })
        save_config(self.config)
        self.theme_switch.set_index(0, emit=False)
        self._sync_behavior_controls()
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
            ("Сборка", "Portable Windows / исходники Python"),
        ]
        for row, (name, value) in enumerate(rows):
            label = QLabel(name)
            label.setObjectName("Muted")
            grid.addWidget(label, row, 0)
            grid.addWidget(QLabel(value), row, 1)
        layout.addWidget(panel)

        actions = QHBoxLayout()
        btn_github = QPushButton("GitHub")
        add_press_effect(btn_github)
        btn_github.clicked.connect(lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        btn_releases = QPushButton("Releases")
        add_press_effect(btn_releases)
        btn_releases.clicked.connect(open_releases)
        btn_zapret = QPushButton("Открыть папку zapret")
        add_press_effect(btn_zapret)
        btn_zapret.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.zm.zapret_path))))
        actions.addWidget(btn_github)
        actions.addWidget(btn_releases)
        actions.addWidget(btn_zapret)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self, initial_update: AppUpdateInfo | None = None):
        super().__init__()
        self.config = load_config()
        self.initial_update = initial_update
        self.sidebar_expanded = False
        self.nav_specs = {
            "dpi": ("D", "DPI"),
            "telegram": ("T", "Telegram"),
            "settings": ("⚙", "Настройки"),
            "about": ("i", "О приложении"),
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

        self.stack.addWidget(self.strategy_widget)
        self.stack.addWidget(self.telegram_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.about_page)

        self.settings_page.theme_changed.connect(self._apply_theme)
        self.settings_page.config_changed.connect(self._on_config_changed)
        self.settings_page.check_updates_requested.connect(self._check_app_updates)
        self.settings_page.zapret_path_changed.connect(self._change_zapret_path)

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
            icon, text = self.nav_specs[key]
            btn = self._nav_button(icon, text)
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
            icon, text = self.nav_specs[key]
            btn = self._nav_button(icon, text)
            btn.clicked.connect(lambda _=False, k=key: self._switch_page(k))
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            bottom_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self.sidebar_layout.addWidget(bottom)

    def _nav_button(self, icon: str, text: str) -> QPushButton:
        label = f"{icon}  {text}" if self.sidebar_expanded else icon
        btn = QPushButton(label)
        btn.setObjectName("NavButton")
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
            icon, text = self.nav_specs[key]
            btn.setText(f"{icon}  {text}" if self.sidebar_expanded else icon)
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
        self.log_widget.setVisible(self.config.get("advanced_logs", True))
        self.settings_page.refresh_banner()

    def _setup_tray(self):
        self.tray = TrayManager(self)
        self.tray.show_window.connect(self._toggle_visible)
        self.tray.quit_app.connect(self._quit)
        self.tray.show()

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
            self.tray.set_status(self.zm.is_running())

    def _check_app_updates(self):
        self.settings_page.lbl_update_status.setText("Проверяем обновления...")
        self._app_update_worker = AppUpdateWorker()
        self._app_update_worker.finished_signal.connect(self._on_app_update_checked)
        self._app_update_worker.start()

    def _on_app_update_checked(self, info, error: str):
        if error:
            self.settings_page.lbl_update_status.setText(f"Не удалось проверить: {error}")
            return
        if info and info.is_newer:
            self._defer_update(info)
            self.settings_page.lbl_update_status.setText(f"Доступна версия {info.latest_version}.")
        else:
            self.settings_page.lbl_update_status.setText("Установлена актуальная версия.")

    def _defer_update(self, info: AppUpdateInfo):
        self.config["deferred_app_update"] = {
            "latest_version": info.latest_version,
            "release_url": info.release_url,
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
