import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import qInstallMessageHandler

from gui.config import get_gui_logs_dir


class AppLogger:
    def __init__(self):
        self.logs_dir = get_gui_logs_dir()
        self._old_excepthook = None
        self._old_threading_hook = None
        self._old_qt_handler = None

    def reload(self):
        self.logs_dir = get_gui_logs_dir()

    def log(self, level: str, source: str, message: str):
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now()
            path = self.logs_dir / f"zapret-gui-app-{stamp:%Y-%m-%d}.log"
            text = f"[{stamp:%Y-%m-%d %H:%M:%S}] [{level.upper()}] {source}: {message}\n"
            with path.open("a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def install_hooks(self):
        if self._old_excepthook is None:
            self._old_excepthook = sys.excepthook
        if self._old_threading_hook is None:
            self._old_threading_hook = threading.excepthook

        sys.excepthook = self._handle_exception
        threading.excepthook = self._handle_thread_exception
        self._old_qt_handler = qInstallMessageHandler(self._handle_qt_message)
        self.log("info", "app", "Application logger initialized")

    def _handle_exception(self, exc_type, exc_value, exc_tb):
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).strip()
        self.log("error", "sys.excepthook", formatted)
        if self._old_excepthook:
            self._old_excepthook(exc_type, exc_value, exc_tb)

    def _handle_thread_exception(self, args):
        formatted = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)).strip()
        self.log("error", f"thread:{getattr(args.thread, 'name', 'unknown')}", formatted)
        if self._old_threading_hook:
            self._old_threading_hook(args)

    def _handle_qt_message(self, mode, context, message):
        source = "qt"
        if context and context.file:
            source = f"qt:{Path(context.file).name}:{context.line}"
        self.log("qt", source, message)
        if self._old_qt_handler:
            self._old_qt_handler(mode, context, message)


_LOGGER = AppLogger()


def install_app_logger():
    _LOGGER.reload()
    _LOGGER.install_hooks()


def reload_app_logger():
    _LOGGER.reload()
    _LOGGER.log("info", "app", "Application logger reloaded")


def log_app_event(level: str, source: str, message: str):
    _LOGGER.log(level, source, message)
