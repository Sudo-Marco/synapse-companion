from __future__ import annotations

import math
import queue
import random
import sys
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QEvent, QEasingCurve, QPoint, QPointF,
                            QPropertyAnimation, QRect, QSettings, Qt, QTimer,
                            QUrl, QVariantAnimation, Signal)
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QDesktopServices,
                           QFont, QGuiApplication, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap, QRegion, QSurfaceFormat, QShortcut,
                           QKeySequence)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget,
                               QHeaderView, QTableWidget, QTableWidgetItem)

from ..runtime.visual_state import VisualState
from ..runtime.autonomy import AutonomyController, PostItStore, StoredPostIt
from ..sensors.audio_analysis import AudioMetrics
from ..sensors.audio_service import AudioMonitorService
from ..sensors.window_geometry import WindowGeometryObserver
from .day_cycle import activity_factor, period_name
from .desktop_motion import (DesktopBehaviorSelector, WorkArea,
                             choose_work_area_target, clamp_window_top_left,
                             desktop_depth)
from .teleport import STYLES as TELEPORT_STYLES, TeleportTrail, teleport_geometry
from .gl_renderer import EyeCanvas
from .postit import PostItWindow


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
PIXEL_FRAME_PATH = (Path(__file__).resolve().parents[1] / "assets" / "pixel"
                    / "ui_frame.png").as_posix()


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

PIXEL_STYLESHEET = f"""
QMainWindow, QWidget#Root {{ background: #182542; color: #fff3a0; }}
QFrame#Header, QFrame#Card, QFrame#Proposal {{
  background: #293b60;
  border-image: url({PIXEL_FRAME_PATH}) 3 3 3 3 stretch stretch;
  border-width: 3px; }}
QLabel {{ color: #f7f1d9; font-family: 'Silkscreen'; }}
QLabel#Muted {{ color: #c3d6cb; }}
QPushButton {{ background: #354a78; color: #fff3a0; border: 2px solid #fff3a0;
  border-radius: 0; padding: 8px 10px; font: 700 9pt 'Silkscreen'; }}
QPushButton:hover {{ background: #485b82; border-color: #ffffff; }}
QPushButton:pressed {{ background: #192b54; border-color: #ffd93b; }}
QPushButton:disabled {{ color: #8790a2; border-color: #485b82; }}
QPushButton#Love {{ background: #405a69; color: #f7f1d9; }}
QPushButton#Love:hover {{ background: #527a75; }}
QPushButton#Negative {{ background: #59465a; color: #ffe0c6; }}
QPushButton#Negative:hover {{ background: #735b83; }}
QPushButton#Gold {{ color: #ffd93b; }}
QProgressBar {{ background: #192b54; border: 2px solid #fff3a0;
  height: 11px; text-align: center; }}
QProgressBar::chunk {{ background: #ffd93b; }}
QMenu {{ background: #293b60; color: #fff3a0; border: 2px solid #fff3a0; }}
QMenu::item:selected {{ background: #485b82; color: #ffffff; }}
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
        self.return_to_pet = QPushButton("◉ OLHO")
        self.return_to_pet.setToolTip("Voltar ao olho flutuante")
        self.return_to_pet.clicked.connect(parent._enter_floating_mode)
        self.return_to_pet.setVisible(bool(parent._pet_mode_enabled))
        layout.addWidget(self.return_to_pet)
        self.close_button = QPushButton("×")
        self.close_button.setFixedWidth(38)
        self.close_button.setToolTip(
            "Fechar o painel e voltar ao olho flutuante"
            if parent._pet_mode_enabled else "Fechar")
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


class SegmentedProgressBar(QProgressBar):
    """Pixel-style progress bar composed of discrete filled cells."""

    def __init__(self, accent: str, *, pixel_mode: bool = False) -> None:
        super().__init__()
        self.pixel_mode = bool(pixel_mode)
        self.accent = QColor(accent)

    def paintEvent(self, event) -> None:
        if not self.pixel_mode:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#192b54"))
        painter.setPen(QPen(QColor("#fff3a0"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        inner = self.rect().adjusted(3, 3, -3, -3)
        if inner.width() <= 0 or inner.height() <= 0:
            painter.end()
            return
        count = max(1, inner.width() // 13)
        gap = 2
        cell_width = max(1, (inner.width() - gap * (count - 1)) // count)
        filled = round(self.value() * count / max(1, self.maximum()))
        for index in range(filled):
            left = inner.left() + index * (cell_width + gap)
            painter.fillRect(left, inner.top(), cell_width, inner.height(),
                             self.accent)
        painter.end()


class MetricCard(QFrame):
    def __init__(self, title: str, accent: str, *, pixel_mode: bool = False) -> None:
        super().__init__()
        self.pixel_mode = bool(pixel_mode)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        row = QHBoxLayout()
        label = QLabel(title.upper())
        font_family = "Silkscreen" if self.pixel_mode else "Consolas"
        label.setStyleSheet(f"color: {MUTED}; font: bold 8pt '{font_family}';")
        row.addWidget(label)
        row.addStretch(1)
        self.value = QLabel("50%")
        self.value.setStyleSheet(f"font: bold 9pt '{font_family}';")
        row.addWidget(self.value)
        layout.addLayout(row)
        self.bar = SegmentedProgressBar(accent, pixel_mode=self.pixel_mode)
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


class LearningPanel(QDialog):
    """On-demand, privacy-safe view of aggregate habits."""

    def __init__(self, parent: QWidget, memory) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.memory = memory
        self.setWindowTitle("Synapse Pet — Aprendizado")
        self.resize(640, 360)
        self.setStyleSheet(f"QDialog {{ background: {BG}; color: {TEXT}; }}")
        layout = QVBoxLayout(self)
        intro = QLabel("PADRÕES AGREGADOS · categorias e contagens, sem texto digitado ou títulos")
        intro.setStyleSheet(f"color: {CYAN}; font: bold 9pt Consolas;")
        layout.addWidget(intro)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Contexto", "Ação", "Observações", "RPE médio", "Atualizado"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)

    def refresh(self) -> None:
        rows = self.memory.habits(100)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            context, action, count, mean_rpe, last_rpe, updated = row
            values = (str(context), str(action), str(count),
                      f"{float(mean_rpe):+.3f} ({float(last_rpe):+.3f})", str(updated))
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(value))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        super().hideEvent(event)


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
        self.teleport_config = self.config.get("teleport", {})
        self.pet_motion_config = self.config.get("pet_motion", {})
        self.desktop_motion_config = self.pet_motion_config.get("desktop", {})
        self.audio_config = self.config.get("audio", {})
        self.day_cycle_config = self.config.get("day_cycle", {})
        self.weather_config = self.config.get("weather", {})
        self.audio_privacy = self.config.get("privacy", {}).get("sensors", {})
        self.audio_service = AudioMonitorService(
            sample_rate=int(self.audio_config.get("sample_rate", 11025)),
            block_size=int(self.audio_config.get("block_size", 512)),
            config=self.audio_config)
        self._audio_enabled = {"microphone": False, "loopback": False}
        self._audio_metrics: dict[str, AudioMetrics] = {}
        self._audio_voice_since: float | None = None
        self._audio_last_voice_at = -math.inf
        self._audio_voice_triggered = False
        self._audio_voice_last_trigger = -math.inf
        self._audio_voice_events: deque[float] = deque()
        self._audio_listening_until = 0.0
        self._audio_music_active = False
        self._audio_music_level = 0.0
        self._audio_bpm = 0.0
        self._audio_beat_phase = 0.0
        self._audio_dance_cooldown_until = 0.0
        self._audio_dance_events: deque[float] = deque()
        behavior_config = self.pet_motion_config.get("behaviors", {})
        self.desktop_behavior_selector = DesktopBehaviorSelector(
            behavior_config, seed=int(self.config.get("seed", 41)))
        self._desktop_animation: QPropertyAnimation | None = None
        self._desktop_animation_style: str | None = None
        self._desktop_last_position: QPoint | None = None
        self._desktop_behavior: str | None = None
        self._desktop_behavior_until = 0.0
        self._desktop_rng = random.Random(int(self.config.get("seed", 41)) ^ 0x44534B54)
        initial_scale = activity_factor(datetime.now().astimezone(),
                                        self.day_cycle_config)
        self._desktop_next_action_at = time.monotonic() + self._desktop_rng.uniform(
            float(self.pet_motion_config.get("interval_min_s", 6.0)),
            float(self.pet_motion_config.get("interval_max_s", 12.0))) / initial_scale
        self._pet_stamina = 1.0
        self._pet_stamina_updated_at = time.monotonic()
        self._active_window_geometry = None
        self._active_window_fullscreen = False
        self._window_geometry_observer = WindowGeometryObserver()
        self._window_geometry_enabled = bool(self.config.get("privacy", {}).get(
            "sensors", {}).get("window_geometry", False))
        self._pixel_theme = str(self.pet_config.get("render_style", "pixel")).lower() == "pixel"
        self._window_stylesheet = PIXEL_STYLESHEET if self._pixel_theme else STYLESHEET
        self.autonomy_config = self.config.get("autonomy", {})
        self.autonomy = AutonomyController(self.autonomy_config)
        self._postit_store = PostItStore(engine.data_dir / "postits.sqlite3")
        self._postit_windows: dict[int, PostItWindow] = {}
        self._pet_mode_enabled = str(self.pet_config.get("mode", "window")).lower() == "floating"
        self._is_floating = False
        self._pet_width = max(180, int(self.pet_config.get("width", 320)))
        self._pet_height = max(104, int(self.pet_config.get("height", 180)))
        self._pet_drag_offset: QPoint | None = None
        self._pet_drag_origin: QPoint | None = None
        self._pet_drag_started = 0.0
        self._pet_drag_moved = False
        self._pet_drag_rewarded = False
        self._pet_last_click_at = 0.0
        self._pet_last_click_position: QPoint | None = None
        self._pet_return_position: QPoint | None = None
        self._pet_hovering = False
        self._autostart_enabled = False
        self._requested_exit = False
        self._settings = QSettings("SynapsePet", "Oculus")
        self._panel_size = (1000, 790)
        self._pet_animation = None
        self._pet_hover_start_geometry: QRect | None = None
        self._jump_animation: QVariantAnimation | None = None
        self._jump_start_geometry: QRect | None = None
        jump_seed = int(self.config.get("seed", 41)) ^ 0x4A554D50
        self._jump_rng = random.Random(jump_seed)
        self._next_jump_at = time.monotonic() + self._jump_rng.uniform(3.0, 7.0)
        self._teleport_animation: QVariantAnimation | None = None
        self._teleport_trail: TeleportTrail | None = None
        self._teleport_start_geometry: QRect | None = None
        self._teleport_destination_geometry: QRect | None = None
        self._teleport_style = None
        self._teleport_history: deque[float] = deque()
        self._last_teleport_at = 0.0
        self._teleport_blink_until = 0.0
        self._teleport_look_target: QPointF | None = None
        self._teleport_rng = random.Random(int(self.config.get("seed", 41)) ^ 0x54454C45)
        self._global_hotkey = None
        self.setWindowTitle("Synapse Pet — Oculus")
        window_flags = (Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.WindowStaysOnTopHint)
        if self._pet_mode_enabled:
            window_flags |= Qt.WindowType.Tool
        self.setWindowFlags(window_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,
                          self._pet_mode_enabled)
        self.setStyleSheet(self._window_stylesheet)
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
        self._learning_panel: LearningPanel | None = None

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(9)
        self.header = DragHeader(self)
        layout.addWidget(self.header)

        configured_renderer = str(self.config.get("renderer", "ascii"))
        pet_config = self.config.get("pet", {})
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
            compact=self._pet_mode_enabled,
            render_style=str(pet_config.get("render_style", "pixel")),
            spectral_config=pet_config.get("spectral", {}),
            seed=int(self.config.get("seed", 41)),
            depth_in_pet_mode=bool(pet_config.get("depth", {}).get(
                "enabled", pet_config.get("depth_in_pet_mode", False))),
            depth_config=pet_config.get("depth", {}),
            day_cycle_config=self.day_cycle_config,
            weather_config=self.weather_config)
        layout.addWidget(self.canvas, 1)
        self.canvas.petRequested.connect(self._give_affection)
        self.canvas.panelRequested.connect(self._show_panel)
        self.canvas.activityDetected.connect(self._register_visual_activity)
        self.canvas.animationStarted.connect(self._accelerate_animation)
        self.canvas.rendererChanged.connect(self._renderer_changed)
        self.canvas.spriteMaskChanged.connect(self._refresh_pet_mask)
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
        self.identity_label = QLabel("PIU / MADRUGADA")
        self.identity_label.setStyleSheet("font: bold 10pt Consolas;")
        labels.addWidget(self.identity_label)
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
        self.happiness_card = MetricCard("Humor", GOLD,
                                         pixel_mode=self._pixel_theme)
        self.energy_card = MetricCard("Energia", CYAN,
                                      pixel_mode=self._pixel_theme)
        self.stress_card = MetricCard("Alerta", "#e58665",
                                      pixel_mode=self._pixel_theme)
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
        if self._pixel_theme:
            self.mode_button.setText("VISUAL · CENÁRIO")
        self.mode_button.setToolTip(
            "Alterna a arte ASCII animada e o painel HUD. Atalho: M.")
        self.mode_button.clicked.connect(self._cycle_mode)
        self.learning_button = QPushButton("APRENDIZADO")
        self.learning_button.setToolTip(
            "Mostra padrões agregados que a SNN reforçou; não registra texto digitado.")
        self.learning_button.clicked.connect(self._open_learning)
        self.undo_button = QPushButton("DESFAZER")
        self.undo_button.clicked.connect(self.engine.submit_undo)
        self.save_button = QPushButton("SALVAR")
        self.save_button.clicked.connect(self.engine.submit_save)
        for button in (self.love_button, self.feedback_button):
            feedback_row.addWidget(button, 1)
        layout.addLayout(feedback_row)
        toolbar = QHBoxLayout()
        for button in (self.debug_button, self.sensor_button, self.mode_button,
                       self.learning_button,
                       self.undo_button, self.save_button):
            toolbar.addWidget(button, 1)
        layout.addLayout(toolbar)

        self.status_label = QLabel("SENSORES DESLIGADOS · 100% LOCAL · M / F11 / T")
        self.status_label.setStyleSheet(f"color: {MUTED}; font: 8pt Consolas;")
        layout.addWidget(self.status_label)

        self._build_sensor_menu()
        self._window_geometry_timer = QTimer(self)
        self._window_geometry_timer.setInterval(max(250, int(
            self.desktop_motion_config.get("geometry_poll_ms", 500))))
        self._window_geometry_timer.timeout.connect(self._poll_window_geometry)
        if self._pet_mode_enabled:
            # This minimal rectangle-only read is also the fullscreen safety
            # guard. Window landing/peeking remains separately opt-in.
            self._window_geometry_timer.start()
        self._build_shortcuts()
        self.panelHotkeyPressed.connect(self._show_panel)
        self._panel_only_widgets = [
            self.header, self.identity_label, self.mood_label, self.system_label,
            self.happiness_card, self.energy_card, self.stress_card,
            self.proposal, self.love_button, self.feedback_button,
            self.debug_button, self.sensor_button, self.mode_button,
            self.learning_button,
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
        QTimer.singleShot(0, self._restore_postits)

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
        self._update_tray_icon()
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
        self._autonomy_action.setChecked(bool(self.engine.autonomy_enabled))
        self._autonomy_action.toggled.connect(self._toggle_autonomy)
        menu.addAction(self._autonomy_action)
        menu.addMenu(self.sensor_menu)
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

    def _set_window_geometry_enabled(self, enabled: bool) -> None:
        self._window_geometry_enabled = bool(enabled)
        if not self._window_geometry_enabled:
            self._active_window_geometry = None
        self._poll_window_geometry()

    def _update_tray_icon(self) -> None:
        tray_icon = getattr(self, "_tray_icon", None)
        if tray_icon is None:
            return
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
        active = []
        if self._audio_enabled.get("microphone"):
            painter.setBrush(QColor("#ff5d69"))
            painter.drawEllipse(21, 1, 9, 9)
            active.append("microfone")
        if self._audio_enabled.get("loopback"):
            painter.setPen(QColor("#ffd166"))
            painter.setFont(QFont("Segoe UI Symbol", 10, QFont.Weight.Bold))
            painter.drawText(17, 31, "♪")
            active.append("áudio do sistema")
        painter.end()
        tray_icon.setIcon(QIcon(pixmap))
        suffix = " · " + ", ".join(active) if active else ""
        tray_icon.setToolTip("Synapse Pet" + suffix)

    def _set_audio_enabled(self, source: str, enabled: bool) -> None:
        source = str(source)
        if source not in self._audio_enabled:
            return
        if enabled:
            self._audio_enabled[source] = True
            self.audio_service.start(source)
        else:
            self._audio_enabled[source] = False
            self.audio_service.stop(source)
            self._audio_metrics.pop(source, None)
            if source == "microphone":
                self._audio_voice_since = None
                self._audio_last_voice_at = -math.inf
                self._audio_voice_triggered = False
                self._audio_listening_until = 0.0
            elif source == "loopback":
                self._audio_music_active = False
                self._audio_bpm = 0.0
                self._audio_beat_phase = 0.0
        self._update_tray_icon()
        self._update_canvas_audio_status()

    def _update_canvas_audio_status(self) -> None:
        if not hasattr(self, "canvas"):
            return
        microphone = self._audio_metrics.get("microphone", AudioMetrics())
        loopback = self._audio_metrics.get("loopback", AudioMetrics())
        self.canvas.set_audio_status(
            microphone_enabled=self._audio_enabled.get("microphone", False),
            loopback_enabled=self._audio_enabled.get("loopback", False),
            voice_active=microphone.voice_active,
            music_active=loopback.music_active,
            bpm=self._audio_bpm,
            beat_phase=self._audio_beat_phase,
            level=max(microphone.level, loopback.level))

    def _update_audio_state(self, now: float) -> None:
        for source, status in self.audio_service.drain_events():
            if status != "unavailable":
                continue
            self._audio_enabled[source] = False
            action = getattr(self, "audio_actions", {}).get(source)
            if action is not None:
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)
            self._notice = ("MICROFONE INDISPONÍVEL" if source == "microphone"
                            else "ÁUDIO DO SISTEMA INDISPONÍVEL")
            self._notice_until = now + 5.0
            self._update_tray_icon()

        self._audio_metrics = self.audio_service.metrics_snapshot()
        microphone = self._audio_metrics.get("microphone", AudioMetrics())
        loopback = self._audio_metrics.get("loopback", AudioMetrics())
        self._audio_music_active = bool(
            self._audio_enabled.get("loopback") and loopback.music_active)
        self._audio_music_level = max(0.0, min(1.0, loopback.level / 0.15))
        self._audio_bpm = (loopback.bpm if self._audio_music_active else 0.0)
        self._audio_beat_phase = (loopback.beat_phase
                                  if self._audio_music_active else 0.0)

        voice_active = bool(
            self._audio_enabled.get("microphone") and microphone.voice_active)
        if voice_active:
            self._audio_last_voice_at = now
            if self._audio_voice_since is None:
                self._audio_voice_since = now
            min_s = max(0.1, float(self.audio_config.get(
                "voice_sustain_s", 0.65)))
            release_s = max(0.5, float(self.audio_config.get(
                "voice_release_s", 2.5)))
            if (not self._audio_voice_triggered
                    and now - self._audio_voice_since >= min_s):
                hour = 3600.0
                while self._audio_voice_events and now - self._audio_voice_events[0] > hour:
                    self._audio_voice_events.popleft()
                cooldown = max(0.0, float(self.audio_config.get(
                    "voice_cooldown_s", 8.0)))
                max_per_hour = max(0, int(self.audio_config.get(
                    "voice_gestures_per_hour", 24)))
                if (len(self._audio_voice_events) < max_per_hour
                        and now - self._audio_voice_last_trigger >= cooldown):
                    self._audio_voice_events.append(now)
                    self._audio_voice_last_trigger = now
                    if self._is_floating and self.engine.autonomy_enabled:
                        self._audio_listening_until = now + release_s
                self._audio_voice_triggered = True
        else:
            release_s = max(0.5, float(self.audio_config.get(
                "voice_release_s", 2.5)))
            if now - self._audio_last_voice_at >= release_s:
                self._audio_voice_since = None
                self._audio_voice_triggered = False
                self._audio_listening_until = 0.0

        self._update_canvas_audio_status()

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
        self._finish_teleport()
        if not self._pet_mode_enabled or not self._is_floating:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return
        self._stop_desktop_motion()
        self._stop_pet_animation(restore_start=True)
        self._stop_jump(restore_start=True)
        self._pet_last_click_at = 0.0
        self._pet_last_click_position = None
        self._pet_return_position = QPoint(self.pos())
        self._settings.setValue("pet/x", self.x())
        self._settings.setValue("pet/y", self.y())
        self._settings.sync()
        self.hide()
        self._is_floating = False
        if hasattr(self, "_window_geometry_timer"):
            self._window_geometry_timer.stop()
        self.clearMask()
        self.removeEventFilter(self)
        for child in self.canvas.findChildren(QWidget):
            child.removeEventFilter(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(self._window_stylesheet)
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
        if self._is_floating:
            self.showNormal()
            self.raise_()
            return
        self._stop_desktop_motion()
        self._stop_pet_animation(restore_start=True)
        self._stop_jump(restore_start=True)
        for panel in (self._debug_panel, self._learning_panel):
            if panel is not None:
                panel.hide()
        self._panel_size = (max(700, self.width()), max(390, self.height()))
        self.hide()
        self._is_floating = True
        if hasattr(self, "_window_geometry_timer"):
            self._window_geometry_timer.start()
        for widget in self._panel_only_widgets:
            widget.hide()
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.canvas.set_mode("pet")
        self._root_widget.setStyleSheet("background: transparent; border: none;")
        self.setStyleSheet("QMainWindow { background: transparent; border: none; }")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(80, 52)
        self.resize(self._pet_width, self._pet_height)
        target = self.canvas._stack.currentWidget()
        target.installEventFilter(self)
        self.setMask(self._pet_mask())
        self._restore_pet_position(self._pet_return_position)
        self._pet_return_position = None
        self._pet_last_click_at = 0.0
        self._pet_last_click_position = None
        self._settings.setValue("pet/x", self.x())
        self._settings.setValue("pet/y", self.y())
        self._settings.sync()
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(False)
        self.showNormal()
        self.raise_()

    def _pet_mask(self) -> QRegion:
        sprite_mask = self.canvas.sprite_mask(self.size())
        if not sprite_mask.isEmpty():
            return sprite_mask
        width, height = self.width(), self.height()
        path = QPainterPath()
        path.moveTo(width * 0.025, height * 0.50)
        path.cubicTo(width * 0.18, height * 0.08, width * 0.82,
                     height * 0.08, width * 0.975, height * 0.50)
        path.cubicTo(width * 0.82, height * 0.92, width * 0.18,
                     height * 0.92, width * 0.025, height * 0.50)
        path.closeSubpath()
        return QRegion(path.toFillPolygon().toPolygon())

    def _refresh_pet_mask(self) -> None:
        if self._is_floating and self.isVisible():
            self.setMask(self._pet_mask())

    def _restore_pet_position(self, preferred_position: QPoint | None = None) -> None:
        saved_x = self._settings.value("pet/x", None)
        saved_y = self._settings.value("pet/y", None)
        if preferred_position is not None:
            point = QPoint(preferred_position)
            screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        elif saved_x is not None and saved_y is not None:
            point = QPoint(int(saved_x), int(saved_y))
            screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        else:
            screen = QGuiApplication.primaryScreen()
            point = QPoint()
        if screen is None:
            return
        area = screen.availableGeometry()
        anchor = ("none" if preferred_position is not None else
                  str(self.pet_config.get("anchor", "none")).lower())
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
        work = WorkArea(area.left(), area.top(), area.width(), area.height())
        x, y = clamp_window_top_left(point.x(), point.y(), self.width(),
                                     self.height(), work)
        point = QPoint(x, y)
        self.move(point)

    @staticmethod
    def _screen_work_areas() -> list[WorkArea]:
        return [WorkArea(screen.availableGeometry().left(),
                         screen.availableGeometry().top(),
                         screen.availableGeometry().width(),
                         screen.availableGeometry().height())
                for screen in QGuiApplication.screens()]

    def _work_area_at(self, point: QPoint) -> WorkArea | None:
        screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        if screen is None:
            return None
        area = screen.availableGeometry()
        return WorkArea(area.left(), area.top(), area.width(), area.height())

    def _clamp_pet_position(self, point: QPoint) -> QPoint:
        center = point + QPoint(self.width() // 2, self.height() // 2)
        area = self._work_area_at(center)
        if area is None:
            return QPoint(point)
        x, y = clamp_window_top_left(point.x(), point.y(), self.width(),
                                     self.height(), area)
        return QPoint(x, y)

    def _sync_world_travel_pose(self) -> None:
        if self._desktop_animation is None:
            return
        center = self.frameGeometry().center()
        area = self._work_area_at(center)
        if area is None:
            return
        depth = desktop_depth(center.y(), area)
        dx = self._desktop_animation.endValue().x() - self._desktop_animation.startValue().x()
        direction = -1 if dx < 0 else 1
        position = self.pos()
        previous = self._desktop_last_position or position
        stride_delta = math.hypot(position.x() - previous.x(),
                                  position.y() - previous.y())
        self._desktop_last_position = QPoint(position)
        self.canvas.set_world_travel(
            self._desktop_animation_style, depth=depth, direction=direction,
            stride_delta_px=stride_delta)

    def _start_desktop_travel(self, x: int, y: int, style: str,
                              *, behavior: str, duration_s: float) -> bool:
        if self._desktop_animation is not None:
            return False
        end = self._clamp_pet_position(QPoint(int(x), int(y)))
        start = self.pos()
        distance = math.hypot(end.x() - start.x(), end.y() - start.y())
        if distance < 30:
            return False
        stamina = max(0.0, min(1.0, self._pet_stamina))
        speed = max(40.0, float(self.desktop_motion_config.get(
            "speed_px_s", 185)) * (0.42 + 0.58 * stamina))
        limits = self.desktop_motion_config
        travel_s = max(float(limits.get("travel_min_s", 1.0)), distance / speed)
        travel_s = min(float(limits.get("travel_max_s", 18.0)), travel_s)
        self._desktop_behavior = behavior
        self._desktop_behavior_until = time.monotonic() + max(
            travel_s, float(duration_s))
        self._desktop_animation_style = style
        self._desktop_last_position = QPoint(start)
        animation = QPropertyAnimation(self, b"pos", self)
        animation.setDuration(max(250, round(travel_s * 1000)))
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.valueChanged.connect(lambda _value: self._sync_world_travel_pose())
        animation.finished.connect(
            lambda animation=animation: self._desktop_travel_finished(animation))
        self._desktop_animation = animation
        self._sync_world_travel_pose()
        animation.start()
        return True

    def _desktop_travel_finished(self, animation: QPropertyAnimation) -> None:
        if self._desktop_animation is not animation:
            return
        self._desktop_animation = None
        self._desktop_animation_style = None
        self._desktop_last_position = None
        animation.deleteLater()
        self.canvas.set_world_travel(None)
        self._settings.setValue("pet/x", self.x())
        self._settings.setValue("pet/y", self.y())
        self._settings.sync()
        if self._desktop_behavior == "window_perch":
            self.canvas.set_behavior_action("peek")
            self._desktop_behavior_until = time.monotonic() + float(
                self.pet_motion_config.get("behaviors", {}).get("actions", {}).get(
                    "window_perch", {}).get("duration_s", 3.5))

    def _stop_desktop_motion(self) -> None:
        animation = self._desktop_animation
        self._desktop_animation = None
        self._desktop_animation_style = None
        self._desktop_last_position = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        self.canvas.set_world_travel(None)
        self._desktop_behavior = None
        self._desktop_behavior_until = 0.0
        self.canvas.set_behavior_action(None)

    def _update_pet_stamina(self, now: float) -> None:
        dt = max(0.0, min(1.0, now - self._pet_stamina_updated_at))
        self._pet_stamina_updated_at = now
        costs = self.desktop_motion_config.get("stamina", {})
        if self._desktop_animation is not None:
            rate = float(costs.get("run_cost_per_s", 0.025))
        elif self._desktop_behavior in {"dance", "audio_dance"}:
            rate = float(costs.get("dance_cost_per_s", 0.045))
        elif self._desktop_behavior == "rest":
            rate = -float(costs.get("rest_recovery_per_s", 0.12))
        else:
            rate = -float(costs.get("recovery_per_s", 0.018))
        self._pet_stamina = max(0.0, min(1.0, self._pet_stamina - rate * dt))

    def _consider_desktop_motion(self, state: VisualState,
                                 health: dict[str, object], now: float) -> None:
        if (not self._is_floating or not self.isVisible()
                or not bool(self.desktop_motion_config.get("enabled", True))
                or not bool(self.pet_motion_config.get("enabled", True))
                or not self.engine.autonomy_enabled
                or health.get("status") != "running"
                or int(health.get("pending_proposals", 0))
                or int(health.get("proposal_queue", 0))
                or self._pet_drag_offset is not None or self._pet_hovering
                or self._pet_animation is not None or self._jump_animation is not None
                or self._teleport_animation is not None
                or self._is_fullscreen_foreground()):
            self._stop_desktop_motion()
            return
        if now < self._audio_listening_until:
            if self._desktop_animation is not None:
                self._stop_desktop_motion()
            self._desktop_behavior = "listen"
            self._desktop_behavior_until = self._audio_listening_until
            self.canvas.set_behavior_action("listen")
            return
        if self._desktop_behavior == "listen":
            self._desktop_behavior = None
            self.canvas.set_behavior_action(None)
        if self._desktop_behavior == "audio_dance" and not self._audio_music_active:
            self._desktop_behavior = None
            self._desktop_behavior_until = 0.0
            self.canvas.set_behavior_action(None)
        if (self._audio_music_active and self._pet_stamina >= float(
                self.audio_config.get("dance_min_stamina", 0.35))
                and now >= self._audio_dance_cooldown_until):
            hour = 3600.0
            while self._audio_dance_events and now - self._audio_dance_events[0] > hour:
                self._audio_dance_events.popleft()
            max_per_hour = max(0, int(self.audio_config.get(
                "dance_sessions_per_hour", 24)))
            if len(self._audio_dance_events) < max_per_hour:
                if self._desktop_animation is not None:
                    self._stop_desktop_motion()
                self._audio_dance_events.append(now)
                duration = max(1.0, min(12.0, float(self.audio_config.get(
                    "dance_chunk_s", 7.0))))
                self._desktop_behavior = "audio_dance"
                self._desktop_behavior_until = now + duration
                if self._audio_music_level >= 0.50:
                    dance = "dance_hop" if state.emotion == "alegre" else "dance_sway"
                elif state.stress >= 0.62:
                    dance = "dance_sway"
                else:
                    dance = "dance_head"
                self.canvas.set_behavior_action(dance)
                self._audio_dance_cooldown_until = (
                    self._desktop_behavior_until + max(0.5, float(
                        self.audio_config.get("dance_pause_s", 1.0))))
                return
        if self._desktop_animation is not None:
            self._sync_world_travel_pose()
            return
        if self._desktop_behavior is not None:
            if now < self._desktop_behavior_until:
                return
            self._desktop_behavior = None
            self.canvas.set_behavior_action(None)
        if now < self._desktop_next_action_at:
            return
        minimum = max(2.0, float(self.pet_motion_config.get("interval_min_s", 6.0)))
        maximum = max(minimum, float(self.pet_motion_config.get("interval_max_s", 12.0)))
        circadian_scale = activity_factor(datetime.now().astimezone(),
                                          self.day_cycle_config)
        self._desktop_next_action_at = (
            now + self._desktop_rng.uniform(minimum, maximum) / circadian_scale)
        behavior_cfg = self.pet_motion_config.get("behaviors", {})
        action_defs = behavior_cfg.get("actions", {})
        if self._pet_stamina < 0.20:
            action = "rest"
        else:
            action = self.desktop_behavior_selector.choose(
                state.emotion, self._pet_stamina, now,
                window_available=(self._window_geometry_enabled
                                  and self._active_window_geometry is not None))
        if action is None:
            return
        action_cfg = action_defs.get(action, {})
        duration = max(0.5, float(action_cfg.get("duration_s", 2.5)))
        if action in {"rest", "think"}:
            self._desktop_behavior = action
            self._desktop_behavior_until = now + duration
            self.canvas.set_behavior_action("rest" if action == "rest" else "think")
            return
        if action == "dance":
            dance = self._desktop_rng.choice(
                ("dance_sway", "dance_hop", "dance_head"))
            self._desktop_behavior = action
            self._desktop_behavior_until = now + duration
            self.canvas.set_behavior_action(dance)
            return

        areas = self._screen_work_areas()
        if not areas:
            return
        current = self.frameGeometry().center()
        current_screen = QGuiApplication.screenAt(current)
        if action == "window_perch":
            rect = self._active_window_rect()
            if rect is None:
                return
            screen = QGuiApplication.screenAt(rect.center()) or current_screen
            if screen is None:
                return
            area = screen.availableGeometry()
            target_x = rect.center().x() - self.width() // 2
            target_y = rect.top() - self.height() + 4
            target = self._clamp_pet_position(QPoint(target_x, target_y))
            style = ("away" if target.y() < self.y() - 70 else
                     "return" if target.y() > self.y() + 70 else "walk")
            self._start_desktop_travel(target.x(), target.y(), style,
                                       behavior=action, duration_s=duration)
            return
        if action in {"follow_cursor", "flee_cursor"}:
            cursor = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor)
            if screen is None:
                return
            area_qt = screen.availableGeometry()
            area = WorkArea(area_qt.left(), area_qt.top(),
                            area_qt.width(), area_qt.height())
            if action == "follow_cursor":
                if state.curiosity < float(self.config.get("learning", {}).get(
                        "curiosity_threshold", 0.72)):
                    return
                target_x = cursor.x() - self.width() // 2
                target_y = cursor.y() - self.height() - 24
            else:
                if math.hypot(cursor.x() - current.x(), cursor.y() - current.y()) > 300:
                    return
                target_x = self.x() + (self.width() if current.x() < cursor.x()
                                       else -self.width())
                target_y = self.y()
            target_x, target_y = clamp_window_top_left(
                target_x, target_y, self.width(), self.height(), area)
            style = "run" if action == "flee_cursor" else "walk"
            self._start_desktop_travel(target_x, target_y, style,
                                       behavior=action, duration_s=duration)
            return

        if action == "wander":
            far = (True if self._desktop_rng.random() < 0.18 else
                   False if self._desktop_rng.random() < 0.22 else None)
            index, x, y = choose_work_area_target(
                areas, (self.x(), self.y()), (self.width(), self.height()),
                self._desktop_rng, far=far)
            target_area = areas[index]
            current_depth = desktop_depth(current.y(), self._work_area_at(current) or target_area)
            target_depth = desktop_depth(y + self.height() // 2, target_area)
            style = ("away" if target_depth > current_depth + 0.14 else
                     "return" if target_depth < current_depth - 0.14 else "walk")
            self._start_desktop_travel(x, y, style, behavior=action,
                                       duration_s=duration)


    def eventFilter(self, watched, event) -> bool:
        if not self._is_floating:
            return super().eventFilter(watched, event)
        event_type = event.type()
        if event_type == QEvent.Type.Enter and not self._pet_hovering:
            self._pet_hovering = True
            self._grow_pet()
        elif event_type == QEvent.Type.Leave:
            self._pet_hovering = False
        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self._show_pet_context_menu()
                return True
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish_teleport()
                point = event.globalPosition().toPoint()
                click_interval = max(200, QApplication.doubleClickInterval()) / 1000.0
                if (self._pet_last_click_position is not None
                        and time.monotonic() - self._pet_last_click_at <= click_interval
                        and (point - self._pet_last_click_position).manhattanLength()
                        <= QApplication.startDragDistance()):
                    self._pet_last_click_at = 0.0
                    self._pet_last_click_position = None
                    self._show_panel()
                    return True
                self._stop_desktop_motion()
                self._stop_jump(restore_start=False)
                self._stop_pet_animation(restore_start=True)
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
                self.move(self._clamp_pet_position(point - self._pet_drag_offset))
                if (self._pet_drag_moved and not self._pet_drag_rewarded
                        and time.monotonic() - self._pet_drag_started >= float(
                            self.interaction_config.get("affection_drag_min_s", 1.0))):
                    self._give_affection()
                    self._pet_drag_rewarded = True
        elif event_type == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if not self._pet_drag_moved:
                    self._pet_last_click_at = time.monotonic()
                    self._pet_last_click_position = event.globalPosition().toPoint()
                else:
                    self._pet_last_click_at = 0.0
                    self._pet_last_click_position = None
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
        self._stop_pet_animation(restore_start=False)
        start = self.geometry()
        self._pet_hover_start_geometry = QRect(start)
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
        animation.finished.connect(
            lambda animation=animation: self._pet_animation_finished(animation))
        animation.start()
        self._pet_animation = animation

    def _pet_animation_finished(self, animation: QPropertyAnimation) -> None:
        if self._pet_animation is animation:
            self._pet_animation = None
            self._pet_hover_start_geometry = None
            animation.deleteLater()

    def _stop_pet_animation(self, *, restore_start: bool) -> None:
        animation = self._pet_animation
        start = self._pet_hover_start_geometry
        self._pet_animation = None
        self._pet_hover_start_geometry = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        if restore_start and start is not None and self._is_floating:
            self.setGeometry(start)

    def _consider_jump(self, state: VisualState, health: dict[str, object],
                       now: float) -> None:
        if (not self._is_floating or not self.isVisible()
                or not bool(self.pet_motion_config.get("enabled", True))
                or not self.engine.autonomy_enabled
                or health["status"] != "running"
                or int(health["pending_proposals"]) > 0
                or int(health["proposal_queue"]) > 0
                or self._desktop_animation is not None
                or self._teleport_animation is not None
                or self._jump_animation is not None
                or self._pet_animation is not None
                or self._pet_drag_offset is not None
                or self._pet_hovering or self._pet_stamina < 0.20):
            return
        if now < self._next_jump_at:
            return

        minimum = max(2.0, float(self.pet_motion_config.get("interval_min_s", 6.0)))
        maximum = max(minimum, float(self.pet_motion_config.get("interval_max_s", 12.0)))
        self._next_jump_at = now + self._jump_rng.uniform(minimum, maximum)
        if now - self.last_interaction < float(
                self.teleport_config.get("quiet_after_interaction_s", 15.0)):
            return

        emotion = str(state.emotion).lower()
        if emotion in {"dormindo", "sleeping"}:
            return
        if emotion in {"alegre", "amoroso", "happy"}:
            style = "happy"
        elif emotion in {"curioso", "curious"}:
            style = "curious"
        elif emotion in {"estressado", "stressed"}:
            style = "stress"
        elif emotion in {"triste", "sad"}:
            style = "sad"
        elif emotion in {"sonolento", "sleepy"}:
            style = "sleepy"
        else:
            style = "idle"

        amplitudes = self.pet_motion_config.get("amplitude_px", {})
        default_amplitudes = {
            "happy": 26, "curious": 18, "stress": 8,
            "sad": 4, "sleepy": 2, "idle": 8,
        }
        amplitude_key = {
            "happy": "alegre", "curious": "curioso", "stress": "estressado",
            "sad": "triste", "sleepy": "sonolento", "idle": "neutro",
        }[style]
        amplitude = max(0, int(amplitudes.get(
            amplitude_key, default_amplitudes[style])))
        duration_ms = {
            "happy": 640, "curious": 700, "stress": 420,
            "sad": 900, "sleepy": 1500, "idle": 850,
        }[style]
        self._begin_jump(style, amplitude, duration_ms)

    def _begin_jump(self, style: str, amplitude: int, duration_ms: int) -> None:
        if (self._jump_animation is not None or not self._is_floating
                or self._pet_stamina < 0.20):
            return
        self._pet_stamina = max(0.0, self._pet_stamina - float(
            self.desktop_motion_config.get("stamina", {}).get("jump_cost", 0.12)))
        start = QRect(self.geometry())
        self._jump_start_geometry = start
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(duration_ms)
        animation.setEasingCurve(QEasingCurve.Type.Linear)
        animation.valueChanged.connect(
            lambda value, style=style, amplitude=amplitude:
            self._jump_frame(float(value), style, amplitude))
        animation.finished.connect(
            lambda animation=animation: self._jump_finished(animation))
        self._jump_animation = animation
        animation.start()

    def _jump_frame(self, progress: float, style: str, amplitude: int) -> None:
        start = self._jump_start_geometry
        if start is None or not self._is_floating:
            return
        t = max(0.0, min(1.0, progress))
        arc = math.sin(math.pi * t)
        if style == "happy":
            lift = abs(math.sin(math.tau * t)) * amplitude * (1.0 - 0.25 * t)
            x_offset = 0
            y_offset = -round(lift)
        elif style == "stress":
            lift = arc * amplitude
            x_offset = round(math.sin(t * math.pi * 10.0) * 2.0 * (1.0 - t))
            y_offset = -round(lift)
        elif style == "sad":
            x_offset = 0
            y_offset = round(arc * amplitude)
        elif style == "sleepy":
            x_offset = 0
            y_offset = -round(arc * amplitude)
        else:
            x_offset = 0
            y_offset = -round(arc * amplitude)
        moved = self._clamp_pet_position(start.topLeft() + QPoint(x_offset, y_offset))
        self.move(moved)

    def _jump_finished(self, animation: QVariantAnimation) -> None:
        if self._jump_animation is not animation:
            return
        start = self._jump_start_geometry
        self._jump_animation = None
        self._jump_start_geometry = None
        if start is not None and self._is_floating:
            self.setGeometry(start)
        animation.deleteLater()

    def _stop_jump(self, *, restore_start: bool) -> None:
        animation = self._jump_animation
        start = self._jump_start_geometry
        self._jump_animation = None
        self._jump_start_geometry = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        if restore_start and start is not None and self._is_floating:
            self.setGeometry(start)

    def _teleport_enabled(self) -> bool:
        return bool(self.teleport_config.get("enabled", True))

    def _consider_teleport(self, state: VisualState, health: dict[str, object],
                            now: float) -> None:
        if (not self._is_floating or not self._teleport_enabled()
                or not self.engine.autonomy_enabled or self._teleport_animation is not None
                or self._desktop_animation is not None
                or self._pet_drag_offset is not None or self._pet_hovering
                or health["status"] != "running"
                or int(health["pending_proposals"]) > 0
                or int(health["proposal_queue"]) > 0
                or now - self.last_interaction < float(
                    self.teleport_config.get("quiet_after_interaction_s", 15.0))):
            return

        cooldown = max(0.0, float(self.teleport_config.get("cooldown_s", 75.0)))
        while self._teleport_history and now - self._teleport_history[0] >= 3600.0:
            self._teleport_history.popleft()
        if now - self._last_teleport_at < cooldown:
            return
        hourly_limit = max(0, int(self.teleport_config.get("max_per_hour", 4)))
        if hourly_limit == 0 or len(self._teleport_history) >= hourly_limit:
            return

        rates = dict(state.rates)
        initiative = max(0.0, float(rates.get("iniciativa", 0.0)))
        if initiative < float(self.teleport_config.get("initiative_rate_hz", 1.25)):
            return
        if state.energy < 0.22 or rates.get("sonolento", 0.0) > 0.8:
            style_name = "sleepy"
        elif state.stress >= 0.62 or rates.get("assustado", 0.0) > 0.8:
            style_name = "stress"
        elif rates.get("atencao", 0.0) > 1.2:
            style_name = "communicate"
        elif state.happiness >= 0.72 or rates.get("feliz", 0.0) > 0.8:
            style_name = "happy"
        elif state.curiosity >= 0.68 or rates.get("curioso", 0.0) > 0.8:
            style_name = "curious"
        else:
            return

        destination = self._teleport_destination(style_name)
        if destination is None:
            return
        self._begin_teleport(style_name, destination, now)

    def _teleport_destination(self, style_name: str) -> QPoint | None:
        screens = list(QGuiApplication.screens())
        if not screens:
            return None
        targets = [str(value).lower() for value in self.teleport_config.get(
            "targets", ("corners", "near_cursor", "active_window", "center"))]
        style_targets = {
            "curious": ("near_cursor", "active_window", "corners", "center"),
            "happy": ("corners", "center"),
            "stress": ("corners", "center"),
            "sleepy": ("center", "corners"),
            "communicate": ("near_cursor", "active_window", "center"),
        }.get(style_name, ("center",))
        available = [name for name in style_targets if name in targets]
        if not available:
            available = ["center"]
        target = self._teleport_rng.choice(available)
        current = self.frameGeometry().center()
        current_screen = QGuiApplication.screenAt(current) or QGuiApplication.primaryScreen()
        screen = current_screen or screens[0]
        area = screen.availableGeometry()
        width, height = self.width(), self.height()
        self._teleport_look_target = None

        if target == "corners":
            screen = self._teleport_rng.choice(screens)
            area = screen.availableGeometry()
            margin = max(24, int(self.pet_config.get("margin", 24)))
            x = self._teleport_rng.choice((area.left() + margin + width // 2,
                                           area.right() - margin - width // 2))
            y = self._teleport_rng.choice((area.top() + margin + height // 2,
                                           area.bottom() - margin - height // 2))
        elif target == "center":
            x, y = area.center().x(), area.center().y()
            self._teleport_look_target = QPointF(x, y)
        elif target == "near_cursor":
            point = QCursor.pos()
            screen = QGuiApplication.screenAt(point) or screen
            area = screen.availableGeometry()
            self._teleport_look_target = QPointF(point)
            angle = self._teleport_rng.uniform(-math.pi, math.pi)
            distance = self._teleport_rng.uniform(110, 190)
            x = point.x() + round(math.cos(angle) * distance)
            y = point.y() + round(math.sin(angle) * distance)
        else:
            rect = self._active_window_rect()
            if rect is None:
                self._teleport_look_target = QPointF(area.center())
                return QPoint(area.center().x(), area.center().y())
            screen = QGuiApplication.screenAt(rect.center()) or screen
            area = screen.availableGeometry()
            self._teleport_look_target = QPointF(rect.center())
            x, y = rect.right() + width // 2 + 22, rect.bottom() + height // 2 + 22

        area = screen.availableGeometry()
        x = max(area.left() + width // 2,
                min(int(x), area.right() - width // 2))
        y = max(area.top() + height // 2,
                min(int(y), area.bottom() - height // 2))
        if math.hypot(x - current.x(), y - current.y()) < 110:
            x = max(area.left() + width // 2,
                    min(x + 150, area.right() - width // 2))
        return QPoint(x, y)

    def _active_window_rect(self) -> QRect | None:
        if not self._window_geometry_enabled or self._active_window_geometry is None:
            return None
        return QRect(self._active_window_geometry)

    def _begin_teleport(self, style_name: str, destination_center: QPoint,
                        now: float | None = None) -> None:
        if not self._is_floating or self._teleport_animation is not None:
            return
        self._stop_jump(restore_start=False)
        self._stop_pet_animation(restore_start=True)
        start = QRect(self.geometry())
        end = QRect(destination_center.x() - (start.width() - 1) // 2,
                    destination_center.y() - (start.height() - 1) // 2,
                    start.width(), start.height())
        style = TELEPORT_STYLES[style_name]
        self._teleport_start_geometry = start
        self._teleport_destination_geometry = end
        self._teleport_style = style
        self.setMinimumSize(80, 52)
        self._teleport_trail = TeleportTrail(
            QPointF(start.center()), QPointF(end.center()), style, style.duration_ms)
        self._teleport_trail.show()
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(style.duration_ms)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.valueChanged.connect(self._teleport_frame)
        animation.finished.connect(self._finish_teleport)
        self._teleport_animation = animation
        self._last_teleport_at = time.monotonic() if now is None else now
        self._teleport_history.append(self._last_teleport_at)
        animation.start()

    def _teleport_frame(self, value) -> None:
        if self._teleport_start_geometry is None or self._teleport_destination_geometry is None:
            return
        geometry, opacity = teleport_geometry(
            self._teleport_start_geometry, self._teleport_destination_geometry,
            float(value), self._teleport_style)
        self.setGeometry(geometry)
        self.setWindowOpacity(opacity)
        if self._teleport_trail is not None:
            self._teleport_trail.set_progress(float(value))

    def _finish_teleport(self) -> None:
        animation = self._teleport_animation
        self._teleport_animation = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        if self._teleport_destination_geometry is not None and self._is_floating:
            self.setGeometry(self._teleport_destination_geometry)
            self._teleport_blink_until = time.monotonic() + 0.32
            widget = self.canvas._stack.currentWidget()
            target = self._teleport_look_target
            if target is not None:
                center = self._teleport_destination_geometry.center()
                gaze_x = max(-1.0, min(
                    1.0, (target.x() - center.x()) / max(1.0, self.width() * 0.5)))
                gaze_y = max(-1.0, min(
                    1.0, (target.y() - center.y()) / max(1.0, self.height() * 0.5)))
                gaze = (gaze_x, gaze_y)
                if hasattr(widget, "gaze_target"):
                    widget.gaze_target = gaze
                elif hasattr(widget, "gaze"):
                    widget.gaze = gaze
        self.setWindowOpacity(1.0)
        if self._teleport_trail is not None:
            self._teleport_trail.close()
            self._teleport_trail.deleteLater()
        self._teleport_trail = None
        self._teleport_start_geometry = None
        self._teleport_destination_geometry = None
        self._teleport_style = None
        self._teleport_look_target = None

    def _restore_postits(self) -> None:
        for note in self._postit_store.active():
            if len(self._postit_windows) >= self._max_postits():
                break
            if self._postit_text(note.template):
                self._spawn_postit(note, animate=False)

    def _max_postits(self) -> int:
        return max(0, int(self.autonomy_config.get("postits", {}).get(
            "max_active", 4)))

    def _postit_text(self, template: str) -> str:
        templates = self.autonomy_config.get("postits", {}).get("templates", {})
        return str(templates.get(template, ""))

    def _consider_autonomy(self, state: VisualState, health: dict[str, object],
                           now: float) -> None:
        if len(self._postit_windows) >= self._max_postits():
            return
        quiet_after = float(self.autonomy_config.get("quiet_after_interaction_s", 18.0))
        quiet = (now - self.last_interaction < quiet_after or self._pet_hovering
                 or self._pet_drag_offset is not None or self._is_fullscreen_foreground())
        rates = dict(state.rates)
        template = self.autonomy.choose_postit(
            state, rates, now, enabled=bool(self.engine.autonomy_enabled),
            quiet=quiet, proposal_pending=(int(health["pending_proposals"]) > 0
                                           or int(health["proposal_queue"]) > 0))
        if template is None:
            return
        emotion = {"alerta": "estressado", "conversa": "atencao",
                   "pausa": "entediado", "curiosidade": "curioso"}[template]
        if not self._postit_text(template):
            return
        screens = list(QGuiApplication.screens())
        if not screens:
            return
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or screens[0]
        area = screen.availableGeometry()
        width, height = 286, 132
        center = self.frameGeometry().center()
        x = center.x() + self._teleport_rng.choice((-1, 1)) * 150 - width // 2
        y = center.y() - height // 2 - 56
        x = max(area.left(), min(x, area.right() - width + 1))
        y = max(area.top(), min(y, area.bottom() - height + 1))
        postit_cfg = self.autonomy_config.get("postits", {})
        note = self._postit_store.add(
            template, emotion, x, y, float(postit_cfg.get("expires_s", 600.0)))
        origin = center - QPoint(width // 2, height // 2)
        self._spawn_postit(note, animate=True, origin=origin)

    def _spawn_postit(self, note: StoredPostIt, *, animate: bool,
                      origin: QPoint | None = None) -> None:
        if note.note_id in self._postit_windows:
            return
        if len(self._postit_windows) >= self._max_postits():
            return
        screen = QGuiApplication.screenAt(QPoint(note.x, note.y)) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            x = max(area.left(), min(note.x, area.right() - 285))
            y = max(area.top(), min(note.y, area.bottom() - 131))
            if (x, y) != (note.x, note.y):
                self._postit_store.move(note.note_id, x, y)
                note = replace(note, x=x, y=y)
        postit_cfg = self.autonomy_config.get("postits", {})
        window = PostItWindow(
            note, self._postit_text(note.template),
            quick_dismiss_s=float(postit_cfg.get("quick_dismiss_s", 10.0)),
            pixel_theme=self._pixel_theme,
            on_interact=self._postit_interacted,
            on_close=self._postit_closed,
            parent=self, origin=origin, animate=animate)
        self._postit_windows[note.note_id] = window

    def _postit_interacted(self, _note_id: int) -> None:
        self.engine.submit_feedback(0.15, context="postit_interaction")

    def _show_habit_postit(self) -> None:
        if (not self.engine.autonomy_enabled
                or not bool(self.autonomy_config.get("behaviors", {}).get(
                    "habit_notice", True))
                or not bool(self.autonomy_config.get("postits", {}).get("enabled", True))
                or self._is_fullscreen_foreground()
                or len(self._postit_windows) >= self._max_postits()):
            return
        cooldown = float(self.autonomy_config.get("cooldowns_s", {}).get(
            "habit_learned", 3600.0))
        if not self.autonomy.reserve_action("habit_learned", time.monotonic(), cooldown):
            return
        text = self._postit_text("habit")
        screens = list(QGuiApplication.screens())
        if not text or not screens:
            return
        center = self.frameGeometry().center()
        screen = QGuiApplication.screenAt(center) or screens[0]
        area = screen.availableGeometry()
        x = max(area.left(), min(center.x() + 110, area.right() - 285))
        y = max(area.top(), min(center.y() - 100, area.bottom() - 131))
        postit_cfg = self.autonomy_config.get("postits", {})
        note = self._postit_store.add(
            "habit", "curioso", x, y, float(postit_cfg.get("expires_s", 600.0)))
        origin = center - QPoint(143, 66)
        self._spawn_postit(note, animate=True, origin=origin)

    def _postit_closed(self, note_id: int, reason: str, position: QPoint,
                       created_at: float, quick_dismiss_s: float) -> None:
        if reason == "moved":
            self._postit_store.move(note_id, position.x(), position.y())
            return
        self._postit_windows.pop(note_id, None)
        if reason == "app_exit":
            return
        self._postit_store.remove(note_id)
        if reason == "dismissed" and time.time() - created_at <= quick_dismiss_s:
            self.engine.submit_feedback(-0.10, context="postit_quick_dismiss")

    def _is_fullscreen_foreground(self) -> bool:
        return self._active_window_fullscreen

    def _quit_from_tray(self) -> None:
        self._requested_exit = True
        if self._global_hotkey is not None:
            self._global_hotkey.stop()
        for note_window in tuple(self._postit_windows.values()):
            note_window._close_reason = "app_exit"
            note_window.close()
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
        self.window_geometry_action = self.sensor_menu.addAction(
            "Pousar em janelas (somente posição e tamanho)")
        self.window_geometry_action.setCheckable(True)
        self.window_geometry_action.setChecked(self._window_geometry_enabled)
        self.window_geometry_action.setToolTip(
            "Usa somente o retângulo da janela em foco; nunca lê título, texto ou conteúdo.")
        self.window_geometry_action.toggled.connect(
            self._set_window_geometry_enabled)
        self.sensor_menu.addSeparator()
        self.audio_actions = {}
        labels = {
            "microphone": "Ouvir microfone (sem transcrição)",
            "loopback": "Ouvir música do sistema (sem título/artista)",
        }
        privacy_keys = {"microphone": "microphone",
                        "loopback": "system_loopback"}
        for source, label in labels.items():
            action = self.sensor_menu.addAction(label)
            action.setCheckable(True)
            action.setToolTip(
                "Desligado por padrão. Processa janelas curtas em memória; "
                "não grava, envia nem transcreve áudio.")
            enabled = bool(self.audio_privacy.get(privacy_keys[source], False))
            action.setChecked(enabled)
            action.toggled.connect(
                lambda checked, key=source: self._set_audio_enabled(key, checked))
            self.audio_actions[source] = action
            if enabled:
                self._set_audio_enabled(source, True)

    def _poll_window_geometry(self) -> None:
        snapshot = self._window_geometry_observer.poll()
        self._active_window_fullscreen = bool(snapshot and snapshot.fullscreen)
        if (snapshot is not None and not snapshot.fullscreen
                and self._window_geometry_enabled):
            self._active_window_geometry = QRect(
                snapshot.left, snapshot.top, snapshot.width, snapshot.height)
        else:
            self._active_window_geometry = None

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

    def _open_learning(self) -> None:
        if self._learning_panel is None:
            self._learning_panel = LearningPanel(self, self.engine.memory)
        self._learning_panel.show()
        self._learning_panel.raise_()
        self._learning_panel.activateWindow()
        self.last_interaction = time.monotonic()

    def _cycle_mode(self) -> None:
        current = next((i for i, (mode, _) in enumerate(self.MODES)
                        if mode == self.render_mode), 0)
        self._set_mode(self.MODES[(current + 1) % len(self.MODES)][0])

    def _set_mode(self, mode: str) -> None:
        self.render_mode = mode
        self.canvas.set_mode(mode)
        title = (("CENÁRIO" if mode == "ascii" else "HUD") if self._pixel_theme
                 else dict(self.MODES).get(mode, "REALISTA"))
        self.mode_button.setText(f"EXPRESSÕES · {title}")
        self.last_interaction = time.monotonic()

    def request_move(self, target: str | tuple[float, float],
                     style: str = "walk") -> bool:
        """Request a data-driven scene movement from autonomy or a UI action."""
        return self.canvas.request_move(target, style)

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
        proposal_pending = bool(
            self._proposal_name
            and self.engine.proposal_is_pending(self._proposal_name))
        self.canvas.set_motion_blocked(
            dragging=self._pet_drag_offset is not None,
            proposal_pending=proposal_pending)
        if proposal_pending or self._pet_drag_offset is not None:
            self._stop_desktop_motion()
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
            elif operation == "habit_learned":
                self._notice = "PADRÃO DE APRENDIZADO OBSERVADO"
                QTimer.singleShot(0, self._show_habit_postit)
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
        self._update_audio_state(now)
        self._frame_count += 1
        if now - self._fps_started >= 1.0:
            self._fps = self._frame_count
            self._frame_count = 0
            self._fps_started = now
        sleeping = bool(getattr(getattr(self.engine, "sleep", None), "sleeping", False))
        render_state = replace(
            self.last_state,
            render_fps=float(self._fps),
            expression_override=("dormindo" if sleeping else
                                 "piscar" if now < self._teleport_blink_until else
                                 self.last_state.expression_override),
        )
        self.canvas.set_state(render_state)
        period = period_name(datetime.now().astimezone(), self.day_cycle_config)
        self.identity_label.setText(
            "PIU / " + period.upper().replace("MANHA", "MANHÃ"))
        health = self.engine.health_snapshot()
        self._consider_teleport(render_state, health, now)
        self._consider_jump(render_state, health, now)
        self._update_pet_stamina(now)
        self._consider_desktop_motion(render_state, health, now)
        self._consider_autonomy(render_state, health, now)
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
        if self._window_geometry_enabled:
            enabled.append("janela-geometria")
        if self._audio_enabled.get("microphone"):
            enabled.append("microfone")
        if self._audio_enabled.get("loopback"):
            loopback_status = self.audio_service.status_snapshot().get("loopback")
            if loopback_status == "fallback_active":
                enabled.append("música (estado Windows)")
            elif self._audio_music_active and self._audio_bpm > 0.0:
                enabled.append(f"música {round(self._audio_bpm)} BPM")
            else:
                enabled.append("áudio do sistema")
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
            stamina_text = (f" · FÔLEGO {round(self._pet_stamina * 100):02d}%"
                            if self._is_floating else "")
            self.status_label.setText(
                f"{sensor_text.upper()}{stamina_text} · {self._fps:02d} FPS · M / F11 / T")
        active = (self.last_state.active or now - self.last_interaction < 3.0
                  or (not self._is_floating and self.canvas.attention_animating)
                  or self._desktop_animation is not None
                  or self._desktop_behavior in {"think", "rest", "dance", "window_perch"})
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
            for note_window in tuple(self._postit_windows.values()):
                note_window._close_reason = "app_exit"
                note_window.close()
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
        if hasattr(self, "_window_geometry_timer"):
            self._window_geometry_timer.stop()
        self.audio_service.stop_all()
        self._stop_desktop_motion()
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
