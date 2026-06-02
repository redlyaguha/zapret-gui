from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject

from core.app_info import get_display_name
from core.assets import get_asset_path


class TrayManager(QObject):
    show_window = Signal()
    start_last_strategy = Signal()
    stop_strategy = Signal()
    quit_app = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.icon = QIcon(str(get_asset_path("assets/app_icon.ico")))
        self.tray = QSystemTrayIcon(parent)
        self.tray.setIcon(self.icon)
        self.tray.setToolTip(get_display_name())

        self.menu = QMenu(parent)
        self.menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                color: #172033;
                border: 1px solid rgba(26, 33, 48, 32);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 28px 8px 12px;
                border-radius: 9px;
                background: transparent;
            }
            QMenu::item:selected {
                background: rgba(10, 132, 255, 34);
                color: #172033;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(26, 33, 48, 32);
                margin: 5px 8px;
            }
        """)
        self.action_show = QAction("Показать / скрыть", parent)
        self.action_show.triggered.connect(lambda _checked=False: self.show_window.emit())
        self.action_status = QAction("Статус: отключено", parent)
        self.action_status.setEnabled(False)
        self.action_start_last = QAction("Включить последнюю стратегию", parent)
        self.action_start_last.triggered.connect(lambda _checked=False: self.start_last_strategy.emit())
        self.action_stop = QAction("Отключить", parent)
        self.action_stop.triggered.connect(lambda _checked=False: self.stop_strategy.emit())
        self.action_quit = QAction("Выход", parent)
        self.action_quit.triggered.connect(lambda _checked=False: self.quit_app.emit())

        self.menu.addAction(self.action_status)
        self.menu.addSeparator()
        self.menu.addAction(self.action_start_last)
        self.menu.addAction(self.action_stop)
        self.menu.addSeparator()
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
        status = "работает" if running else "отключено"
        self.action_status.setText(f"Статус: {status}")
        self.action_start_last.setEnabled(not running)
        self.action_stop.setEnabled(running)
        self.tray.setToolTip(f"{get_display_name()} - {status}")
