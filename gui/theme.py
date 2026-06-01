import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


THEMES = {
    "dark": {
        "bg": "#111318",
        "panel": "rgba(34, 38, 48, 218)",
        "panel_solid": "#222630",
        "panel_soft": "#2c3240",
        "sidebar": "rgba(24, 27, 35, 232)",
        "text": "#f3f6fb",
        "muted": "#a5adba",
        "border": "rgba(255, 255, 255, 38)",
        "accent": "#58a6ff",
        "accent_soft": "rgba(88, 166, 255, 42)",
        "success": "#53d18a",
        "warning": "#ffbd4a",
        "danger": "#ff6b6b",
        "field": "rgba(255, 255, 255, 18)",
    },
    "light": {
        "bg": "#eef2f8",
        "panel": "rgba(255, 255, 255, 226)",
        "panel_solid": "#ffffff",
        "panel_soft": "#f4f7fb",
        "sidebar": "rgba(255, 255, 255, 234)",
        "text": "#172033",
        "muted": "#667085",
        "border": "rgba(26, 33, 48, 32)",
        "accent": "#0a84ff",
        "accent_soft": "rgba(10, 132, 255, 34)",
        "success": "#178f54",
        "warning": "#b66b00",
        "danger": "#c73838",
        "field": "rgba(23, 32, 51, 10)",
    },
}


def resolve_theme(theme_name: str) -> str:
    if theme_name == "system":
        if sys.platform.startswith("win"):
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                )
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "light" if int(value) else "dark"
            except Exception:
                pass
        palette = QApplication.palette()
        window = palette.color(QPalette.ColorRole.Window)
        return "dark" if window.lightness() < 128 else "light"
    return theme_name if theme_name in THEMES else "dark"


def palette(theme_name: str) -> dict:
    return THEMES[resolve_theme(theme_name)]


def apply_app_theme(app: QApplication, theme_name: str):
    colors = palette(theme_name)
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(colors["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(colors["panel_solid"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["panel_soft"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(colors["panel_solid"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)


def app_stylesheet(theme_name: str) -> str:
    c = palette(theme_name)
    return f"""
    QWidget {{
        color: {c["text"]};
        font-family: "Segoe UI", "Inter", Arial, sans-serif;
        font-size: 13px;
    }}
    QWidget:focus, QPushButton:focus, QComboBox:focus, QListWidget:focus, QTextEdit:focus {{
        outline: none;
    }}
    QMainWindow, QDialog {{
        background: {c["bg"]};
    }}
    #AppRoot {{
        background: {c["bg"]};
    }}
    #Sidebar {{
        background: {c["sidebar"]};
        border: 1px solid {c["border"]};
        border-radius: 22px;
    }}
    #GlassPanel, QGroupBox {{
        background: {c["panel"]};
        border: 1px solid {c["border"]};
        border-radius: 18px;
    }}
    QGroupBox {{
        margin-top: 12px;
        padding: 18px 14px 14px 14px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: {c["muted"]};
    }}
    QLabel#HeroTitle {{
        font-size: 28px;
        font-weight: 700;
    }}
    QLabel#PageTitle {{
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel#SectionTitle {{
        font-size: 15px;
        font-weight: 650;
    }}
    QLabel#Muted {{
        color: {c["muted"]};
    }}
    QLabel#Pill {{
        padding: 7px 10px;
        border-radius: 12px;
        background: {c["field"]};
        color: {c["muted"]};
    }}
    QPushButton {{
        min-height: 26px;
        max-height: 34px;
        padding: 4px 12px;
        border-radius: 17px;
        border: 1px solid {c["border"]};
        background: {c["panel_solid"]};
        color: {c["text"]};
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {c["accent_soft"]};
        border-color: {c["accent"]};
    }}
    QPushButton:pressed {{
        background: {c["panel_soft"]};
        padding-top: 6px;
        padding-bottom: 2px;
    }}
    QPushButton:disabled {{
        color: {c["muted"]};
        background: transparent;
    }}
    QPushButton#PrimaryButton {{
        min-height: 40px;
        max-height: 48px;
        padding: 4px 14px;
        border-radius: 24px;
        background: {c["accent"]};
        color: white;
        border: 0;
        font-size: 15px;
        font-weight: 700;
    }}
    QPushButton#DangerButton {{
        background: rgba(255, 107, 107, 38);
        color: {c["danger"]};
        border-radius: 17px;
    }}
    QPushButton#NavButton {{
        border: 0;
        background: transparent;
        text-align: center;
        padding: 0;
        border-radius: 17px;
        font-size: 15px;
        font-weight: 700;
        min-width: 44px;
        min-height: 44px;
        max-height: 44px;
    }}
    QPushButton#NavButton:checked {{
        background: {c["accent_soft"]};
        color: {c["accent"]};
    }}
    QPushButton#IconButton {{
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        max-height: 36px;
        padding: 0;
        border-radius: 13px;
        text-align: center;
    }}
    QPushButton#Segment {{
        border-radius: 17px;
        min-height: 28px;
        max-height: 34px;
        min-width: 88px;
        padding: 3px 10px;
        border: 0;
    }}
    QPushButton#Segment:checked {{
        background: {c["accent"]};
        color: white;
    }}
    QComboBox, QTextEdit, QListWidget {{
        background: {c["field"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
        padding: 5px;
        selection-background-color: {c["accent"]};
    }}
    QTextEdit#LogText, QScrollArea#LogScroll {{
        border-radius: 16px;
        background: {c["field"]};
    }}
    QComboBox {{
        min-height: 26px;
        max-height: 34px;
        padding: 3px 8px;
        min-width: 190px;
    }}
    QListWidget::item {{
        padding: 9px;
        border-radius: 10px;
    }}
    QListWidget::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QScrollArea {{
        border: 0;
        background: transparent;
    }}
    QScrollBar:vertical {{
        width: 12px;
        background: transparent;
        margin: 4px 2px 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]};
        min-height: 34px;
        border-radius: 6px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
        border: 0;
        background: transparent;
    }}
    QCheckBox {{
        spacing: 9px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 6px;
        border: 1px solid {c["border"]};
        background: {c["field"]};
    }}
    QCheckBox::indicator:hover {{
        border-color: {c["accent"]};
    }}
    QCheckBox::indicator:checked {{
        background: {c["accent"]};
        border-color: {c["accent"]};
    }}
    QProgressBar {{
        border: 1px solid {c["border"]};
        border-radius: 9px;
        background: {c["field"]};
        height: 12px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        border-radius: 8px;
        background: {c["accent"]};
    }}
    """
