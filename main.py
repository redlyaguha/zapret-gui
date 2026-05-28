import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from core.assets import get_asset_path
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("zapret-gui")
    app.setOrganizationName("zapret-gui")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(get_asset_path("assets/app_icon.ico"))))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
