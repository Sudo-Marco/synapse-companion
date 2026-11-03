from __future__ import annotations

import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from ..runtime.engine import PetEngine
from .avatar import Avatar
from .debug_panel import DebugPanel


BG = "#070b10"
PANEL = "#0d141c"
PANEL_ALT = "#111b24"
LINE = "#1a3039"
CYAN = "#31d7e4"
GOLD = "#e9b725"
TEXT = "#d8e4e7"
MUTED = "#70858d"

SENSOR_LABELS = {
    "input_activity": "Contar atividade de teclado e mouse",
    "active_window": "Categorizar aplicativo em foco",
    "file_events": "Monitorar uma pasta escolhida",
    "clipboard": "Detectar mudança no clipboard",
    "system_stats": "Ler CPU e memória",
}


class PetWindow:
    """Desktop shell for the eye avatar, feedback, sensors, and proposals."""

    def __init__(self, engine: PetEngine) -> None:
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("Synapse Pet — Oculus")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self._allow_restore = False
        self._drag_origin: tuple[int, int] | None = None
        self._proposal_name: str | None = None
        self._demo_mode = False
        self._demo_started = 0.0
        self._affection_reaction_until = 0.0

        width, height = 636, 696
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.bind("<Map>", self._on_map)
        self.root.bind("<Button-3>", self._show_sensor_menu)

        self._build_titlebar()
        self.avatar = Avatar(self.root, width=600, height=360)
        self.avatar.pack(padx=18, pady=(13, 9))
        self.avatar.bind("<Motion>", self.avatar.look_at)

        self._build_identity()
        self._build_metrics()
        self._build_proposal()
        self._build_feedback()
        self._build_toolbar()
        self._build_footer()
        self._build_sensor_menu()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.engine.start()
        self.root.after(120, self.refresh)

    def _build_titlebar(self) -> None:
        bar = tk.Frame(self.root, bg="#0b1118", height=42,
                       highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        mark = tk.Label(bar, text="◉", bg="#0b1118", fg=CYAN,
                        font=("Segoe UI Symbol", 16, "bold"))
        mark.pack(side="left", padx=(14, 8))
        title = tk.Label(bar, text="SYNAPSE PET", bg="#0b1118", fg=TEXT,
                         font=("Consolas", 10, "bold"))
        title.pack(side="left")
        subtitle = tk.Label(bar, text="  /  OCULUS", bg="#0b1118", fg=GOLD,
                            font=("Consolas", 9))
        subtitle.pack(side="left")
        local = tk.Label(bar, text="●  LOCAL", bg="#0b1118", fg="#69c99c",
                         font=("Consolas", 8, "bold"))
        local.pack(side="right", padx=12)
        self._button(bar, "—", self._minimize, bg="#0b1118", fg=MUTED,
                     hover="#26343e", width=3, help_text="Minimiza o olho na barra de tarefas.").pack(side="right")
        self._button(bar, "×", self.close, bg="#0b1118", fg=MUTED,
                     hover="#8f3e49", width=3, help_text="Fecha o Synapse Pet e salva o estado.").pack(side="right")
        for widget in (bar, mark, title, subtitle, local):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_motion)

    def _button(self, parent: tk.Misc, text: str, command,
                *, bg: str = PANEL_ALT, fg: str = TEXT, hover: str = "#1c333d",
                width: int | None = None, font: tuple = ("Segoe UI", 9, "bold"),
                help_text: str = "") -> tk.Button:
        options = {"text": text, "command": command, "bg": bg, "fg": fg,
                   "activebackground": hover, "activeforeground": TEXT,
                   "relief": "flat", "bd": 0, "highlightthickness": 1,
                   "highlightbackground": LINE, "highlightcolor": CYAN,
                   "font": font, "padx": 12, "pady": 9, "cursor": "hand2"}
        if width is not None:
            options["width"] = width
        button = tk.Button(parent, **options)
        button.bind("<Enter>", lambda _event: self._button_hover(button, hover, help_text))
        button.bind("<Leave>", lambda _event: self._button_unhover(button, bg))
        return button

    def _button_hover(self, button: tk.Button, color: str, help_text: str) -> None:
        button.configure(bg=color)
        if help_text and hasattr(self, "help_status"):
            self.help_status.configure(text=help_text, fg=CYAN)

    def _button_unhover(self, button: tk.Button, color: str) -> None:
        button.configure(bg=color)
        if hasattr(self, "help_status"):
            self.help_status.configure(text=self._default_help(), fg=MUTED)

    def _default_help(self) -> str:
        return ("CICLO DE EXPRESSÕES ATIVO · apenas visual" if self._demo_mode
                else "Passe o cursor nos controles para ver o que cada um faz.")

    def _build_identity(self) -> None:
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=22, pady=(1, 8))
        left = tk.Frame(row, bg=BG)
        left.pack(side="left")
        tk.Label(left, text="OCULUS / NOCTURNE", bg=BG, fg=TEXT,
                 font=("Consolas", 10, "bold")).pack(anchor="w")
        self.mood_text = tk.Label(left, text="observando em silêncio", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 9))
        self.mood_text.pack(anchor="w", pady=(3, 0))
        self.system_text = tk.Label(row, text="SNN  ·  ESTÁVEL", bg=BG, fg=CYAN,
                                    font=("Consolas", 8))
        self.system_text.pack(side="right", anchor="center")

    def _metric_card(self, parent: tk.Misc, title: str, value: float, color: str,
                     column: int) -> tuple[tk.Label, tk.Canvas]:
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        card.grid(row=0, column=column, sticky="ew", padx=4)
        parent.grid_columnconfigure(column, weight=1, uniform="metric")
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x", padx=10, pady=(8, 3))
        tk.Label(top, text=title, bg=PANEL, fg=MUTED,
                 font=("Consolas", 7, "bold")).pack(side="left")
        label = tk.Label(top, text=f"{value:02.0f}%", bg=PANEL, fg=TEXT,
                         font=("Consolas", 8, "bold"))
        label.pack(side="right")
        track = tk.Canvas(card, height=5, bg="#1b2830", highlightthickness=0)
        track.pack(fill="x", padx=10, pady=(0, 9))
        track.create_rectangle(0, 0, 1, 5, fill=color, outline="", tags="fill")
        track._accent = color
        return label, track

    def _build_metrics(self) -> None:
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=18, pady=(0, 9))
        self.happiness_metric = self._metric_card(row, "HUMOR", .5, GOLD, 0)
        self.energy_metric = self._metric_card(row, "ENERGIA", .8, CYAN, 1)
        self.alert_metric = self._metric_card(row, "ALERTA", .1, "#d77b62", 2)

    def _build_proposal(self) -> None:
        self.proposal = tk.Frame(self.root, bg="#13202a",
                                 highlightthickness=1, highlightbackground=GOLD)
        self.proposal_title = tk.Label(self.proposal, text="SUGESTÃO DO OLHO",
                                       bg="#13202a", fg=GOLD,
                                       font=("Consolas", 8, "bold"))
        self.proposal_title.pack(anchor="w", padx=12, pady=(9, 0))
        self.proposal_description = tk.Label(self.proposal, text="", bg="#13202a",
                                             fg=TEXT, font=("Segoe UI", 9),
                                             wraplength=580, justify="left")
        self.proposal_description.pack(anchor="w", padx=12, pady=(4, 8))
        actions = tk.Frame(self.proposal, bg="#13202a")
        actions.pack(fill="x", padx=8, pady=(0, 8))
        self._button(actions, "ACEITAR", lambda: self._answer_proposal(True),
                     bg="#17413f", fg="#8fe5d0", hover="#205650",
                     help_text="Aceita a sugestão e executa a ferramenta.").pack(side="left", expand=True, fill="x", padx=3)
        self._button(actions, "RECUSAR", lambda: self._answer_proposal(False),
                     bg="#3a2528", fg="#ed9a8b", hover="#5a3036",
                     help_text="Recusa a sugestão e ensina o Pet a evitar esse momento.").pack(side="left", expand=True, fill="x", padx=3)
        self._button(actions, "DEPOIS", lambda: self._answer_proposal(None),
                     bg="#202c35", fg=TEXT, hover="#334550",
                     help_text="Adia a decisão e envia apenas um sinal leve.").pack(side="left", expand=True, fill="x", padx=3)
        self.proposal.pack_forget()

    def _build_feedback(self) -> None:
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=18, pady=(2, 7))
        self.feedback_row = row
        self._button(row, "♡   CARINHO", self._give_affection,
                     bg="#163438", fg="#83e5df", hover="#205057",
                     font=("Segoe UI", 10, "bold"),
                     help_text="Aumenta o humor, reduz o tédio e registra carinho.").pack(side="left", expand=True, fill="x", padx=4)
        self._button(row, "◌   FEEDBACK", lambda: self.engine.submit_feedback(-1),
                     bg="#29242b", fg="#e3a79b", hover="#47313a",
                     font=("Segoe UI", 10, "bold"),
                     help_text="Dá uma avaliação negativa para ajustar o comportamento.").pack(side="left", expand=True, fill="x", padx=4)

    def _build_toolbar(self) -> None:
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=18, pady=(0, 9))
        self._button(row, "DEBUG", lambda: DebugPanel(self.root, self.engine),
                     bg=PANEL, fg=CYAN, hover="#17313a", font=("Segoe UI", 8, "bold"),
                     help_text="Abre taxas, emoções, dopamina e disparos dos neurônios.").pack(side="left", expand=True, fill="x", padx=2)
        self._button(row, "SENSORES", self._show_sensor_menu,
                     bg=PANEL, fg=GOLD, hover="#382f1b", font=("Segoe UI", 8, "bold"),
                     help_text="Liga ou desliga sensores; todos começam desligados.").pack(side="left", expand=True, fill="x", padx=2)
        self.demo_button = self._button(row, "EXPRESSÕES", self._toggle_demo,
                     bg=PANEL, fg="#d8a8ff", hover="#392b49", font=("Segoe UI", 8, "bold"),
                     help_text="Mostra alegria, estresse, tristeza e calma sem alterar o aprendizado.")
        self.demo_button.pack(side="left", expand=True, fill="x", padx=2)
        self._button(row, "DESFAZER", self._undo,
                     bg=PANEL, fg=TEXT, hover="#27343c", font=("Segoe UI", 8, "bold"),
                     help_text="Desfaz a última ação que tenha suporte a undo.").pack(side="left", expand=True, fill="x", padx=2)
        self._button(row, "SALVAR", self._save,
                     bg=PANEL, fg=TEXT, hover="#27343c", font=("Segoe UI", 8, "bold"),
                     help_text="Grava agora o estado, personalidade e pesos da criatura.").pack(side="left", expand=True, fill="x", padx=2)

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg="#0b1118", height=45,
                          highlightthickness=1, highlightbackground=LINE)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.help_status = tk.Label(footer, text=self._default_help(), bg="#0b1118",
                                    fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.help_status.pack(fill="x", padx=14, pady=(4, 0))
        bottom = tk.Frame(footer, bg="#0b1118")
        bottom.pack(fill="x", side="bottom")
        self.sensor_status = tk.Label(footer, text="SENSORES DESLIGADOS",
                                      bg="#0b1118", fg=MUTED,
                                      font=("Consolas", 8))
        self.sensor_status.pack(in_=bottom, side="left", padx=14, pady=(0, 5))
        self.footer_status = tk.Label(footer, text="100% LOCAL  ·  PRIVACIDADE ATIVA",
                                      bg="#0b1118", fg="#5d9f8e",
                                      font=("Consolas", 7))
        self.footer_status.pack(in_=bottom, side="right", padx=14, pady=(0, 5))

    def _build_sensor_menu(self) -> None:
        self.sensor_menu = tk.Menu(self.root, tearoff=False, bg="#111a22", fg=TEXT,
                                   activebackground="#1e3e48", activeforeground=CYAN,
                                   selectcolor=CYAN, font=("Segoe UI", 9))
        self.sensor_vars: dict[str, tk.BooleanVar] = {}
        for name, label in SENSOR_LABELS.items():
            var = tk.BooleanVar(value=self.engine.sensor_manager.sensors[name].enabled)
            self.sensor_vars[name] = var
            self.sensor_menu.add_checkbutton(
                label=label, variable=var,
                command=lambda n=name, v=var: self._toggle_sensor(n, v.get()))

    def _show_sensor_menu(self, event: tk.Event | None = None) -> None:
        if event is None:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
        else:
            x, y = event.x_root, event.y_root
        self.sensor_menu.tk_popup(x, y)

    def _toggle_sensor(self, name: str, enabled: bool) -> None:
        if name == "file_events" and enabled:
            folder = filedialog.askdirectory(title="Escolha uma pasta monitorada")
            if not folder:
                self.sensor_vars[name].set(False)
                return
            self.engine.sensor_manager.sensors[name].folder = Path(folder)
        self.engine.set_sensor_enabled(name, enabled)

    def _answer_proposal(self, accepted: bool | None) -> None:
        if self._proposal_name is not None:
            self.engine.submit_tool_response(self._proposal_name, accepted,
                                             getattr(self, "_proposal_context", "outro"))
        self._proposal_name = None
        self.proposal.pack_forget()

    def _save(self) -> None:
        self.engine.submit_save()

    def _undo(self) -> None:
        result = self.engine.undo_last()
        if result.get("status") == "nothing_to_undo":
            self.footer_status.configure(text="NADA PARA DESFAZER", fg=GOLD)
        else:
            self.footer_status.configure(text="ÚLTIMA AÇÃO DESFEITA", fg=CYAN)

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_origin is not None:
            x = event.x_root - self._drag_origin[0]
            y = event.y_root - self._drag_origin[1]
            self.root.geometry(f"+{x}+{y}")

    def _minimize(self) -> None:
        self._allow_restore = True
        self.root.overrideredirect(False)
        self.root.iconify()

    def _on_map(self, _event: tk.Event) -> None:
        if self._allow_restore:
            self.root.after(30, self._restore_border)

    def _restore_border(self) -> None:
        if self._allow_restore:
            self.root.overrideredirect(True)
            self._allow_restore = False

    @staticmethod
    def _emotion_label(happiness: float, fear: float, energy: float,
                       boredom: float = 0.) -> str:
        if fear >= .62:
            return "estressado — buscando um momento de calma"
        if energy <= .18:
            return "sonolento — descansando o olhar"
        if happiness >= .72:
            return "alegre — brilho no olhar"
        if happiness <= .32 or boredom >= .82:
            return "triste — precisa de um pouco de carinho"
        return "observando em silêncio"

    def _toggle_demo(self) -> None:
        self._demo_mode = not self._demo_mode
        if self._demo_mode:
            self._demo_started = time.monotonic()
            self.demo_button.configure(text="PARAR CICLO")
            self.help_status.configure(
                text="DEMO VISUAL · alterna expressões sem mudar humor ou aprendizado.",
                fg="#d8a8ff")
        else:
            self.demo_button.configure(text="EXPRESSÕES")
            self.help_status.configure(text=self._default_help(), fg=MUTED)

    def _give_affection(self) -> None:
        self.engine.submit_affection()
        self._affection_reaction_until = time.monotonic() + 1.8

    def _update_metric(self, metric: tuple[tk.Label, tk.Canvas], value: float) -> None:
        label, bar = metric
        value = max(0.0, min(1.0, value))
        label.configure(text=f"{value * 100:02.0f}%")
        bar.delete("fill")
        width = max(1, int(bar.winfo_width() * value))
        bar.create_rectangle(0, 0, width, 5, fill=bar._accent, outline="", tags="fill")

    def refresh(self) -> None:
        if not self.root.winfo_exists():
            return
        e = self.engine.emotions
        demo_mode = None
        if self._demo_mode:
            demo_states = (
                ("observando", .52, .78, .12, .45, .20),
                ("alegre", .92, .86, .08, .82, .08),
                ("estressado", .24, .54, .88, .66, .42),
                ("triste", .18, .30, .18, .12, .91),
                ("sonolento", .43, .12, .10, .18, .48),
            )
            phase = int((time.monotonic() - self._demo_started) / 3.6)
            demo_mode, happiness, energy, fear, curiosity, boredom = demo_states[
                phase % len(demo_states)]
            self.system_text.configure(text="DEMO VISUAL  ·  SEM APRENDIZADO",
                                       fg="#d8a8ff")
        else:
            happiness, energy, fear, curiosity = (
                e.happiness, e.energy, e.fear, e.curiosity)
            boredom = getattr(e, "boredom", 0.)
            self.system_text.configure(text="SNN  ·  ESTÁVEL", fg=CYAN)
        reacting_to_affection = (not self._demo_mode
                                 and time.monotonic() < self._affection_reaction_until)
        self.avatar.draw(happiness, energy, fear, curiosity, boredom,
                         mode=demo_mode or ("alegre" if reacting_to_affection else None))
        self.mood_text.configure(text=("sentiu o carinho — ficou contente"
                                       if reacting_to_affection else
                                       self._emotion_label(happiness, fear, energy, boredom)))
        self._update_metric(self.happiness_metric, happiness)
        self._update_metric(self.energy_metric, energy)
        self._update_metric(self.alert_metric, fear)
        enabled = [name for name, var in self.sensor_vars.items() if var.get()]
        self.sensor_status.configure(text=("SENSORES: " + " · ".join(enabled)).upper()
                                     if enabled else "SENSORES DESLIGADOS")
        try:
            candidate = self.engine.proposals.get_nowait()
        except queue.Empty:
            candidate = None
        if candidate is not None and self._proposal_name is None:
            manifest = self.engine.registry.get(candidate.name)
            self._proposal_name = candidate.name
            self._proposal_context = candidate.context
            self.proposal_description.configure(text=manifest.description)
            self.proposal.pack(fill="x", padx=18, pady=(0, 8), before=self.feedback_row)
        self.root.after(33, self.refresh)

    def close(self) -> None:
        self.engine.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
