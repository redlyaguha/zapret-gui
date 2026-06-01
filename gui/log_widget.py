from PySide6.QtWidgets import QFrame, QWidget, QVBoxLayout, QScrollArea
from PySide6.QtCore import Signal, QDateTime, Qt
from typing import Optional


class LogWidget(QWidget):
    log_received = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setObjectName("LogFrame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("LogScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(74)
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10, 8, 10, 8)
        self.scroll_layout.setAlignment(self._align_top())
        self.scroll_layout.setSpacing(4)
        self.scroll.setWidget(self.scroll_content)
        frame_layout.addWidget(self.scroll)
        layout.addWidget(self.frame)

        self.log_received.connect(self._append_log_line)

    def _align_top(self):
        from PySide6.QtCore import Qt
        return Qt.AlignmentFlag.AlignTop

    def log(self, message: str, level: str = "info"):
        ts = QDateTime.currentDateTime().toString("HH:mm:ss")
        html = f'<span style="color:#8b95a7;">[{ts}]</span> '
        if level == "ok":
            html += f'<span style="color:#53d18a;">{message}</span>'
        elif level == "error":
            html += f'<span style="color:#ff6b6b;">{message}</span>'
        elif level == "warn":
            html += f'<span style="color:#ffbd4a;">{message}</span>'
        elif level == "system":
            html += f'<span style="color:#58a6ff;">{message}</span>'
        else:
            html += f'<span style="color:#d9dee8;">{message}</span>'
        html += "<br>"
        self.log_received.emit(html, "")

    def _append_log_line(self, html: str, _):
        from PySide6.QtWidgets import QLabel
        label = QLabel(html)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet("padding: 1px 4px; background: transparent;")
        label.setMaximumWidth(self.scroll.width() - 30)
        self.scroll_layout.addWidget(label)
        self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        )

    def clear_log(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
