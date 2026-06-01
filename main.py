import sys
import os
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QVBoxLayout,
)

from core.app_info import APP_NAME, get_display_name
from core.assets import get_asset_path
from gui.app_update import check_app_update
from gui.config import load_config, save_config
from gui.effects import add_press_effect
from gui.main_window import MainWindow
from gui.theme import apply_app_theme, app_stylesheet


class StartupUpdateWorker(QThread):
    finished_signal = Signal(object, str)

    def run(self):
        try:
            info = check_app_update()
            self.finished_signal.emit(info, "")
        except Exception as e:
            self.finished_signal.emit(None, str(e))


class SplashDialog(QDialog):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.update_info = None
        self.setWindowTitle(get_display_name())
        self.setFixedSize(520, 320)
        self.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("zapret-gui")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("Проверяем обновления приложения и готовим интерфейс.")
        subtitle.setObjectName("Muted")
        self.status = QLabel("Проверка обновлений...")
        self.status.setObjectName("Muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        self.actions = QHBoxLayout()
        self.btn_update = QPushButton("Обновить сейчас")
        add_press_effect(self.btn_update)
        self.btn_update.clicked.connect(self._open_release)
        self.btn_later = QPushButton("Позже")
        add_press_effect(self.btn_later)
        self.btn_later.clicked.connect(self._later)
        self.btn_continue = QPushButton("Продолжить")
        self.btn_continue.setObjectName("PrimaryButton")
        add_press_effect(self.btn_continue)
        self.btn_continue.clicked.connect(self.accept)
        self.actions.addWidget(self.btn_update)
        self.actions.addWidget(self.btn_later)
        self.actions.addWidget(self.btn_continue)

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addLayout(self.actions)
        layout.addStretch()

        self._set_actions_visible(False)

    def start(self):
        self._worker = StartupUpdateWorker()
        self._worker.finished_signal.connect(self._on_checked)
        self._worker.start()

    def _on_checked(self, info, error: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        if error:
            self.status.setText("Не удалось проверить обновления. Продолжаем запуск.")
            QTimer.singleShot(700, self.accept)
            return
        if info and info.is_newer:
            self.update_info = info
            self.status.setText(f"Доступна новая версия zapret-gui: {info.latest_version}")
            self._set_actions_visible(True)
        else:
            self.status.setText("Установлена актуальная версия.")
            QTimer.singleShot(500, self.accept)

    def _set_actions_visible(self, visible: bool):
        for i in range(self.actions.count()):
            item = self.actions.itemAt(i)
            if item.widget():
                item.widget().setVisible(visible)

    def _open_release(self):
        if self.update_info:
            webbrowser.open(self.update_info.release_url)
            self._later()

    def _later(self):
        if self.update_info:
            self.config["deferred_app_update"] = {
                "latest_version": self.update_info.latest_version,
                "release_url": self.update_info.release_url,
            }
            save_config(self.config)
        self.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))

    config = load_config()
    apply_app_theme(app, config.get("theme", "system"))
    app.setStyleSheet(app_stylesheet(config.get("theme", "system")))

    splash = SplashDialog(config)
    QTimer.singleShot(80, splash.start)
    splash.exec()

    window = MainWindow(initial_update=splash.update_info)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
