from PySide6.QtCore import QObject, QEvent, QPropertyAnimation, QRect, QEasingCurve


class PressEffect(QObject):
    def __init__(self, button, parent=None):
        super().__init__(parent or button)
        self.button = button
        self._base_geometry = None
        self._animation = None
        button.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.button and event.type() == QEvent.Type.MouseButtonPress:
            self._base_geometry = self.button.geometry()
            self._animate(True)
        elif obj is self.button and event.type() in (
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.Leave,
        ):
            self._animate(False)
        return super().eventFilter(obj, event)

    def _animate(self, pressed: bool):
        if self._base_geometry is None:
            self._base_geometry = self.button.geometry()

        base = self._base_geometry
        if pressed:
            target = QRect(base.x() + 2, base.y() + 2, max(1, base.width() - 4), max(1, base.height() - 4))
        else:
            target = base

        self._animation = QPropertyAnimation(self.button, b"geometry", self)
        self._animation.setDuration(85 if pressed else 120)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(self.button.geometry())
        self._animation.setEndValue(target)
        self._animation.start()


def add_press_effect(button):
    effect = PressEffect(button)
    button._press_effect = effect
    return button
