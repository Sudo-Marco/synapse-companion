from __future__ import annotations

import tkinter as tk


class Bubble(tk.Toplevel):
    """Small dark speech card with a terminal-style accent."""

    def __init__(self, master: tk.Misc, text: str) -> None:
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#070b10")
        card = tk.Frame(self, bg="#101a22", highlightthickness=1,
                        highlightbackground="#31d7e4")
        card.pack(padx=1, pady=1)
        tk.Label(card, text="◉  OCULUS", bg="#101a22", fg="#e9b725",
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(card, text=text, bg="#101a22", fg="#d8e4e7", padx=12, pady=8,
                 wraplength=260, justify="left", font=("Segoe UI", 9)).pack(anchor="w")
        self.after(4500, self.destroy)
