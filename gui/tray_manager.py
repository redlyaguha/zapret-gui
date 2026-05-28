from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject

from core.app_info import get_display_name
from core.assets import get_asset_path


class TrayManager(QObject):
    show_window = Signal()
    quit_app = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.icon = QIcon(str(get_asset_path("assets/app_icon.ico")))
        self.tray = QSystemTrayIcon(parent)
        self.tray.setIcon(self.icon)
        self.tray.setToolTip(get_display_name())

        self.menu = QMenu(parent)
        self.action_show = QAction("Show/Hide", parent)
        self.action_show.triggered.connect(self.show_window)
        self.action_quit = QAction("Exit", parent)
        self.action_quit.triggered.connect(self.quit_app)

        self.menu.addAction(self.action_show)
        self.menu.addSeparator()
        self.menu.addAction(self.action_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)

    def show(self):
        self.tray.show()

    def hide(self):
        self.tray.hide()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window.emit()

    def set_status(self, running: bool):
        status = "Running" if running else "Stopped"
        self.tray.setToolTip(f"{get_display_name()} - {status}")
