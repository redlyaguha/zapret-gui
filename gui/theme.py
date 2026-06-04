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
        "bg": "#f8fafc",
        "panel": "rgba(255, 255, 255, 242)",
        "panel_solid": "#ffffff",
        "panel_soft": "#f3f6fa",
        "sidebar": "rgba(255, 255, 255, 246)",
        "text": "#172033",
        "muted": "#667085",
        "border": "rgba(26, 33, 48, 24)",
        "accent": "#0a84ff",
        "accent_soft": "rgba(10, 132, 255, 34)",
        "success": "#178f54",
        "warning": "#b66b00",
        "danger": "#c73838",
        "field": "#f1f4f8",
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
    QLabel#SettingLabel {{
        font-size: 14px;
        font-weight: 400;
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
        border-color: {c["border"]};
    }}
    QPushButton[pressEffect="true"]:pressed {{
        background: {c["accent_soft"]};
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
    QPushButton#PrimaryButton:pressed {{
        background: {c["accent"]};
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
        font-size: 15px;
        font-weight: 700;
        min-height: 48px;
        max-height: 48px;
    }}
    QPushButton#NavButton[expanded="true"] {{
        padding: 0;
    }}
    QPushButton#IconButton {{
        min-width: 48px;
        max-width: 48px;
        min-height: 48px;
        max-height: 48px;
        padding: 0;
        border-radius: 18px;
        text-align: center;
    }}
    QPushButton#SelectButton {{
        min-height: 36px;
        max-height: 36px;
        min-width: 270px;
        padding: 0 14px;
        border-radius: 18px;
        text-align: left;
        background: {c["field"]};
    }}
    QPushButton#SelectButton:hover {{
        background: {c["panel_soft"]};
        border-color: {c["accent"]};
    }}
    QPushButton#SelectButton:pressed {{
        background: {c["field"]};
        border-color: {c["accent"]};
    }}
    QPushButton#SelectButton:disabled {{
        color: rgba(127, 139, 156, 92);
        background: rgba(127, 139, 156, 20);
        border-color: rgba(127, 139, 156, 45);
    }}
    QPushButton#SelectButton::menu-indicator {{
        image: none;
        width: 0;
    }}
    QFrame#SelectPopup {{
        background: {c["panel_solid"]};
        border: 1px solid {c["border"]};
        border-radius: 16px;
    }}
    QPushButton#SelectMenuItem {{
        border: 0;
        background: transparent;
        border-radius: 11px;
        padding: 0 14px;
        text-align: left;
        min-height: 34px;
        max-height: 34px;
        font-weight: 600;
    }}
    QPushButton#SelectMenuItem:hover {{
        background: {c["accent_soft"]};
        border: 0;
    }}
    QPushButton#SelectMenuItem[selected="true"] {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QPushButton#CompactButton {{
        min-height: 30px;
        max-height: 34px;
        padding: 3px 12px;
        border-radius: 15px;
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
    QFrame#SegmentedTrack {{
        background: {c["field"]};
        border: 1px solid {c["border"]};
        border-radius: 20px;
    }}
    QFrame#SegmentThumb {{
        background: {c["accent"]};
        border-radius: 18px;
    }}
    QPushButton#SegmentFlat {{
        border: 0;
        background: transparent;
        border-radius: 18px;
        font-weight: 700;
    }}
    QPushButton#SegmentFlat:checked {{
        color: white;
    }}
    QPushButton#SegmentFlat:pressed {{
        background: transparent;
    }}
    QComboBox, QTextEdit, QListWidget {{
        background: {c["field"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
        padding: 6px;
        selection-background-color: {c["accent"]};
    }}
    QFrame#LogFrame {{
        border-radius: 16px;
        background: {c["field"]};
        border: 1px solid {c["border"]};
    }}
    QScrollArea#LogScroll {{
        border: 0;
        border-radius: 16px;
        background: transparent;
    }}
    QScrollArea#LogScroll > QWidget > QWidget {{
        background: transparent;
    }}
    QTextEdit#DetailsText {{
        border: 0;
        border-radius: 14px;
        background: {c["field"]};
        padding: 10px;
    }}
    QComboBox {{
        min-height: 26px;
        max-height: 34px;
        padding: 3px 8px;
        min-width: 190px;
    }}
    QComboBox:disabled {{
        color: rgba(127, 139, 156, 92);
        background: rgba(127, 139, 156, 20);
        border-color: rgba(127, 139, 156, 45);
    }}
    QComboBox::drop-down {{
        border: 0;
        width: 28px;
        border-top-right-radius: 14px;
        border-bottom-right-radius: 14px;
        background: rgba(127, 139, 156, 20);
    }}
    QComboBox::drop-down:disabled {{
        background: rgba(127, 139, 156, 14);
    }}
    QComboBox QAbstractItemView {{
        background: {c["panel_solid"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
        padding: 6px;
        selection-background-color: {c["accent_soft"]};
    }}
    QMenu {{
        background: {c["panel_solid"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 14px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 28px 8px 12px;
        border-radius: 10px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c["border"]};
        margin: 5px 8px;
    }}
    QListWidget::item {{
        padding: 10px 12px;
        margin: 3px 4px;
        border-radius: 11px;
    }}
    QListWidget::item:selected {{
        background: {c["accent_soft"]};
        color: {c["text"]};
        border: 0;
    }}
    QScrollArea {{
        border: 0;
        background: transparent;
    }}
    QScrollBar:vertical {{
        width: 10px;
        background: transparent;
        margin: 8px 3px 8px 3px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(127, 139, 156, 90);
        min-height: 34px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba(127, 139, 156, 135);
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
        border: 0;
        background: transparent;
    }}
    QScrollBar:horizontal {{
        height: 10px;
        background: transparent;
        margin: 3px 8px 3px 8px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(127, 139, 156, 90);
        min-width: 34px;
        border-radius: 5px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal,
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
        border: 0;
        background: transparent;
    }}
    QCheckBox {{
        spacing: 11px;
        min-height: 30px;
        padding: 1px 0;
    }}
    QCheckBox:checked {{
        color: {c["text"]};
    }}
    QCheckBox:unchecked {{
        color: {c["muted"]};
    }}
    QCheckBox:disabled {{
        color: rgba(127, 139, 156, 100);
    }}
    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 6px;
        border: 1px solid {c["border"]};
        background: {c["field"]};
    }}
    QCheckBox::indicator:disabled {{
        border-color: rgba(127, 139, 156, 55);
        background: rgba(127, 139, 156, 22);
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
