from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea
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

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { border: 1px solid #333; background: #1e1e1e; }
        """)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(self._align_top())
        self.scroll_layout.setSpacing(2)
        self.scroll.setWidget(self.scroll_content)

        btn_layout = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_log)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_clear)

        layout.addWidget(self.scroll)
        layout.addLayout(btn_layout)

        self.log_received.connect(self._append_log_line)

    def _align_top(self):
        from PySide6.QtCore import Qt
        return Qt.AlignmentFlag.AlignTop

    def log(self, message: str, level: str = "info"):
        ts = QDateTime.currentDateTime().toString("HH:mm:ss")
        html = f'<span style="color:#888;">[{ts}]</span> '
        if level == "ok":
            html += f'<span style="color:#4caf50;">{message}</span>'
        elif level == "error":
            html += f'<span style="color:#f44336;">{message}</span>'
        elif level == "warn":
            html += f'<span style="color:#ff9800;">{message}</span>'
        elif level == "system":
            html += f'<span style="color:#64b5f6;">{message}</span>'
        else:
            html += f'<span style="color:#ccc;">{message}</span>'
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
