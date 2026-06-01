from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)

from core.diagnostics import run_diagnostics
from core.strategy_parser import find_strategies, parse_strategy
from gui.effects import add_press_effect


POLL_INTERVAL_MS = 1500
POLL_MAX_ATTEMPTS = 15


class SegmentedSwitch(QFrame):
    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.labels = labels
        self._index = 0
        self.setObjectName("SegmentedTrack")
        self.setFixedSize(236, 42)

        self.thumb = QFrame(self)
        self.thumb.setObjectName("SegmentThumb")
        self.thumb.lower()

        self.buttons = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        for idx, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setObjectName("SegmentFlat")
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _=False, i=idx: self.set_index(i))
            self.group.addButton(btn, idx)
            self.buttons.append(btn)
            layout.addWidget(btn)
        self.buttons[0].setChecked(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_thumb(animated=False)

    def set_index(self, index: int, emit=True):
        if index == self._index:
            return
        self._index = index
        self.buttons[index].setChecked(True)
        self._place_thumb(animated=True)
        if emit:
            self.changed.emit(index)

    def _thumb_rect(self) -> QRect:
        width = (self.width() - 6) // len(self.labels)
        return QRect(3 + width * self._index, 3, width, self.height() - 6)

    def _place_thumb(self, animated: bool):
        rect = self._thumb_rect()
        self.thumb.raise_()
        for button in self.buttons:
            button.raise_()
        if animated:
            self._animation = QPropertyAnimation(self.thumb, b"geometry", self)
            self._animation.setStartValue(self.thumb.geometry())
            self._animation.setEndValue(rect)
            self._animation.setDuration(170)
            self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._animation.start()
        else:
            self.thumb.setGeometry(rect)


class DropdownSelect(QPushButton):
    changed = Signal(int)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = options
        self._index = 0
        self._popup = None
        self.setObjectName("SelectButton")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(40)
        self.setMinimumWidth(280)
        self.clicked.connect(self._open_menu)
        self._sync_text()

    def set_index(self, index: int, emit=True):
        if index < 0 or index >= len(self.options):
            return
        if index == self._index:
            self._sync_text()
            return
        self._index = index
        self._sync_text()
        if emit:
            self.changed.emit(index)

    def _sync_text(self):
        self.setText(f"{self.options[self._index]}  ▾")

    def _open_menu(self):
        if self._popup and self._popup.isVisible():
            self._popup.close()
            return

        popup = QWidget(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        popup.destroyed.connect(lambda: setattr(self, "_popup", None))
        popup.setMinimumWidth(self.width())
        popup.setMaximumWidth(max(self.width(), 320))

        outer = QVBoxLayout(popup)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("SelectPopup")
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)
        for idx, label in enumerate(self.options):
            item = QPushButton(label)
            item.setObjectName("SelectMenuItem")
            item.setProperty("selected", idx == self._index)
            item.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            item.setFixedHeight(38)
            item.clicked.connect(lambda _=False, i=idx, p=popup: self._choose(i, p))
            layout.addWidget(item)

        self._popup = popup
        popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        popup.show()

    def _choose(self, index: int, popup: QWidget):
        self.set_index(index)
        popup.close()


class StrategyWidget(QWidget):
    def __init__(self, zapret_manager, service_controller, log_widget, parent=None):
        super().__init__(parent)
        self.zm = zapret_manager
        self.sc = service_controller
        self.log = log_widget
        self.strategies = []
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._on_poll_tick)
        self._poll_attempts = 0
        self._poll_target = None
        self._state = "idle"
        self._pending_strategy_name = None
        self._last_error = None
        self._details_visible = False
        self._logs_expanded = False
        self.game_modes = ["disabled", "all", "tcp", "udp"]
        self.ipset_modes = ["loaded", "none", "any"]
        self._build_ui()
        self.refresh()
        self._auto_set_mode()

    def rebind(self, zapret_manager, service_controller):
        self.zm = zapret_manager
        self.sc = service_controller
        self.refresh()
        self._auto_set_mode()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("DPI")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Управление обходом DPI для выбранной стратегии zapret.")
        subtitle.setObjectName("Muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        root.addLayout(header)

        status_panel = QFrame()
        status_panel.setObjectName("GlassPanel")
        status_panel.setMinimumHeight(172)
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_layout.setSpacing(12)
        self.lbl_status = QLabel("Отключено")
        self.lbl_status.setObjectName("HeroTitle")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status_detail = QLabel("Выберите стратегию и нажмите «Включить».")
        self.lbl_status_detail.setObjectName("Muted")
        self.lbl_status_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_power = QPushButton("Включить")
        self.btn_power.setObjectName("PrimaryButton")
        self.btn_power.setFixedHeight(52)
        self.btn_power.setMinimumWidth(320)
        self.btn_power.setMaximumWidth(620)
        self.btn_power.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_power.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(self.btn_power)
        self.btn_power.clicked.connect(self._toggle_power)
        status_layout.addWidget(self.lbl_status)
        status_layout.addWidget(self.lbl_status_detail)
        status_layout.addWidget(self.btn_power, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(status_panel)

        strategy_panel = QFrame()
        strategy_panel.setObjectName("GlassPanel")
        self.strategy_panel = strategy_panel
        self.strategy_panel.setMinimumHeight(360)
        strategy_layout = QVBoxLayout(strategy_panel)
        strategy_layout.setContentsMargins(16, 14, 16, 16)
        strategy_layout.setSpacing(12)
        strategy_title = QLabel("Стратегия")
        strategy_title.setObjectName("SectionTitle")
        strategy_layout.addWidget(strategy_title)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Режим запуска"), 1)
        self.mode_switch = SegmentedSwitch(["Процесс", "Служба"])
        self.mode_switch.changed.connect(self._on_mode_change)
        mode_row.addWidget(self.mode_switch)
        strategy_layout.addLayout(mode_row)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(156)
        self.list_widget.currentRowChanged.connect(self._on_select)
        strategy_layout.addWidget(self.list_widget)

        actions = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить список")
        self.btn_refresh.setFixedHeight(38)
        self.btn_refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(self.btn_refresh)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_details = QPushButton("Подробности")
        self.btn_details.setFixedHeight(38)
        self.btn_details.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(self.btn_details)
        self.btn_details.setCheckable(True)
        self.btn_details.clicked.connect(self._toggle_details)
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_details)
        actions.addStretch()
        strategy_layout.addLayout(actions)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setVisible(False)
        self.details.setObjectName("DetailsText")
        self.details.setMinimumHeight(148)
        strategy_layout.addWidget(self.details)
        root.addWidget(strategy_panel, 1)

        filter_panel = QFrame()
        filter_panel.setObjectName("GlassPanel")
        filter_panel.setMinimumHeight(212)
        filter_layout = QVBoxLayout(filter_panel)
        filter_layout.setContentsMargins(16, 16, 16, 18)
        filter_layout.setSpacing(16)
        filter_title = QLabel("Фильтры")
        filter_title.setObjectName("SectionTitle")
        filter_layout.addWidget(filter_title)

        self.lbl_game = QLabel("Game Filter: —")
        self.game_select = DropdownSelect(["Выключен", "TCP и UDP", "Только TCP", "Только UDP"])
        self.game_select.changed.connect(self._set_game)
        filter_layout.addWidget(self._setting_row(self.lbl_game, self.game_select))

        self.lbl_ipset = QLabel("IPSet: —")
        self.ipset_select = DropdownSelect(["Загруженный список", "Отключить список", "Любой IP"])
        self.ipset_select.changed.connect(self._set_ipset)
        filter_layout.addWidget(self._setting_row(self.lbl_ipset, self.ipset_select))

        self.chk_autoupdate = QCheckBox("Проверять обновления zapret при запуске zapret")
        self.chk_autoupdate.toggled.connect(self._toggle_autoupdate)
        filter_layout.addWidget(self.chk_autoupdate)

        tools_row = QHBoxLayout()
        self.btn_diagnostics = QPushButton("Диагностика")
        self.btn_diagnostics.setObjectName("CompactButton")
        self.btn_diagnostics.setFixedHeight(36)
        self.btn_diagnostics.setMaximumWidth(150)
        self.btn_diagnostics.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(self.btn_diagnostics)
        self.btn_diagnostics.clicked.connect(self._run_diagnostics)
        tools_row.addWidget(self.btn_diagnostics)
        tools_row.addStretch()
        filter_layout.addLayout(tools_row)
        root.addWidget(filter_panel)

        log_panel = QFrame()
        log_panel.setObjectName("GlassPanel")
        self.log_panel = log_panel
        self.log_panel.setMinimumHeight(172)
        self.log_panel.setMaximumHeight(172)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(14, 12, 14, 14)
        log_header = QHBoxLayout()
        log_title = QLabel("Расширенные логи")
        log_title.setObjectName("SectionTitle")
        self.btn_expand_logs = QPushButton("Раскрыть")
        self.btn_expand_logs.setFixedHeight(34)
        self.btn_expand_logs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(self.btn_expand_logs)
        self.btn_expand_logs.clicked.connect(self._toggle_logs)
        self.btn_clear_logs = QPushButton("Очистить")
        self.btn_clear_logs.setFixedHeight(34)
        self.btn_clear_logs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add_press_effect(self.btn_clear_logs)
        self.btn_clear_logs.clicked.connect(self.log.clear_log)
        log_header.addWidget(log_title)
        log_header.addStretch()
        log_header.addWidget(self.btn_clear_logs)
        log_header.addWidget(self.btn_expand_logs)
        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log)
        root.addWidget(log_panel)
        root.addStretch()

    def _toggle_logs(self):
        self._logs_expanded = not self._logs_expanded
        target = 390 if self._logs_expanded else 172
        self.btn_expand_logs.setText("Свернуть" if self._logs_expanded else "Раскрыть")
        self._log_min_animation = QPropertyAnimation(self.log_panel, b"minimumHeight", self)
        self._log_max_animation = QPropertyAnimation(self.log_panel, b"maximumHeight", self)
        for animation, start in (
            (self._log_min_animation, self.log_panel.minimumHeight()),
            (self._log_max_animation, self.log_panel.maximumHeight()),
        ):
            animation.setStartValue(start)
            animation.setEndValue(target)
            animation.setDuration(180)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.start()

    def _setting_row(self, label: QLabel, control: QWidget):
        row = QWidget()
        row.setObjectName("FilterRow")
        row.setFixedHeight(46)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(label, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return row

    def _on_mode_change(self, idx: int):
        self.zm.is_service_mode = idx == 1

    def refresh(self):
        self._state = "idle"
        self._last_error = None
        self._pending_strategy_name = None
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self.strategies = find_strategies(self.zm.zapret_path)
        for strategy in self.strategies:
            self.list_widget.addItem(strategy.stem)
        self.list_widget.blockSignals(False)
        if self.strategies:
            self.list_widget.setCurrentRow(0)
        else:
            self.details.setPlainText("Стратегии не найдены.")
        self._refresh_filters()
        self._update_status(auto_detect=True)

    def _auto_set_mode(self):
        is_service = self.zm._is_service_running()
        self.zm.is_service_mode = is_service
        self.mode_switch.set_index(1 if is_service else 0, emit=False)

    def _refresh_filters(self):
        self.game_select.blockSignals(True)
        self.ipset_select.blockSignals(True)
        self.chk_autoupdate.blockSignals(True)

        game_status = self.sc.game_filter_status()
        ipset_status = self.sc.ipset_filter_status()
        self.lbl_game.setText(f"Game Filter: {game_status}")
        self.lbl_ipset.setText(f"IPSet: {ipset_status}")
        game_idx = 0
        if "TCP and UDP" in game_status:
            game_idx = 1
        elif "(TCP)" in game_status:
            game_idx = 2
        elif "(UDP)" in game_status:
            game_idx = 3
        self.game_select.set_index(game_idx, emit=False)
        self.ipset_select.set_index(self.ipset_modes.index(ipset_status) if ipset_status in self.ipset_modes else 0, emit=False)
        self.chk_autoupdate.setChecked(self.sc.auto_update_status())

        self.game_select.blockSignals(False)
        self.ipset_select.blockSignals(False)
        self.chk_autoupdate.blockSignals(False)

    def _on_select(self, idx: int):
        if self._state == "error":
            self._state = "idle"
            self._last_error = None
        if 0 <= idx < len(self.strategies):
            info = parse_strategy(self.strategies[idx])
            args_text = "\n".join(info["args"]) if info["args"] else "Аргументы не найдены."
            self.details.setPlainText(args_text)
        self._update_status()

    def _toggle_details(self, checked: bool):
        self._details_visible = checked
        self.details.setVisible(checked)
        self.btn_details.setText("Скрыть подробности" if checked else "Подробности")
        self.strategy_panel.setMinimumHeight(548 if checked else 360)

    def _toggle_power(self):
        if self.zm.is_running() and self._state not in ("starting", "stopping"):
            self._stop()
        else:
            self._start()

    def _start(self):
        idx = self.list_widget.currentRow()
        if not (0 <= idx < len(self.strategies)):
            self._state = "error"
            self._last_error = "Выберите стратегию"
            self._update_status()
            return

        bat = self.strategies[idx]
        self._state = "starting"
        self._pending_strategy_name = bat.stem
        self._last_error = None
        self._update_status()
        mode = "служба" if self.zm.is_service_mode else "процесс"
        self.log.log(f"Запуск стратегии: {bat.stem} ({mode})", "system")
        try:
            self.zm.start_strategy(bat)
        except Exception as e:
            self._state = "error"
            self._last_error = str(e) or "Не удалось запустить"
            self._poll_timer.stop()
            self._poll_target = None
            self.log.log(f"Ошибка запуска: {self._last_error}", "error")
            self._update_status()
            return
        self._start_poll("start")

    def _stop(self):
        self._state = "stopping"
        self._last_error = None
        self._pending_strategy_name = self.zm.current_strategy
        self.log.log("Остановка winws.exe...", "system")
        try:
            self.zm.stop()
        except Exception as e:
            self._state = "error"
            self._last_error = str(e) or "Не удалось остановить"
            self._poll_timer.stop()
            self._poll_target = None
            self.log.log(f"Ошибка остановки: {self._last_error}", "error")
            self._update_status()
            return
        self._start_poll("stop")

    def _start_poll(self, target: str):
        self._poll_target = target
        self._poll_attempts = 0
        self._update_status()
        self._poll_timer.start(POLL_INTERVAL_MS)

    def _on_poll_tick(self):
        self._poll_attempts += 1
        running = self._update_status()
        target = self._poll_target

        if target == "start" and running:
            self._poll_timer.stop()
            self._poll_target = None
            self._state = "idle"
            self._pending_strategy_name = None
            self.log.log("Стратегия запущена", "ok")
            self._update_status()
        elif target == "stop" and not running:
            self._poll_timer.stop()
            self._poll_target = None
            self._state = "idle"
            self._pending_strategy_name = None
            self.log.log("Остановлено", "ok")
            self._update_status()
        elif self._poll_attempts >= POLL_MAX_ATTEMPTS:
            self._poll_timer.stop()
            self._poll_target = None
            self._last_error = "Таймаут запуска" if target == "start" else "Таймаут остановки"
            self.log.log(self._last_error, "error")
            self._state = "error"
            self._update_status()

    def _update_status(self, auto_detect=False):
        running = self.zm.is_running()
        if auto_detect and running and not self.zm.current_strategy:
            self.zm.detect_strategy()

        busy = self._state in ("starting", "stopping")
        self.btn_power.setEnabled(not busy)
        self.btn_refresh.setEnabled(not busy)
        self.list_widget.setEnabled(not busy and not running)

        if self._state == "starting":
            name = self._pending_strategy_name or "выбранная стратегия"
            self._set_status("Запускается", f"Готовим стратегию «{name}».", "#58a6ff", "Запускается")
        elif self._state == "stopping":
            self._set_status("Останавливается", "Останавливаем процесс и службы zapret.", "#58a6ff", "Останавливается")
        elif self._state == "error":
            self._set_status("Ошибка", self._last_error or "Операция не выполнена.", "#ff6b6b", "Повторить")
        elif running:
            current = self.zm.current_strategy
            if current == "__service__":
                detail = "Работает как Windows-служба."
            elif current:
                detail = f"Активная стратегия: {current}"
            else:
                detail = "zapret работает, но стратегия не определена."
            self._set_status("Работает", detail, "#53d18a", "Отключить")
        else:
            self._set_status("Отключено", "Выберите стратегию и нажмите «Включить».", "#a5adba", "Включить")

        self._highlight_current()
        return running

    def _set_status(self, title: str, detail: str, color: str, button: str):
        self.lbl_status.setText(title)
        self.lbl_status.setStyleSheet(f"color: {color};")
        self.lbl_status_detail.setText(detail)
        self.btn_power.setText(button)

    def _highlight_current(self):
        current = self.zm.current_strategy
        if self._state in ("starting", "stopping", "error"):
            current = self._pending_strategy_name or current

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setBackground(Qt.GlobalColor.transparent)

    def _set_game(self, idx: int):
        mode = self.game_modes[idx]
        self.sc.set_game_filter(mode)
        self.lbl_game.setText(f"Game Filter: {self.sc.game_filter_status()}")
        self.log.log(f"Game Filter: {mode}", "system")

    def _set_ipset(self, idx: int):
        mode = self.ipset_modes[idx]
        try:
            self.sc.set_ipset_filter(mode)
        except Exception as e:
            self.log.log(f"IPSet error: {e}", "error")
            QMessageBox.critical(self, "IPSet", f"Не удалось изменить IPSet:\n{e}")
            self._refresh_filters()
            return
        self.lbl_ipset.setText(f"IPSet: {self.sc.ipset_filter_status()}")
        self.log.log(f"IPSet: {mode}", "system")

    def _toggle_autoupdate(self, checked: bool):
        self.sc.set_auto_update(checked)
        self.log.log(f"Проверка обновлений zapret: {'включена' if checked else 'выключена'}", "system")

    def _run_diagnostics(self):
        results = run_diagnostics(self.zm.zapret_path)
        lines = [f"{name}: {status}" for name, status in results]
        for line in lines:
            self.log.log(line, "system")
        QMessageBox.information(self, "Диагностика", "\n".join(lines))
