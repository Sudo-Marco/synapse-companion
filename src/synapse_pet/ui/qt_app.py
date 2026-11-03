from __future__ import annotations

import queue
import sys
import threading
import time
from collections import deque
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (QEvent, QEasingCurve, QPoint, QPropertyAnimation,
                            QSettings, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QDesktopServices,
                           QFont, QGuiApplication, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap, QRegion, QSurfaceFormat, QShortcut,
                           QKeySequence)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from ..runtime.visual_state import VisualState
from .gl_renderer import EyeCanvas


BG = "#050a10"
PANEL = "#0c151e"
LINE = "#1a3440"
CYAN = "#3ed8e3"
GOLD = "#e9b725"
TEXT = "#d9e6e7"
MUTED = "#71878e"
SENSOR_LABELS = {
    "input_activity": "Contar atividade de teclado e mouse",
    "active_window": "Categorizar aplicativo em foco",
    "file_events": "Monitorar uma pasta escolhida",
    "clipboard": "Detectar mudança no clipboard",
    "system_stats": "Ler CPU e memória",
}


STYLESHEET = f"""
QMainWindow, QWidget#Root {{ background: {BG}; color: {TEXT}; }}
QFrame#Header, QFrame#Card, QFrame#Proposal {{ background: {PANEL}; border: 1px solid {LINE}; }}
QLabel {{ color: {TEXT}; }}
QLabel#Muted {{ color: {MUTED}; }}
QPushButton {{ background: #111d27; color: {TEXT}; border: 1px solid {LINE};
  border-radius: 3px; padding: 9px 12px; font: 700 9pt 'Segoe UI'; }}
QPushButton:hover {{ background: #183440; border-color: {CYAN}; }}
QPushButton#Love {{ background: #143438; color: #8ce6df; font-size: 10pt; }}
QPushButton#Love:hover {{ background: #20535a; }}
QPushButton#Negative {{ background: #29242c; color: #e5a69c; font-size: 10pt; }}
QPushButton#Negative:hover {{ background: #49323d; }}
QPushButton#Gold {{ color: {GOLD}; }}
QProgressBar {{ background: #17242d; border: 0; height: 7px; text-align: center; }}
QProgressBar::chunk {{ background: {CYAN}; }}
QMenu {{ background: #111a22; color: {TEXT}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background: #1e3e48; color: {CYAN}; }}
"""


def configure_opengl() -> None:
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    fmt.setSwapInterval(0)
    QSurfaceFormat.setDefaultFormat(fmt)


def ensure_application() -> QApplication:
    application = QApplication.instance()
    if application is None:
        configure_opengl()
        application = QApplication(sys.argv)
        application.setStyle("Fusion")
        application.setApplicationName("Synapse Pet")
    return application


class DragHeader(QFrame):
    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent)
        self.window = parent
        self._drag_offset: QPoint | None = None
        self.setObjectName("Header")
        self.setFixedHeight(46)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 12, 0)
        mark = QLabel("◉")
        mark.setStyleSheet(f"color: {CYAN}; font: bold 17pt 'Segoe UI Symbol';")
        layout.addWidget(mark)
        title = QLabel("SYNAPSE PET")
        title.setStyleSheet("font: bold 10pt Consolas;")
        layout.addWidget(title)
        subtitle = QLabel("/ OCULUS")
        subtitle.setStyleSheet(f"color: {GOLD}; font: 9pt Consolas;")
        layout.addWidget(subtitle)
        layout.addStretch(1)
        self.renderer_label = QLabel("LOCAL · OPENGL")
        self.renderer_label.setStyleSheet("color: #70c9a4; font: bold 8pt Consolas;")
        layout.addWidget(self.renderer_label)
        self.minimize = QPushButton("—")
        self.minimize.setFixedWidth(38)
        self.minimize.clicked.connect(parent.showMinimized)
        layout.addWidget(self.minimize)
        self.close_button = QPushButton("×")
        self.close_button.setFixedWidth(38)
        self.close_button.clicked.connect(parent.close)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class MetricCard(QFrame):
    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        row = QHBoxLayout()
        label = QLabel(title.upper())
        label.setStyleSheet(f"color: {MUTED}; font: bold 8pt Consolas;")
        row.addWidget(label)
        row.addStretch(1)
        self.value = QLabel("50%")
        self.value.setStyleSheet("font: bold 9pt Consolas;")
        row.addWidget(self.value)
        layout.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setValue(50)
        self.bar.setStyleSheet(f"QProgressBar::chunk {{ background: {accent}; }}")
        layout.addWidget(self.bar)

    def set_value(self, value: float) -> None:
        percent = int(max(0.0, min(1.0, value)) * 100 + 0.5)
        self.value.setText(f"{percent:02d}%")
        self.bar.setValue(percent)


class TraceWidget(QWidget):
    def __init__(self, values: deque[float], color: str) -> None:
        super().__init__()
        self.values = values
        self.color = QColor(color)
        self.setMinimumHeight(90)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PANEL))
        mid = self.height() / 2
        painter.setPen(QPen(QColor("#293b44"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(5, int(mid), self.width() - 5, int(mid))
        if len(self.values) > 1:
            points = []
            values = list(self.values)
            for i, value in enumerate(values):
                x = 5 + i * (self.width() - 10) / (len(values) - 1)
                y = mid - max(-1.0, min(1.0, value)) * self.height() * 0.4
                points.append(QPoint(int(x), int(y)))
            painter.setPen(QPen(self.color, 2))
            for first, second in zip(points, points[1:]):
                painter.drawLine(first, second)
        painter.end()


class DebugPanel(QDialog):
    def __init__(self, parent: QWidget, state_provider, health_provider) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Oculus // Neural telemetry")
        self.resize(580, 430)
        self.setStyleSheet(f"QDialog {{ background: {BG}; color: {TEXT}; }}")
        self.state_provider = state_provider
        self.health_provider = health_provider
        self.dopamine = deque(maxlen=100)
        self.firing = deque(maxlen=100)
        layout = QVBoxLayout(self)
        title = QLabel("◉  NEURAL TELEMETRY  /  LIVE")
        title.setStyleSheet(f"color: {CYAN}; font: bold 10pt Consolas;")
        layout.addWidget(title)
        self.readout = QLabel()
        self.readout.setFont(QFont("Consolas", 9))
        layout.addWidget(self.readout)
        layout.addWidget(QLabel("DOPAMINE TRACE"))
        self.dopamine_plot = TraceWidget(self.dopamine, CYAN)
        layout.addWidget(self.dopamine_plot)
        layout.addWidget(QLabel("SNN FIRING RATE"))
        self.rate_plot = TraceWidget(self.firing, GOLD)
        layout.addWidget(self.rate_plot)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(160)
        self.refresh()

    def refresh(self) -> None:
        s = self.state_provider()
        health = self.health_provider()
        self.dopamine.append(s.dopamine)
        self.firing.append(s.firing_rate)
        runtime_status = {"running": "ATIVA", "stalled": "PARADA",
                          "stopped": "PARADA"}.get(
                              str(health["status"]), str(health["status"]).upper())
        thread_status = "VIVA" if health["thread_alive"] else "MORTA"
        self.readout.setText(
            f"SIMULAÇÃO {runtime_status:<8} REGIME {str(health['regime']).upper():<8}\n"
            f"THREAD {thread_status:<5} FILA {health['event_queue']:>3}  "
            f"PROP.Q {health['proposal_queue']:>2}  PEND {health['pending_proposals']:>2}\n"
            f"STATE {s.emotion.upper():<12} TICK {health['tick']:>8}\n"
            f"NETWORK {s.neuron_count:>4} NEURONS  "
            f"{s.recurrent_edges:>5} RECURRENT EDGES\n"
            f"DOPAMINE {s.dopamine:+.3f}  STRESS {s.stress:.2f}  ENERGY {s.energy:.2f}\n"
            f"HAPPINESS {s.happiness:.2f}  CURIOSITY {s.curiosity:.2f}  "
            f"TRUST {s.trust:.2f}  SPIKES {len(s.active_neurons)}"
            + (f"\nLAST ERROR {health['last_error']}" if health["last_error"] else ""))
        self.dopamine_plot.update()
        self.rate_plot.update()


class PetWindow(QMainWindow):
    MODES = (("ascii", "ASCII"), ("hud", "HUD"))
    panelHotkeyPressed = Signal()

    def __init__(self, engine) -> None:
        self.application = ensure_application()
        super().__init__()
        self.engine = engine
        self.config = engine.config
        self.visual_config = self.config.get("visual", {})
        self.interaction_config = self.config.get("interaction", {})
        self.pet_config = self.config.get("pet", {})
        self._pet_mode_enabled = str(self.pet_config.get("mode", "window")).lower() == "floating"
        self._is_floating = False
        self._pet_width = max(180, int(self.pet_config.get("width", 320)))
        self._pet_height = max(104, int(self.pet_config.get("height", 180)))
        self._pet_drag_offset: QPoint | None = None
        self._pet_drag_origin: QPoint | None = None
        self._pet_drag_started = 0.0
        self._pet_drag_moved = False
        self._pet_drag_rewarded = False
        self._pet_hovering = False
        self._autostart_enabled = False
        self._requested_exit = False
        self._settings = QSettings("SynapsePet", "Oculus")
        self._panel_size = (1000, 790)
        self._pet_animation = None
        self._global_hotkey = None
        self.setWindowTitle("Synapse Pet — Oculus")
        window_flags = (Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint)
        if self._pet_mode_enabled:
            window_flags |= Qt.WindowType.Tool
        self.setWindowFlags(window_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,
                          self._pet_mode_enabled)
        self.setStyleSheet(STYLESHEET)
        self.resize(self._panel_size[0], self._panel_size[1])
        self.last_state = VisualState()
        self.render_mode = "ascii"
        self.last_interaction = time.monotonic()
        self._frame_count = 0
        self._fps_started = time.monotonic()
        self._fps = 0
        self._notice = ""
        self._notice_until = 0.0
        self._proposal_name: str | None = None
        self._proposal_context = "outro"
        self._closing = False
        self._really_close = False
        self._shutdown_thread: threading.Thread | None = None
        self._saved_opacity = 1.0
        self._debug_panel: DebugPanel | None = None

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(9)
        self.header = DragHeader(self)
        layout.addWidget(self.header)

        configured_renderer = str(self.config.get("renderer", "ascii"))
        self.canvas = EyeCanvas(
            "ascii" if self._pet_mode_enabled else configured_renderer,
            int(self.visual_config.get("width", 960)),
            int(self.visual_config.get("height", 540)),
            int(self.visual_config.get("ascii_columns", 100)),
            int(self.visual_config.get("ascii_rows", 56)),
            str(self.visual_config.get("palette", "cyan_amber_white")),
            int(self.visual_config.get("max_particles", 48)),
            scene_time=str(self.visual_config.get("scene_time", "auto")),
            eye_design=str(self.visual_config.get("eye_design", "A")),
            ascii_max_columns=int(self.visual_config.get("ascii_max_columns", 170)),
            ascii_max_rows=int(self.visual_config.get("ascii_max_rows", 96)),
            affection_drag_min_s=float(self.interaction_config.get(
                "affection_drag_min_s", 1.0)),
            compact=self._pet_mode_enabled)
        layout.addWidget(self.canvas, 1)
        self.canvas.petRequested.connect(self._give_affection)
        self.canvas.activityDetected.connect(self._register_visual_activity)
        self.canvas.animationStarted.connect(self._accelerate_animation)
        self.canvas.rendererChanged.connect(self._renderer_changed)
        self._mouse_sample_position: tuple[int, int] | None = None
        self._mouse_last_move = time.monotonic()
        self._mouse_last_category: str | None = None
        self._mouse_last_sent = 0.0
        self._mouse_observation_timer = QTimer(self)
        interval_s = max(0.25, float(self.interaction_config.get(
            "mouse_observation_interval_s", 0.5)))
        self._mouse_observation_timer.setInterval(round(interval_s * 1000))
        self._mouse_observation_timer.timeout.connect(self._poll_mouse_attention)
        self._mouse_observation_timer.start()
        self._renderer_changed(self.canvas.current_renderer)
        self.canvas.set_state(self.last_state)

        identity = QHBoxLayout()
        labels = QVBoxLayout()
        name = QLabel("OCULUS / NOCTURNE")
        name.setStyleSheet("font: bold 10pt Consolas;")
        labels.addWidget(name)
        self.mood_label = QLabel("observando em silêncio")
        self.mood_label.setStyleSheet(f"color: {MUTED}; font: 9pt 'Segoe UI';")
        labels.addWidget(self.mood_label)
        identity.addLayout(labels)
        identity.addStretch(1)
        self.system_label = QLabel("SNN · ESTÁVEL")
        self.system_label.setStyleSheet(f"color: {CYAN}; font: 8pt Consolas;")
        identity.addWidget(self.system_label)
        layout.addLayout(identity)

        metrics = QHBoxLayout()
        self.happiness_card = MetricCard("Humor", GOLD)
        self.energy_card = MetricCard("Energia", CYAN)
        self.stress_card = MetricCard("Alerta", "#e58665")
        metrics.addWidget(self.happiness_card)
        metrics.addWidget(self.energy_card)
        metrics.addWidget(self.stress_card)
        layout.addLayout(metrics)

        self.proposal = QFrame()
        self.proposal.setObjectName("Proposal")
        proposal_layout = QVBoxLayout(self.proposal)
        self.proposal_text = QLabel()
        self.proposal_text.setWordWrap(True)
        proposal_layout.addWidget(self.proposal_text)
        proposal_actions = QHBoxLayout()
        self.accept_button = QPushButton("ACEITAR")
        self.accept_button.clicked.connect(lambda: self._answer_proposal(True))
        self.reject_button = QPushButton("RECUSAR")
        self.reject_button.clicked.connect(lambda: self._answer_proposal(False))
        self.defer_button = QPushButton("DEPOIS")
        self.defer_button.clicked.connect(lambda: self._answer_proposal(None))
        for button in (self.accept_button, self.reject_button, self.defer_button):
            proposal_actions.addWidget(button)
        proposal_layout.addLayout(proposal_actions)
        self.proposal.hide()
        layout.addWidget(self.proposal)

        feedback_row = QHBoxLayout()
        self.love_button = QPushButton("♡  CARINHO")
        self.love_button.setObjectName("Love")
        self.love_button.setToolTip("Aumenta o humor e dá conforto social.")
        self.love_button.clicked.connect(self._give_affection)
        self.feedback_button = QPushButton("◌  FEEDBACK")
        self.feedback_button.setObjectName("Negative")
        self.feedback_button.clicked.connect(lambda: self.engine.submit_feedback(-1))
        self.debug_button = QPushButton("DEBUG")
        self.debug_button.clicked.connect(self._open_debug)
        self.sensor_button = QPushButton("SENSORES")
        self.sensor_button.setObjectName("Gold")
        self.sensor_button.clicked.connect(self._show_sensor_menu)
        self.mode_button = QPushButton("EXPRESSÕES · ASCII")
        self.mode_button.setToolTip(
            "Alterna a arte ASCII animada e o painel HUD. Atalho: M.")
        self.mode_button.clicked.connect(self._cycle_mode)
        self.undo_button = QPushButton("DESFAZER")
        self.undo_button.clicked.connect(self.engine.submit_undo)
        self.save_button = QPushButton("SALVAR")
        self.save_button.clicked.connect(self.engine.submit_save)
        for button in (self.love_button, self.feedback_button):
            feedback_row.addWidget(button, 1)
        layout.addLayout(feedback_row)
        toolbar = QHBoxLayout()
        for button in (self.debug_button, self.sensor_button, self.mode_button,
                       self.undo_button, self.save_button):
            toolbar.addWidget(button, 1)
        layout.addLayout(toolbar)

        self.status_label = QLabel("SENSORES DESLIGADOS · 100% LOCAL · M / F11 / T")
        self.status_label.setStyleSheet(f"color: {MUTED}; font: 8pt Consolas;")
        layout.addWidget(self.status_label)

        self._build_sensor_menu()
        self._build_shortcuts()
        self.panelHotkeyPressed.connect(self._show_panel)
        self._panel_only_widgets = [
            self.header, name, self.mood_label, self.system_label,
            self.happiness_card, self.energy_card, self.stress_card,
            self.proposal, self.love_button, self.feedback_button,
            self.debug_button, self.sensor_button, self.mode_button,
            self.undo_button, self.save_button, self.status_label,
        ]
        self._root_widget = root
        self._root_layout = layout
        self._create_tray_icon()
        self._start_global_panel_hotkey()
        self.engine.start()
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._refresh)
        self.frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.frame_timer.setInterval(33)
        self.frame_timer.start()
        QTimer.singleShot(0, self._refresh)

    def _build_shortcuts(self) -> None:
        for sequence, callback in (("M", self._cycle_mode), ("H", lambda: self._set_mode("hud")),
                                   ("F11", self._toggle_fullscreen),
                                   ("T", self._toggle_transparency),
                                   ("Escape", self._leave_fullscreen)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            shortcut.setEnabled(not self._pet_mode_enabled)

    def _create_tray_icon(self) -> None:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(CYAN), 2))
        painter.setBrush(QColor("#07131b"))
        painter.drawEllipse(3, 3, 26, 26)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(CYAN))
        painter.drawEllipse(11, 11, 10, 10)
        painter.end()
        self._tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        menu = QMenu(self)
        self._tray_panel_action = menu.addAction("Abrir painel")
        self._tray_panel_action.triggered.connect(self._show_panel)
        menu.addSeparator()
        self._pause_action = QAction("Pausar simulação", self)
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self._toggle_simulation_pause)
        menu.addAction(self._pause_action)
        self._autonomy_action = QAction("Silenciar autonomia", self)
        self._autonomy_action.setCheckable(True)
        self._autonomy_action.setChecked(True)
        self._autonomy_action.toggled.connect(self._toggle_autonomy)
        menu.addAction(self._autonomy_action)
        self._autostart_action = QAction("Iniciar com o Windows", self)
        self._autostart_action.setCheckable(True)
        self._autostart_action.setChecked(self._read_windows_startup())
        self._autostart_action.toggled.connect(self._set_windows_startup)
        menu.addAction(self._autostart_action)
        menu.addSeparator()
        quit_action = menu.addAction("Sair")
        quit_action.triggered.connect(self._quit_from_tray)
        self._tray_icon.setContextMenu(menu)
        self._tray_icon.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon.show()

    def _toggle_simulation_pause(self, paused: bool) -> None:
        self.engine.set_paused(paused)
        self._pause_action.setText("Retomar simulação" if paused else
                                   "Pausar simulação")

    def _toggle_autonomy(self, enabled: bool) -> None:
        self.engine.set_autonomy_enabled(enabled)
        self._autonomy_action.setText("Silenciar autonomia" if enabled else
                                      "Ativar autonomia")

    def _start_global_panel_hotkey(self) -> None:
        if not self._pet_mode_enabled:
            return
        hotkey = str(self.pet_config.get("panel_hotkey", "<ctrl>+<alt>+o"))
        try:
            from pynput.keyboard import GlobalHotKeys
            self._global_hotkey = GlobalHotKeys({
                hotkey: self.panelHotkeyPressed.emit,
            })
            self._global_hotkey.start()
        except Exception as exc:
            self.engine.logger.warning("Atalho global indisponível: %s", exc)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick}:
            self._show_panel()

    def _set_windows_startup(self, enabled: bool) -> None:
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE) as key:
                if enabled:
                    command = f'"{sys.executable}" -m synapse_pet.main'
                    winreg.SetValueEx(key, "SynapsePet", 0,
                                      winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, "SynapsePet")
                    except FileNotFoundError:
                        pass
            self._autostart_enabled = bool(enabled)
        except (OSError, ImportError) as exc:
            self._autostart_action.blockSignals(True)
            self._autostart_action.setChecked(not enabled)
            self._autostart_action.blockSignals(False)
            QMessageBox.warning(self, "Inicialização", f"Não foi possível alterar: {exc}")

    @staticmethod
    def _read_windows_startup() -> bool:
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "SynapsePet")
            return True
        except (OSError, ImportError):
            return False

    def _show_panel(self) -> None:
        if not self._pet_mode_enabled or not self._is_floating:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return
        self._settings.setValue("pet/x", self.x())
        self._settings.setValue("pet/y", self.y())
        self.hide()
        self._is_floating = False
        self.clearMask()
        self.removeEventFilter(self)
        for child in self.canvas.findChildren(QWidget):
            child.removeEventFilter(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(STYLESHEET)
        self._root_widget.setStyleSheet("")
        self._root_layout.setContentsMargins(12, 12, 12, 10)
        self._root_layout.setSpacing(9)
        for widget in self._panel_only_widgets:
            widget.show()
        if self._proposal_name and self.engine.proposal_is_pending(self._proposal_name):
            self.proposal.show()
        self.canvas.set_mode(self.render_mode)
        self.resize(*self._panel_size)
        self.setMinimumSize(700, 390)
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(True)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _enter_floating_mode(self) -> None:
        if not self._pet_mode_enabled:
            return
        self._panel_size = (max(700, self.width()), max(390, self.height()))
        self.hide()
        self._is_floating = True
        for widget in self._panel_only_widgets:
            widget.hide()
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.canvas.set_mode("pet")
        self._root_widget.setStyleSheet("background: transparent; border: none;")
        self.setStyleSheet("QMainWindow { background: transparent; border: none; }")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(180, 104)
        self.resize(self._pet_width, self._pet_height)
        target = self.canvas._stack.currentWidget()
        target.installEventFilter(self)
        self.setMask(self._pet_mask())
        self._restore_pet_position()
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(False)
        self.show()
        self.raise_()

    def _pet_mask(self) -> QRegion:
        width, height = self.width(), self.height()
        path = QPainterPath()
        path.moveTo(width * 0.025, height * 0.50)
        path.cubicTo(width * 0.18, height * 0.08, width * 0.82,
                     height * 0.08, width * 0.975, height * 0.50)
        path.cubicTo(width * 0.82, height * 0.92, width * 0.18,
                     height * 0.92, width * 0.025, height * 0.50)
        path.closeSubpath()
        return QRegion(path.toFillPolygon().toPolygon())

    def _restore_pet_position(self) -> None:
        saved_x = self._settings.value("pet/x", None)
        saved_y = self._settings.value("pet/y", None)
        if saved_x is not None and saved_y is not None:
            point = QPoint(int(saved_x), int(saved_y))
            screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        else:
            screen = QGuiApplication.primaryScreen()
            point = QPoint()
        if screen is None:
            return
        area = screen.availableGeometry()
        anchor = str(self.pet_config.get("anchor", "none")).lower()
        margin = max(0, int(self.pet_config.get("margin", 24)))
        if anchor == "top_left":
            point = QPoint(area.left() + margin, area.top() + margin)
        elif anchor == "top_right":
            point = QPoint(area.right() - self.width() - margin,
                           area.top() + margin)
        elif anchor == "bottom_left":
            point = QPoint(area.left() + margin,
                           area.bottom() - self.height() - margin)
        elif anchor == "bottom_right" or saved_x is None:
            point = QPoint(area.right() - self.width() - margin,
                           area.bottom() - self.height() - margin)
        point.setX(max(area.left(), min(point.x(), area.right() - self.width())))
        point.setY(max(area.top(), min(point.y(), area.bottom() - self.height())))
        self.move(point)

    def eventFilter(self, watched, event) -> bool:
        if not self._is_floating:
            return super().eventFilter(watched, event)
        event_type = event.type()
        if event_type == QEvent.Type.Enter and not self._pet_hovering:
            self._pet_hovering = True
            self._grow_pet()
        elif event_type == QEvent.Type.Leave:
            self._pet_hovering = False
        if event_type == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            self._show_panel()
            return True
        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self._show_pet_context_menu()
                return True
            if event.button() == Qt.MouseButton.LeftButton:
                point = event.globalPosition().toPoint()
                self._pet_drag_offset = point - self.frameGeometry().topLeft()
                self._pet_drag_origin = point
                self._pet_drag_started = time.monotonic()
                self._pet_drag_moved = False
                self._pet_drag_rewarded = False
        elif event_type == QEvent.Type.MouseMove and self._pet_drag_offset is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                point = event.globalPosition().toPoint()
                if self._pet_drag_origin is not None:
                    self._pet_drag_moved |= (
                        (point - self._pet_drag_origin).manhattanLength()
                        >= QApplication.startDragDistance())
                self.move(point - self._pet_drag_offset)
                if (self._pet_drag_moved and not self._pet_drag_rewarded
                        and time.monotonic() - self._pet_drag_started >= float(
                            self.interaction_config.get("affection_drag_min_s", 1.0))):
                    self._give_affection()
                    self._pet_drag_rewarded = True
        elif event_type == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._settings.setValue("pet/x", self.x())
                self._settings.setValue("pet/y", self.y())
                self._pet_drag_offset = None
                self._pet_drag_origin = None
                self._pet_drag_moved = False
                self._pet_drag_rewarded = False
        return super().eventFilter(watched, event)

    def _show_pet_context_menu(self) -> None:
        menu = QMenu(self)
        open_panel = menu.addAction("Abrir painel")
        menu.addSeparator()
        quit_action = menu.addAction("Sair")
        selected = menu.exec(QCursor.pos())
        if selected is open_panel:
            self._show_panel()
        elif selected is quit_action:
            self._quit_from_tray()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._is_floating:
            self.setMask(self._pet_mask())
        elif self.isVisible():
            self._panel_size = (max(700, self.width()), max(390, self.height()))

    def _grow_pet(self) -> None:
        if not self._is_floating:
            return
        start = self.geometry()
        grown_width, grown_height = round(start.width() * 1.08), round(start.height() * 1.08)
        center = start.center()
        grown = start.__class__(center.x() - grown_width // 2,
                                center.y() - grown_height // 2,
                                grown_width, grown_height)
        animation = QPropertyAnimation(self, b"geometry", self)
        animation.setDuration(700)
        animation.setStartValue(start)
        animation.setKeyValueAt(0.28, grown)
        animation.setKeyValueAt(0.72, grown)
        animation.setEndValue(start)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.start()
        self._pet_animation = animation

    def _quit_from_tray(self) -> None:
        self._requested_exit = True
        if self._global_hotkey is not None:
            self._global_hotkey.stop()
        self.close()

    def _build_sensor_menu(self) -> None:
        self.sensor_menu = QMenu(self)
        self.sensor_actions = {}
        for name, label in SENSOR_LABELS.items():
            action = self.sensor_menu.addAction(label)
            action.setCheckable(True)
            sensor = self.engine.sensor_manager.sensors[name]
            action.setChecked(sensor.enabled)
            action.toggled.connect(lambda enabled, n=name: self._toggle_sensor(n, enabled))
            self.sensor_actions[name] = action

    def _show_sensor_menu(self) -> None:
        self.sensor_menu.exec(self.sensor_button.mapToGlobal(self.sensor_button.rect().bottomLeft()))

    def _toggle_sensor(self, name: str, enabled: bool) -> None:
        if name == "file_events" and enabled:
            folder = QFileDialog.getExistingDirectory(self, "Escolha uma pasta monitorada")
            if not folder:
                self.sensor_actions[name].setChecked(False)
                return
            self.engine.sensor_manager.sensors[name].folder = Path(folder)
        self.engine.set_sensor_enabled(name, enabled)

    def _renderer_changed(self, name: str) -> None:
        self.header.renderer_label.setText(name.upper())
        self.last_interaction = time.monotonic()

    def _give_affection(self) -> None:
        self.engine.submit_affection()
        self.last_interaction = time.monotonic()
        self._grow_pet()

    def _register_visual_activity(self) -> None:
        self.last_interaction = time.monotonic()
        if hasattr(self, "frame_timer") and self.frame_timer.interval() > 33:
            self.frame_timer.setInterval(33)

    def _poll_mouse_attention(self) -> None:
        if not self.canvas.isVisible():
            return
        pointer = QCursor.pos()
        local = self.canvas.mapFromGlobal(pointer)
        if not self.canvas.rect().contains(local):
            self._mouse_sample_position = None
            self._mouse_last_category = None
            return
        now = time.monotonic()
        position = (pointer.x(), pointer.y())
        moved = self._mouse_sample_position is None
        if self._mouse_sample_position is not None:
            dx = position[0] - self._mouse_sample_position[0]
            dy = position[1] - self._mouse_sample_position[1]
            moved = dx * dx + dy * dy >= 9
        if moved:
            self._mouse_last_move = now
        self._mouse_sample_position = position
        nx = local.x() / max(1, self.canvas.width()) - 0.5
        ny = local.y() / max(1, self.canvas.height()) - 0.5
        proximity = "near" if nx * nx + ny * ny <= 0.22 * 0.22 else "far"
        motion = "moving" if now - self._mouse_last_move < 0.75 else "still"
        category = f"{proximity}_{motion}"
        if category != self._mouse_last_category or now - self._mouse_last_sent >= 1.0:
            self.engine.submit_mouse_attention(category)
            self._mouse_last_category = category
            self._mouse_last_sent = now

    def _accelerate_animation(self) -> None:
        if hasattr(self, "frame_timer") and self.frame_timer.interval() > 33:
            self.frame_timer.setInterval(33)

    def _open_debug(self) -> None:
        if self._debug_panel is None:
            self._debug_panel = DebugPanel(
                self, lambda: self.last_state, self.engine.health_snapshot)
        self._debug_panel.show()
        self._debug_panel.raise_()

    def _cycle_mode(self) -> None:
        current = next((i for i, (mode, _) in enumerate(self.MODES)
                        if mode == self.render_mode), 0)
        self._set_mode(self.MODES[(current + 1) % len(self.MODES)][0])

    def _set_mode(self, mode: str) -> None:
        self.render_mode = mode
        self.canvas.set_mode(mode)
        title = dict(self.MODES).get(mode, "REALISTA")
        self.mode_button.setText(f"EXPRESSÕES · {title}")
        self.last_interaction = time.monotonic()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _leave_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()

    def _toggle_transparency(self) -> None:
        self._saved_opacity = 1.0 if self._saved_opacity < 1.0 else 0.90
        self.setWindowOpacity(self._saved_opacity)

    def _answer_proposal(self, accepted: bool | None) -> None:
        if self._proposal_name:
            self.engine.submit_tool_response(self._proposal_name, accepted,
                                             getattr(self, "_proposal_context", "outro"))
        self._proposal_name = None
        self.proposal.hide()

    def _offer_folder_configuration(self) -> None:
        answer = QMessageBox.question(
            self, "Configure uma pasta",
            "Para explorar arquivos, o Synapse Pet precisa de uma pasta permitida. "
            "Deseja abrir configs/default.yaml para configurar tools.allowed_folders?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Yes:
            config_path = Path(__file__).resolve().parents[3] / "configs" / "default.yaml"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_path)))

    @staticmethod
    def _emotion_label(state: VisualState) -> str:
        return {
            "alegre": "alegre — brilho no olhar",
            "estressado": "estressado — buscando um momento de calma",
            "triste": "triste — precisa de um pouco de carinho",
            "sonolento": "sonolento — descansando o olhar",
            "dormindo": "dormindo — sonhando com a paisagem",
            "curioso": "curioso — acompanhando o ambiente",
        }.get(state.emotion, "observando em silêncio")

    def _refresh(self) -> None:
        if self.isMinimized() or not self.isVisible():
            self.frame_timer.stop()
            return
        try:
            while True:
                self.last_state = self.engine.visual_updates.get_nowait()
        except queue.Empty:
            pass
        candidate = None
        while True:
            try:
                candidate = self.engine.proposals.get_nowait()
            except queue.Empty:
                candidate = None
                break
            if self.engine.proposal_is_pending(candidate.name):
                break
            candidate = None
        if candidate is not None and getattr(self, "_proposal_name", None) is None:
            manifest = self.engine.registry.get(candidate.name)
            self._proposal_name = candidate.name
            self._proposal_context = candidate.context
            self.proposal_text.setText(manifest.description)
            if self._is_floating:
                if self._tray_icon.isVisible():
                    self._tray_icon.showMessage(
                        "Synapse Pet", "Há uma proposta aguardando no painel.",
                        QSystemTrayIcon.MessageIcon.Information, 4000)
            else:
                self.proposal.show()
        while True:
            try:
                result = self.engine.action_results.get_nowait()
            except queue.Empty:
                break
            operation = result.get("operation")
            status = result.get("status")
            if operation == "save":
                self._notice = ("SALVO" if status == "saved"
                                else f"ERRO AO SALVAR: {result.get('error', '')}")
            elif operation == "proposal" and status in {"timeout", "expired"}:
                if getattr(self, "_proposal_name", None) == result.get("tool"):
                    self._proposal_name = None
                    self.proposal.hide()
                self._notice = "PROPOSTA EXPIRADA"
            elif operation == "runtime":
                self._notice = {
                    "restarted": "SIMULAÇÃO RECUPERADA",
                    "paused": "SIMULAÇÃO PAUSADA",
                    "resumed": "SIMULAÇÃO RETOMADA",
                    "autonomy_on": "AUTONOMIA ATIVADA",
                    "autonomy_off": "AUTONOMIA SILENCIADA",
                }.get(str(status), f"SIMULAÇÃO: {status}")
            elif operation == "tool" and status == "configuration_required":
                self._notice = "PASTA NECESSÁRIA PARA EXPLORAR"
                if result.get("tool") in {"abrir_pasta", "resumo_arquivos_alterados"}:
                    QTimer.singleShot(0, self._offer_folder_configuration)
            elif operation == "tool" and status in {"parameters_required", "invalid_parameters"}:
                self._notice = "AÇÃO NÃO EXECUTADA · FALTAM DADOS VÁLIDOS"
            elif operation == "tool" and status == "error":
                self._notice = f"FALHA NA AÇÃO {result.get('tool', '')}"
            elif status == "undone":
                self._notice = "ÚLTIMA AÇÃO DESFEITA"
            if self._notice:
                self._notice_until = time.monotonic() + 5.0

        now = time.monotonic()
        self._frame_count += 1
        if now - self._fps_started >= 1.0:
            self._fps = self._frame_count
            self._frame_count = 0
            self._fps_started = now
        sleeping = bool(getattr(getattr(self.engine, "sleep", None), "sleeping", False))
        render_state = replace(
            self.last_state,
            render_fps=float(self._fps),
            expression_override=("dormindo" if sleeping
                                 else self.last_state.expression_override),
        )
        self.canvas.set_state(render_state)
        health = self.engine.health_snapshot()
        stopped = health["status"] in {"stalled", "stopped"}
        paused = health["status"] == "paused"
        if paused:
            self.mood_label.setText("SIMULAÇÃO PAUSADA")
            self.system_label.setText("SNN · PAUSADA")
            self.system_label.setStyleSheet("color: #e9b725; font: 8pt Consolas;")
        elif stopped:
            self.mood_label.setText("SIMULAÇÃO PARADA — valores emocionais congelados")
            self.system_label.setText("SNN · PARADA")
            self.system_label.setStyleSheet("color: #e58665; font: 8pt Consolas;")
        else:
            self.mood_label.setText(self._emotion_label(render_state))
            self.system_label.setText("SNN · ESTÁVEL")
            self.system_label.setStyleSheet(f"color: {CYAN}; font: 8pt Consolas;")
        self.happiness_card.set_value(self.last_state.happiness)
        self.energy_card.set_value(self.last_state.energy)
        self.stress_card.set_value(self.last_state.stress)
        enabled = [name for name, action in self.sensor_actions.items() if action.isChecked()]
        sensor_text = "SENSORES: " + " · ".join(enabled) if enabled else "SENSORES DESLIGADOS"
        if paused:
            self.status_label.setText(f"SIMULAÇÃO PAUSADA · TICK {health['tick']}")
        elif stopped:
            self.status_label.setText(
                f"SIMULAÇÃO PARADA · TICK {health['tick']} · "
                f"THREAD {'VIVA' if health['thread_alive'] else 'MORTA'} · "
                f"FILA {health['event_queue']} · LOG: {self.engine.log_path}")
        elif self._notice and now < self._notice_until:
            self.status_label.setText(self._notice)
        else:
            self.status_label.setText(f"{sensor_text.upper()} · {self._fps:02d} FPS · M / F11 / T")
        active = (self.last_state.active or now - self.last_interaction < 3.0
                  or (not self._is_floating and self.canvas.attention_animating))
        fps = int(self.visual_config.get("fps_active", 30) if active
                  else self.visual_config.get("fps_idle", 5))
        interval = max(1, round(1000 / max(1, fps)))
        if self.frame_timer.interval() != interval:
            self.frame_timer.setInterval(interval)
        self.canvas.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "frame_timer"):
            self.frame_timer.start()

    def hideEvent(self, event) -> None:
        if hasattr(self, "frame_timer"):
            self.frame_timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "frame_timer"):
            if self.isMinimized():
                self.frame_timer.stop()
            elif self.isVisible():
                self.frame_timer.start()

    def closeEvent(self, event) -> None:
        if self._really_close:
            event.accept()
            self.application.quit()
            return
        if self._pet_mode_enabled and not self._requested_exit:
            event.ignore()
            if self._debug_panel is not None:
                self._debug_panel.hide()
            if not self._is_floating:
                self._enter_floating_mode()
            return
        event.ignore()
        if self._closing:
            return
        self._closing = True
        self.frame_timer.stop()
        self._tray_icon.hide()
        self.hide()
        self._shutdown_thread = threading.Thread(target=self.engine.stop,
                                                name="synapse-pet-shutdown", daemon=True)
        self._shutdown_thread.start()
        QTimer.singleShot(50, self._poll_shutdown)

    def _poll_shutdown(self) -> None:
        if self._shutdown_thread and self._shutdown_thread.is_alive():
            QTimer.singleShot(50, self._poll_shutdown)
            return
        self._really_close = True
        self.close()

    def run(self) -> None:
        if self._pet_mode_enabled:
            self._enter_floating_mode()
        else:
            self.show()
        self.application.exec()
