from __future__ import annotations

import tkinter as tk


BG = "#070b10"
PANEL = "#0d141c"
LINE = "#1a3039"
CYAN = "#31d7e4"
GOLD = "#e9b725"
TEXT = "#d8e4e7"
MUTED = "#71858d"


class DebugPanel:
    """On-demand neural telemetry; the plots stop when the panel closes."""

    def __init__(self, master: tk.Misc, engine: object) -> None:
        self.engine = engine
        self.window = tk.Toplevel(master)
        self.window.title("Oculus // Neural telemetry")
        self.window.configure(bg=BG)
        self.window.geometry("540x500")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.spike_history: list[object] = []
        self.dopamine_history: list[float] = []

        header = tk.Frame(self.window, bg="#0b1118", height=48,
                          highlightthickness=1, highlightbackground=LINE)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="◉", bg="#0b1118", fg=CYAN,
                 font=("Segoe UI Symbol", 16, "bold")).pack(side="left", padx=14)
        tk.Label(header, text="NEURAL TELEMETRY", bg="#0b1118", fg=TEXT,
                 font=("Consolas", 10, "bold")).pack(side="left")
        tk.Label(header, text="LIVE  /  LOCAL", bg="#0b1118", fg=GOLD,
                 font=("Consolas", 8)).pack(side="right", padx=14)

        self.readout = tk.Label(self.window, text="", bg=BG, fg=TEXT,
                                justify="left", anchor="w",
                                font=("Consolas", 9), padx=18, pady=12)
        self.readout.pack(fill="x")

        tk.Label(self.window, text="DOPAMINE TRACE", bg=BG, fg=MUTED,
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=18, pady=(3, 5))
        self.dopamine_plot = tk.Canvas(self.window, height=94, bg=PANEL,
                                       highlightthickness=1, highlightbackground=LINE)
        self.dopamine_plot.pack(fill="x", padx=16)
        tk.Label(self.window, text="SPIKE RASTER  /  RECENT TICKS", bg=BG, fg=MUTED,
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=18, pady=(13, 5))
        self.raster = tk.Canvas(self.window, height=145, bg=PANEL,
                                highlightthickness=1, highlightbackground=LINE)
        self.raster.pack(fill="x", padx=16)
        tk.Label(self.window, text="Plots run only while this panel is open.",
                 bg=BG, fg="#4f6972", font=("Segoe UI", 8)).pack(anchor="e", padx=18, pady=10)
        self.refresh()

    def refresh(self) -> None:
        if not self.window.winfo_exists():
            return
        e = self.engine
        mood = e.emotions
        spikes = e.network.population.spikes.copy()
        self.spike_history = (self.spike_history + [spikes])[-45:]
        self.dopamine_history = (self.dopamine_history + [e.neuromodulators.dopamine])[-100:]
        self.readout.configure(text=(
            f"SYSTEM   STABLE       TICKS {e.network.tick_count:>8}\n"
            f"NETWORK  {e.network.population.size:>4} NEURONS   "
            f"{len(e.network.recurrent.weights):>5} RECURRENT EDGES\n"
            f"DOPAMINE {e.neuromodulators.dopamine:+.3f}       "
            f"STRESS {e.neuromodulators.stress:.2f}       ENERGY {e.neuromodulators.energy:.2f}\n"
            f"MOOD     {mood.happiness:.2f}       CURIOSITY {mood.curiosity:.2f}       "
            f"TRUST {mood.trust:.2f}"
        ))
        self._draw_trace()
        self._draw_raster()
        self.window.after(160, self.refresh)

    def _draw_trace(self) -> None:
        canvas = self.dopamine_plot
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        mid = height / 2
        canvas.create_line(8, mid, width - 8, mid, fill="#263943", dash=(2, 4))
        if len(self.dopamine_history) < 2:
            return
        points = []
        for i, value in enumerate(self.dopamine_history):
            x = 8 + i * (width - 16) / max(1, len(self.dopamine_history) - 1)
            y = mid - max(-1.0, min(1.0, value)) * (height * .38)
            points.extend((x, y))
        canvas.create_line(*points, fill=CYAN, width=2, smooth=True)

    def _draw_raster(self) -> None:
        canvas = self.raster
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        rows = max(1, len(self.spike_history))
        neuron_count = len(self.engine.network.population.spikes)
        for row, spikes in enumerate(self.spike_history):
            y = 5 + row * (height - 10) / rows
            active = spikes.nonzero()[0]
            if len(active):
                for index in active:
                    x = 5 + int(index) * (width - 10) / max(1, neuron_count - 1)
                    canvas.create_rectangle(x, y, x + 2, y + 2,
                                            fill=GOLD if index >= self.engine.network.output_start else CYAN,
                                            outline="")
