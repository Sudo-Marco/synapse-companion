from __future__ import annotations

import math
from pathlib import Path
import time

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QStackedWidget, QWidget

from ..runtime.visual_state import StateAnimator, VisualState
from .ascii_renderer import AsciiRenderer, qimage_rgb
from .ascii_runtime import AnimatedAsciiEyeWidget
from .cpu_renderer import CpuEyeWidget
from .interaction import AffectionDragTracker


class OpenGLEyeWidget(QOpenGLWidget):
    fallbackRequested = Signal(str)
    rendererReady = Signal(str)
    petRequested = Signal()
    activityDetected = Signal()

    def __init__(self, width: int, height: int, ascii_columns: int,
                 ascii_rows: int, palette: str, max_particles: int,
                 parent: QWidget | None = None,
                 affection_drag_min_s: float = 1.0) -> None:
        super().__init__(parent)
        self.setMinimumSize(700, 390)
        self.setMouseTracking(True)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        self.setToolTip(
            f"Mova para direcionar o olhar; arraste sobre o olho por {affection_drag_min_s:g}s "
            "ou use CARINHO.")
        self.internal_width = max(320, width)
        self.internal_height = max(240, height)
        self.max_particles = max(1, min(48, int(max_particles)))
        self.state = VisualState()
        self.target_state = self.state
        self.animator = StateAnimator(self.state)
        self._opening_value = 0.84
        self._opening_time = 0.0
        self.mode = "shader"
        self.gaze = (0.0, 0.0)
        self._drag_tracker = AffectionDragTracker(affection_drag_min_s)
        self._ascii = AsciiRenderer(ascii_columns, ascii_rows, palette,
                                   self.internal_width, self.internal_height)
        self._ctx = self._program = self._vao = self._fbo = None
        self._blit_program = self._blit_vao = None
        self.rendered_frames = 0
        self._error = ""
        self.renderer_name = "moderngl / OpenGL 3.3"
        self._checked_modes: set[str] = set()

    def initializeGL(self) -> None:
        try:
            import moderngl
            from importlib.resources import files

            self._ctx = moderngl.create_context(require=330)
            vertex = """#version 330
            in vec2 in_pos;
            in vec2 in_uv;
            out vec2 v_uv;
            void main() {
                gl_Position = vec4(in_pos, 0.0, 1.0);
                v_uv = in_uv;
            }
            """
            fragment = files("synapse_pet.ui").joinpath("shaders/eye.frag").read_text(encoding="utf-8")
            self._program = self._ctx.program(vertex_shader=vertex, fragment_shader=fragment)
            vertices = np.asarray((
                -1, -1, 0, 0,  1, -1, 1, 0,
                -1,  1, 0, 1,  1,  1, 1, 1,
            ), dtype="f4")
            self._vbo = self._ctx.buffer(vertices.tobytes())
            self._vao = self._ctx.vertex_array(
                self._program, [(self._vbo, "2f 2f", "in_pos", "in_uv")])
            self._blit_program = self._ctx.program(
                vertex_shader=vertex,
                fragment_shader="""#version 330
                in vec2 v_uv;
                uniform sampler2D u_source;
                out vec4 fragColor;
                void main() { fragColor = texture(u_source, v_uv); }
                """)
            self._blit_vao = self._ctx.vertex_array(
                self._blit_program, [(self._vbo, "2f 2f", "in_pos", "in_uv")])
            self._texture = self._ctx.texture(
                (self.internal_width, self.internal_height), 4, dtype="f1")
            self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._fbo = self._ctx.framebuffer(color_attachments=[self._texture])
            self._ctx.disable(moderngl.DEPTH_TEST | moderngl.BLEND)
            self.rendererReady.emit(f"ModernGL {moderngl.__version__} / OpenGL {self._ctx.version_code}")
        except Exception as exc:
            self._error = f"OpenGL 3.3 indisponível: {exc}"
            QTimer.singleShot(0, lambda: self.fallbackRequested.emit(self._error))

    def set_state(self, state: VisualState) -> None:
        self.target_state = state
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        nx = max(0.0, min(1.0, point.x() / max(1, self.width())))
        ny = max(0.0, min(1.0, point.y() / max(1, self.height())))
        self.gaze = (nx * 2.0 - 1.0, ny * 2.0 - 1.0)
        if self._drag_tracker.move(
                point.x(), point.y(), self.width(), self.height(),
                bool(event.buttons() & Qt.MouseButton.LeftButton)):
            self.petRequested.emit()
        self.activityDetected.emit()
        self.update()
        super().mouseMoveEvent(event)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:
        self._drag_tracker.press(
            event.position().x(), event.position().y(), self.width(), self.height(),
            event.button() == Qt.MouseButton.LeftButton)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_tracker.release():
                self.petRequested.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._drag_tracker.cancel()
        super().leaveEvent(event)

    def _target_opening(self) -> float:
        state = self.state
        override = state.expression_override
        if override == "aberto":
            return 0.88
        if override == "semicerrado":
            return 0.54
        if override == "arregalado":
            return 1.04
        if override == "piscar":
            return 0.92
        if state.emotion == "alegre":
            return 0.89
        if state.emotion == "estressado":
            return 0.68
        if state.emotion == "triste":
            return 0.62
        if state.emotion == "curioso":
            return 1.0
        if state.emotion == "sonolento":
            return 0.42
        return 0.42 + 0.54 * max(0.0, min(1.0, state.energy))

    def _advance_opening(self, now: float) -> None:
        dt = 1.0 / 30.0 if self._opening_time == 0 else max(0.0, min(0.5, now - self._opening_time))
        self._opening_time = now
        blend = 1.0 - math.exp(-dt / 0.15)
        self._opening_value += (self._target_opening() - self._opening_value) * blend

    def _uniforms(self, now: float) -> None:
        p = self._program
        s = self.state
        p["u_resolution"].value = (float(self.internal_width), float(self.internal_height))
        p["u_gaze"].value = tuple(float(v) for v in self.gaze)
        p["u_time"].value = float(now)
        p["u_happiness"].value = float(s.happiness)
        p["u_energy"].value = float(s.energy)
        p["u_stress"].value = float(s.stress)
        p["u_curiosity"].value = float(s.curiosity)
        p["u_rate"].value = float(s.firing_rate)
        p["u_dopamine"].value = float(s.dopamine)
        p["u_open"].value = float(self._opening_value)
        expression = {"alegre": 1, "estressado": 2, "triste": 3,
                      "curioso": 4, "sonolento": 5, "piscar": 6,
                      "aberto": 7, "semicerrado": 8,
                      "arregalado": 9}.get(s.emotion, 0)
        p["u_emotion"].value = expression
        particles = np.zeros((48, 4), dtype="f4")
        ids = s.spike_ids[:self.max_particles]
        for index, neuron_id in enumerate(ids):
            angle = neuron_id * 2.399963229728653
            radius = 0.31 + 0.15 * ((neuron_id * 0.61803398875) % 1.0)
            particles[index] = (
                0.5 + math.cos(angle) * radius,
                0.5 + math.sin(angle) * radius * 0.66,
                0.0035 + (neuron_id % 3) * 0.0008,
                0.52 + min(0.48, s.firing_rate * 10.0),
            )
        p["u_particle_count"].value = len(ids)
        p["u_particles"].write(particles.tobytes())

    def _image_from_gl(self) -> QImage:
        raw = self._fbo.read(components=4, alignment=1)
        pixels = np.frombuffer(raw, dtype=np.uint8).reshape(
            self.internal_height, self.internal_width, 4)[::-1].copy()
        data = pixels.tobytes()
        return QImage(data, self.internal_width, self.internal_height,
                      self.internal_width * 4, QImage.Format.Format_RGBA8888).copy()

    def _validate_screen_once(self, framebuffer) -> None:
        """Fall back if a driver's first completed frame is visibly corrupted."""
        if self.mode in self._checked_modes:
            return
        try:
            width, height = framebuffer.size
            raw = framebuffer.read(components=4, alignment=1)
            pixels = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
        except Exception:
            # Some window-system framebuffers cannot be read back; shader
            # compilation and normal rendering remain the compatibility check.
            self._checked_modes.add(self.mode)
            return
        red_blocks = ((pixels[..., 0] > 150) & (pixels[..., 1] < 50)
                      & (pixels[..., 2] < 50))
        ratio = float(red_blocks.mean())
        if ratio > 0.025:
            raise RuntimeError(
                f"OpenGL framebuffer has {ratio:.1%} bright red pixels; "
                "switching to the QPainter compatibility renderer")
        self._checked_modes.add(self.mode)

    def paintGL(self) -> None:
        self.rendered_frames += 1
        if self._ctx is not None and self._fbo is not None:
            try:
                now = time.monotonic()
                self.state = self.animator.advance(self.target_state, now)
                self._advance_opening(now)
                self._uniforms(now)
                self._fbo.use()
                self._ctx.viewport = (0, 0, self.internal_width, self.internal_height)
                self._vao.render(self._ctx.TRIANGLE_STRIP)
                display_texture = self._texture
                temporary_texture = None
                if self.mode in {"ascii", "hud"}:
                    image = self._image_from_gl()
                    if self.mode == "ascii":
                        image = self._ascii.render(image)
                    else:
                        hud_painter = QPainter(image)
                        CpuEyeWidget._draw_hud(self, hud_painter)
                        hud_painter.end()
                    pixels = np.ascontiguousarray(qimage_rgb(image)[::-1]).tobytes()
                    temporary_texture = self._ctx.texture(
                        (image.width(), image.height()), 3, pixels, alignment=1)
                    temporary_texture.filter = (self._ctx.LINEAR, self._ctx.LINEAR)
                    display_texture = temporary_texture
                screen = self._ctx.detect_framebuffer(self.defaultFramebufferObject())
                screen.use()
                dpr = self.devicePixelRatioF()
                self._ctx.viewport = (0, 0, int(self.width() * dpr), int(self.height() * dpr))
                display_texture.use(location=0)
                self._blit_program["u_source"].value = 0
                self._blit_vao.render(self._ctx.TRIANGLE_STRIP)
                if temporary_texture is not None:
                    temporary_texture.release()
                self._validate_screen_once(screen)
            except Exception as exc:
                self._error = f"Falha no shader; usando QPainter: {exc}"
                QTimer.singleShot(0, lambda: self.fallbackRequested.emit(self._error))

    def _cpu_frame(self) -> QImage:
        self._cpu.target_state, self._cpu.gaze = self.target_state, self.gaze
        self._cpu.mode = self.mode
        return self._cpu.render_frame()

    def releaseGL(self) -> None:
        for resource_name in ("_fbo", "_texture", "_blit_vao", "_blit_program",
                              "_vao", "_vbo", "_program", "_ctx"):
            resource = getattr(self, resource_name, None)
            if resource is not None:
                try:
                    resource.release()
                except Exception:
                    pass
                setattr(self, resource_name, None)


class EyeCanvas(QWidget):
    petRequested = Signal()
    panelRequested = Signal()
    rendererChanged = Signal(str)
    activityDetected = Signal()
    animationStarted = Signal()

    def __init__(self, renderer: str, width: int, height: int,
                 ascii_columns: int, ascii_rows: int, palette: str,
                 max_particles: int, parent: QWidget | None = None,
                 scene_time: str = "auto", eye_design: str = "A",
                 ascii_max_columns: int = 170,
                 ascii_max_rows: int = 96,
                 affection_drag_min_s: float = 1.0,
                 compact: bool = False,
                 render_style: str = "spectral",
                 spectral_config: dict | None = None) -> None:
        super().__init__(parent)
        self.renderer_config = renderer.lower()
        self.render_style = (render_style if render_style in {"spectral", "ascii", "vector"}
                             else "spectral")
        spectral_config = spectral_config or {}
        self._state = VisualState()
        self._mode = "ascii"
        self._stack = QStackedWidget(self)
        self._ascii_eye: AnimatedAsciiEyeWidget | None = None
        self._cpu: CpuEyeWidget | AnimatedAsciiEyeWidget | None = None
        self._gl: OpenGLEyeWidget | None = None
        self._fallback_timer: QTimer | None = None
        use_direct = (compact or self.render_style in {"spectral", "vector"}
                      or self.renderer_config in {"ascii", "cpu"})
        if use_direct:
            self._ascii_eye = AnimatedAsciiEyeWidget(
                ascii_columns, ascii_rows, scene_time, eye_design, max_particles,
                max_columns=ascii_max_columns, max_rows=ascii_max_rows,
                affection_drag_min_s=affection_drag_min_s, compact=compact,
                render_style=self.render_style, spectral_config=spectral_config)
            self._cpu = self._ascii_eye
            self._ascii_eye.petRequested.connect(self.petRequested.emit)
            self._ascii_eye.panelRequested.connect(self.panelRequested.emit)
            self._ascii_eye.activityDetected.connect(self.activityDetected.emit)
            self._ascii_eye.animationStarted.connect(self.animationStarted.emit)
            self._stack.addWidget(self._ascii_eye)
            self._stack.setCurrentWidget(self._ascii_eye)
            self.renderer_name = {
                "spectral": "Olho espectral · QPainter",
                "ascii": "ASCII direto · PySide6",
                "vector": "Olho vetorial · QPainter",
            }[self.render_style]
        else:
            self._cpu = CpuEyeWidget(
                width, height, ascii_columns, ascii_rows, palette,
                affection_drag_min_s=affection_drag_min_s)
            self._cpu.petRequested.connect(self.petRequested.emit)
            self._stack.addWidget(self._cpu)
        if self._ascii_eye is None and self.renderer_config != "cpu":
            self._gl = OpenGLEyeWidget(width, height, ascii_columns, ascii_rows,
                                       palette, max_particles,
                                       affection_drag_min_s=affection_drag_min_s)
            self._gl.petRequested.connect(self.petRequested.emit)
            self._gl.activityDetected.connect(self.activityDetected.emit)
            self._gl.fallbackRequested.connect(self._activate_cpu)
            self._gl.rendererReady.connect(self._activate_gl)
            self._stack.addWidget(self._gl)
            self._stack.setCurrentWidget(self._gl)
            self._fallback_timer = QTimer(self)
            self._fallback_timer.setSingleShot(True)
            self._fallback_timer.timeout.connect(self._check_gl)
            self._fallback_timer.start(900)
            self.renderer_name = "OpenGL 3.3 inicializando"
        elif self._ascii_eye is None:
            self.renderer_name = "QPainter CPU"
            self.rendererChanged.emit(self.renderer_name)

        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self.setMinimumSize(80, 52) if compact else self.setMinimumSize(700, 390)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def attention_animating(self) -> bool:
        return bool(self._ascii_eye and self._ascii_eye.attention_animating)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        if self._ascii_eye is not None:
            self._ascii_eye.set_mode(mode)
            return
        backend_mode = ("shader" if self.render_style == "vector" and mode == "ascii"
                        else mode)
        self._cpu.set_mode(backend_mode)
        if self._gl is not None:
            self._gl.set_mode(backend_mode)

    def set_state(self, state: VisualState) -> None:
        self._state = state
        self._cpu.set_state(state)
        if self._gl is not None:
            self._gl.set_state(state)

    def _check_gl(self) -> None:
        if self._gl is not None and not self._gl.isValid():
            self._activate_cpu("QOpenGLWidget sem contexto válido")

    def _activate_cpu(self, reason: str) -> None:
        if self._stack.currentWidget() is self._cpu:
            return
        self._cpu.set_state(self._state)
        backend_mode = ("shader" if self.render_style == "vector" and self._mode == "ascii"
                        else self._mode)
        self._cpu.set_mode(backend_mode)
        self._stack.setCurrentWidget(self._cpu)
        self.renderer_name = "QPainter CPU"
        self.rendererChanged.emit(self.renderer_name + " · " + reason[:90])

    def current_frame(self) -> QImage:
        widget = self._stack.currentWidget()
        if widget is self._ascii_eye:
            return self._ascii_eye.current_frame()
        if isinstance(widget, OpenGLEyeWidget):
            return widget.grabFramebuffer()
        return widget.grab().toImage()

    def _activate_gl(self, name: str) -> None:
        self.renderer_name = name
        self.rendererChanged.emit(name)

    @property
    def rendered_frames(self) -> int:
        return self._stack.currentWidget().rendered_frames

    @property
    def current_renderer(self) -> str:
        return self.renderer_name
