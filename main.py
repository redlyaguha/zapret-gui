import sys
import os
import ctypes
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QVBoxLayout,
)

from core.app_info import APP_NAME, get_display_name
from core.assets import get_asset_path
from gui.config import (
    configure_data_dir, data_dir_from_parent, default_parent_dir,
    get_data_dir, has_configured_data_dir, load_config, save_config,
)
from gui.effects import add_press_effect
from gui.main_window import MainWindow
from gui.theme import apply_app_theme, app_stylesheet


class DataDirDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{get_display_name()} - папка данных")
        self.setFixedSize(620, 260)
        self.parent_path = default_parent_dir()
        self.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        title = QLabel("Выберите папку для настроек и логов")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("Приложение создаст внутри выбранной папки каталог zapret-gui-config.")
        subtitle.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        self.path_label = QLabel(str(self.parent_path))
        self.path_label.setObjectName("Pill")
        btn_browse = QPushButton("Выбрать")
        add_press_effect(btn_browse)
        btn_browse.clicked.connect(self._browse)
        row.addWidget(self.path_label, 1)
        row.addWidget(btn_browse)
        layout.addLayout(row)

        self.final_label = QLabel(f"Итоговый путь: {self.get_data_dir()}")
        self.final_label.setObjectName("Muted")
        layout.addWidget(self.final_label)

        actions = QHBoxLayout()
        actions.addStretch()
        btn_continue = QPushButton("Продолжить")
        btn_continue.setObjectName("PrimaryButton")
        add_press_effect(btn_continue)
        btn_continue.clicked.connect(self.accept)
        actions.addWidget(btn_continue)
        layout.addStretch()
        layout.addLayout(actions)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите родительскую папку", str(self.parent_path))
        if folder:
            self.parent_path = data_dir_from_parent(Path(folder)).parent
            self.path_label.setText(str(self.parent_path))
            self.final_label.setText(f"Итоговый путь: {self.get_data_dir()}")

    def get_data_dir(self):
        return data_dir_from_parent(self.parent_path)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))
    startup_tray = "--startup-tray" in sys.argv

    apply_app_theme(app, "system")
    app.setStyleSheet(app_stylesheet("system"))

    if not has_configured_data_dir() or not get_data_dir().exists():
        data_dir_dialog = DataDirDialog()
        if data_dir_dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        configure_data_dir(data_dir_dialog.get_data_dir(), migrate_legacy=True)

    config = load_config()
    save_config(config)
    apply_app_theme(app, config.get("theme", "system"))
    app.setStyleSheet(app_stylesheet(config.get("theme", "system")))

    window = MainWindow()
    if not startup_tray:
        window.show()
    QTimer.singleShot(250, lambda: maybe_prompt_admin_restart(window))
    QTimer.singleShot(500, window.maybe_check_app_updates)
    sys.exit(app.exec())


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def maybe_prompt_admin_restart(window: MainWindow):
    if is_admin():
        return
    reply = QMessageBox.question(
        window,
        "Права администратора",
        "Приложение запущено без прав администратора.\n\nПерезапустить от имени администратора?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return
    if restart_as_admin():
        QApplication.quit()


def restart_as_admin() -> bool:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    else:
        executable = sys.executable
        script = Path(sys.argv[0]).resolve()
        params = " ".join([f'"{script}"'] + [f'"{arg}"' for arg in sys.argv[1:]])
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    return result > 32


if __name__ == "__main__":
    main()
