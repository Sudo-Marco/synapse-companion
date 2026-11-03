from __future__ import annotations

import math
import random
import time
import tkinter as tk


class Avatar(tk.Canvas):
    """Detailed cybernetic eye with expression-specific, low-cost animation."""

    BG = "#05090e"
    CYAN = "#42e4ed"
    GOLD = "#f4bd32"
    MUTED = "#657b83"

    def __init__(self, master: tk.Misc, width: int = 600, height: int = 360) -> None:
        super().__init__(master, width=width, height=height, bg=self.BG,
                         highlightthickness=1, highlightbackground="#19313a")
        self.width, self.height = width, height
        self.cx, self.cy = width / 2, height * .59
        self.rx, self.ry = width * .425, height * .275
        self.iris_radius = self.ry * .79
        self.rng = random.Random(109)
        self.gaze = (0.0, 0.0)
        self.pupil_offset = (0.0, 0.0)
        self.mode = "observando"
        self.energy = .8
        self.happiness = .5
        self.stress = .1
        self.curiosity = .5
        self.boredom = .2
        self.next_blink = time.monotonic() + 2.5
        self.blink_start = 0.0
        self.blink_duration = .2
        self.rotating_ticks: list[tuple[int, float, float, float]] = []
        self.stars: list[tuple[int, float]] = []
        self.lashes: list[tuple[int, float, float, bool]] = []
        self.sparkles: list[int] = []
        self.tears: list[tuple[int, int, int, float]] = []

        self._draw_background()
        self._draw_socket()
        self._draw_iris()
        self._draw_sclera_details()
        self.upper_shadow = self.create_polygon(0, 0, 1, 1,
                                                 fill="#26363a", outline="")
        self.upper_mask = self.create_polygon(0, 0, 1, 1, fill=self.BG, outline="")
        self.lower_mask = self.create_polygon(0, 0, 1, 1, fill=self.BG, outline="")
        self.upper_lid = self.create_line(0, 0, 1, 1, fill=self.CYAN, width=2, smooth=True)
        self.lower_lid = self.create_line(0, 0, 1, 1, fill="#11717d", width=2, smooth=True)
        self._draw_lashes()
        self._draw_expression_fx()
        self._set_lids(1.0, 1.0)

    @staticmethod
    def _flat(points: list[tuple[float, float]]) -> list[float]:
        return [coordinate for point in points for coordinate in point]

    @staticmethod
    def _almond(cx: float, cy: float, rx: float, ry: float,
                steps: int = 64) -> list[tuple[float, float]]:
        upper, lower = [], []
        for i in range(steps + 1):
            u = i / steps
            x = cx - rx + 2 * rx * u
            arc = math.sin(math.pi * u) ** .72
            upper.append((x, cy - ry * arc))
            lower.append((x, cy + ry * arc))
        return upper + list(reversed(lower))

    def _draw_background(self) -> None:
        self.create_rectangle(0, 0, self.width, self.height, fill=self.BG, outline="")
        for x in range(18, self.width, 36):
            self.create_line(x, 0, x, self.height, fill="#091218")
        for y in range(14, self.height, 28):
            self.create_line(0, y, self.width, y, fill="#091218")

        glyphs = ("0", "1", ".", ":", "+", "*", "/", "\\", "[", "]", "<", ">")
        for i in range(118):
            x = self.rng.randint(9, self.width - 9)
            y = self.rng.randint(9, self.height - 9)
            inside_eye = (abs((x - self.cx) / self.rx) < .94
                          and abs((y - self.cy) / self.ry) < .82)
            header_area = 12 < y < 81 and self.width * .22 < x < self.width * .78
            if inside_eye or header_area:
                continue
            item = self.create_text(x, y, text=self.rng.choice(glyphs),
                                    fill=self.rng.choice(("#183944", "#1b4852", "#273941")),
                                    font=("Consolas", self.rng.choice((6, 7, 8))))
            if i % 6 == 0:
                self.stars.append((item, self.rng.random() * math.tau))

        self.system_text = self.create_text(18, 17, anchor="nw", text="> SYSTEM: ONLINE",
                                            fill=self.CYAN, font=("Consolas", 9, "bold"))
        self.create_text(18, 35, anchor="nw", text="> MODE: OBSERVATION",
                         fill="#11717d", font=("Consolas", 8))
        self.state_text = self.create_text(18, 51, anchor="nw", text="> STATE: SERENE",
                                           fill="#11717d", font=("Consolas", 8))
        self.create_text(self.width - 18, 17, anchor="ne",
                         text="[ SYNAPTIC LINK  //  LOCAL ]",
                         fill=self.GOLD, font=("Consolas", 8))
        self.create_text(self.cx, 42, text="O C U L U S   /   N O C T U R N E",
                         fill=self.GOLD, font=("Consolas", 10, "bold"))
        self.create_line(self.cx - 150, 57, self.cx + 150, 57,
                         fill="#66521c", dash=(2, 4))
        self.create_text(self.cx, 73, text="E T E R N A L   W A T C H",
                         fill="#e3eeea", font=("Consolas", 8))
        self.create_line(18, self.height - 29, self.width - 18, self.height - 29,
                         fill="#18303a", dash=(2, 5))
        self.create_text(20, self.height - 13, anchor="sw",
                         text="> THE EYE IS A WINDOW",
                         fill="#e3eeea", font=("Consolas", 8))
        self.activity_text = self.create_text(
            self.width - 20, self.height - 13, anchor="se",
            text="IRIS // LIVE", fill="#11717d", font=("Consolas", 8))

    def _draw_socket(self) -> None:
        outer = self._almond(self.cx, self.cy, self.rx + 9, self.ry + 9)
        eye = self._almond(self.cx, self.cy, self.rx, self.ry)
        inner = self._almond(self.cx, self.cy, self.rx - 7, self.ry - 7)
        self.socket = self.create_polygon(
            *self._flat(outer), fill="#10191f", outline=self.GOLD,
            width=2, smooth=True, splinesteps=24)
        self.sclera = self.create_polygon(
            *self._flat(eye), fill="#91aaa9", outline=self.CYAN,
            width=2, smooth=True, splinesteps=24)
        self.create_polygon(*self._flat(inner), fill="#c4d5cd",
                            outline="#3c6970", width=1, smooth=True, splinesteps=24)
        self.create_text(self.cx, self.cy - self.ry - 13, text="L I M B U S",
                         fill="#9cb4b1", font=("Consolas", 7))
        self.create_text(27, self.cy + self.ry + 17, text="X: 08F   Y: 1A2",
                         anchor="w", fill=self.MUTED, font=("Consolas", 7))
        self.create_text(self.width - 27, self.cy + self.ry + 17,
                         text="OPTIC ARRAY / 01", anchor="e",
                         fill=self.MUTED, font=("Consolas", 7))

    def _draw_iris(self) -> None:
        r = self.iris_radius
        self.outer_iris = self.create_oval(
            self.cx-r, self.cy-r, self.cx+r, self.cy+r,
            fill="#12414a", outline=self.GOLD, width=2, tags="iris")
        self.create_oval(self.cx-r*.91, self.cy-r*.91, self.cx+r*.91, self.cy+r*.91,
                         fill="#0b2730", outline="#11717d", width=2, tags="iris")
        self.create_oval(self.cx-r*.80, self.cy-r*.80, self.cx+r*.80, self.cy+r*.80,
                         fill="#10252c", outline="#49747a", width=1, tags="iris")
        self.create_oval(self.cx-r*.68, self.cy-r*.68, self.cx+r*.68, self.cy+r*.68,
                         outline="#c18f28", width=1, tags="iris")

        # Fine fibers and machine-cut radial ticks.
        for i in range(64):
            angle = math.tau * i / 64
            inner = r * (.72 if i % 4 else .62)
            outer = r * (.96 if i % 4 else 1.05)
            color = "#f4bd32" if i % 8 == 0 else (
                "#52d6dc" if i % 2 == 0 else "#267581")
            item = self.create_line(
                self.cx+math.cos(angle)*inner, self.cy+math.sin(angle)*inner,
                self.cx+math.cos(angle)*outer, self.cy+math.sin(angle)*outer,
                fill=color, width=2 if i % 8 == 0 else 1, tags="iris")
            self.rotating_ticks.append((item, angle, inner, outer))
        for i in range(40):
            angle = math.tau * i / 40 + .05
            start, end = r*.46, r*(.66 if i % 3 == 0 else .57)
            self.create_line(self.cx+math.cos(angle)*start, self.cy+math.sin(angle)*start,
                             self.cx+math.cos(angle)*end, self.cy+math.sin(angle)*end,
                             fill="#c1993b" if i % 5 == 0 else "#237989",
                             width=1, tags="iris")
        for i in range(16):
            self.create_arc(self.cx-r*.86, self.cy-r*.86, self.cx+r*.86, self.cy+r*.86,
                            start=i*22.5+4, extent=11, style=tk.ARC,
                            outline="#69a8a2" if i%4 else self.GOLD,
                            width=2 if i%4 == 0 else 1, tags="iris")

        self.create_oval(self.cx-r*.43, self.cy-r*.43, self.cx+r*.43, self.cy+r*.43,
                         fill="#08151a", outline=self.CYAN, width=2, tags="iris")
        self.pupil = self.create_oval(0, 0, 1, 1, fill="#010407",
                                      outline="#53747a", width=2, tags="pupil")
        self.glint_a = self.create_oval(0, 0, 1, 1, fill="#e3eeea",
                                        outline="", tags="pupil")
        self.glint_b = self.create_oval(0, 0, 1, 1, fill=self.GOLD,
                                        outline="", tags="pupil")
        for angle, label in ((-math.pi/2, "12"), (0, "03"),
                             (math.pi/2, "06"), (math.pi, "09")):
            d = r*1.08
            self.create_text(self.cx+math.cos(angle)*d, self.cy+math.sin(angle)*d,
                             text=label, fill=self.GOLD, font=("Consolas", 6), tags="iris")
        self.scan = self.create_line(self.cx-self.rx*.8, self.cy, self.cx+self.rx*.8,
                                     self.cy, fill="#39bfcb", dash=(2,7), width=1)
        self.scan_glint = self.create_oval(self.cx+20, self.cy-2, self.cx+24,
                                           self.cy+2, fill=self.GOLD, outline="")
        self.tag_raise("iris")
        self.tag_raise("pupil")
        self.tag_raise(self.scan)
        self.tag_raise(self.scan_glint)

    def _draw_sclera_details(self) -> None:
        for side in (-1, 1):
            x = self.cx + side * self.rx * .80
            for i in range(7):
                y = self.cy - 25 + i * 9
                self.create_line(x-8, y, x+8, y-3, fill="#64817f", width=1)
            self.create_arc(x-19, self.cy-29, x+19, self.cy+29,
                            start=70 if side < 0 else 250, extent=110,
                            style=tk.ARC, outline="#d4e3d8", width=2)
            sx = self.cx + side * self.rx * .67
            for i in range(3):
                y = self.cy - 11 + i * 11
                self.create_line(sx, y, sx+side*9, y+3, sx+side*15, y+1,
                                 fill="#587f82", width=1, smooth=True)

    def _draw_lashes(self) -> None:
        for i in range(19):
            u = .10 + .80 * i / 18
            length = 9 + (1-abs(u-.5)*2)*7
            item = self.create_line(0,0,1,1, fill="#91b0aa",
                                    width=2 if i%3==0 else 1, tags="lashes")
            self.lashes.append((item, u, length, True))
        for i in range(9):
            u = .18 + .64 * i / 8
            item = self.create_line(0,0,1,1, fill="#457078", width=1,
                                    tags="lashes")
            self.lashes.append((item, u, 5, False))

    def _draw_expression_fx(self) -> None:
        for _ in range(8):
            self.sparkles.append(self.create_text(
                self.cx, self.cy, text="✦", fill=self.GOLD,
                font=("Segoe UI Symbol", 10), state="hidden", tags="sparkles"))
        for side in (-1, 1):
            drop = self.create_oval(0,0,1,1, fill="#7ce9f2",
                                    outline="#d8ffff", width=1, state="hidden",
                                    tags="tears")
            glint = self.create_oval(0,0,1,1, fill="#eaffff",
                                     outline="", state="hidden", tags="tears")
            self.tears.append((drop, glint, side, self.rng.random()*3))

    def look_at(self, event: tk.Event) -> None:
        self.gaze = (max(-1., min(1., (event.x-self.cx)/self.rx)),
                     max(-1., min(1., (event.y-self.cy)/self.ry)))

    def _set_lids(self, upper_open: float, lower_open: float) -> None:
        n, lid_rx, lid_ry = 64, self.rx+9, self.ry+9
        upper, lower, shadow_inner = [], [], []
        upper_open = max(.025, min(1., upper_open))
        lower_open = max(.025, min(1., lower_open))
        for i in range(n+1):
            u = i/n
            x = self.cx-lid_rx+2*lid_rx*u
            arc = math.sin(math.pi*u)**.72
            y = self.cy-lid_ry*upper_open*arc
            upper.append((x,y))
            lower.append((x,self.cy+lid_ry*lower_open*arc))
            shadow_inner.append((x, y + min(17, self.ry * .18) * arc))

        left, right = self.cx-lid_rx-2, self.cx+lid_rx+2
        top = [(left,self.cy),(left,self.cy-lid_ry-24),
               (right,self.cy-lid_ry-24),(right,self.cy)] + list(reversed(upper))
        bottom = [(left,self.cy),(left,self.cy+lid_ry+24),
                  (right,self.cy+lid_ry+24),(right,self.cy)] + list(reversed(lower))
        shadow = upper + list(reversed(shadow_inner))
        self.coords(self.upper_mask, *self._flat(top))
        self.coords(self.lower_mask, *self._flat(bottom))
        self.coords(self.upper_shadow, *self._flat(shadow))
        self.coords(self.upper_lid, *self._flat(upper))
        self.coords(self.lower_lid, *self._flat(lower))

        lash_color = {"alegre":"#d6ad45", "estressado":"#e78c62",
                      "triste":"#7ab5cb", "sonolento":"#708a9c"}.get(self.mode,"#91b0aa")
        self.itemconfigure("lashes", fill=lash_color)
        for item,u,length,is_upper in self.lashes:
            index = round(u*n)
            x,y = upper[index] if is_upper else lower[index]
            slant = (u-.5)*(13 if is_upper else 8)
            self.coords(item,x,y,x+slant,y-length if is_upper else y+length)

        lid_color = "#ee9465" if self.mode=="estressado" else self.CYAN
        self.itemconfigure(self.upper_lid, fill=lid_color)
        self.itemconfigure(self.lower_lid,
                           fill=lid_color if self.mode=="alegre" else "#11717d")
        self.tag_raise(self.upper_shadow)
        self.tag_raise(self.upper_mask)
        self.tag_raise(self.lower_mask)
        self.tag_raise(self.upper_lid)
        self.tag_raise(self.lower_lid)
        self.tag_raise("lashes")
        self.tag_raise("tears")
        self.tag_raise("sparkles")

    @staticmethod
    def classify(happiness: float, energy: float, stress: float, boredom: float) -> str:
        if stress >= .62:
            return "estressado"
        if happiness >= .72 and stress < .42:
            return "alegre"
        if happiness <= .32 or boredom >= .82:
            return "triste"
        if energy <= .18:
            return "sonolento"
        return "observando"

    def _blink(self, now: float) -> float:
        if self.mode == "alegre":
            phase = now % 4.1
            def pulse(center: float, width: float) -> float:
                return max(0., 1.-abs(phase-center)/width)
            return max(pulse(.10,.11), pulse(.29,.10))
        if self.mode == "estressado":
            phase = now % 1.65
            return max(0.,1.-phase/.105) if phase < .105 else 0.
        if self.mode in {"triste","sonolento"}:
            period = 5.3 if self.mode=="triste" else 3.8
            duration = .48 if self.mode=="triste" else .7
            phase = now % period
            return max(0.,math.sin(math.pi*phase/duration)) if phase < duration else 0.
        if now >= self.next_blink:
            self.next_blink = now + self.rng.uniform(2.8,5.2)
            self.blink_start = now
            self.blink_duration = self.rng.uniform(.16,.22)
        if self.blink_start:
            phase = (now-self.blink_start)/self.blink_duration
            if phase >= 1:
                self.blink_start = 0.
                return 0.
            return max(0.,math.sin(math.pi*phase))
        return 0.

    def draw(self, happiness: float, energy: float, fear: float,
             curiosity: float=.5, boredom: float=0.,
             mode: str | None=None) -> None:
        now = time.monotonic()
        self.happiness=max(0.,min(1.,happiness))
        self.energy=max(0.,min(1.,energy))
        self.stress=max(0.,min(1.,fear))
        self.curiosity=max(0.,min(1.,curiosity))
        self.boredom=max(0.,min(1.,boredom))
        self.mode=mode or self.classify(self.happiness,self.energy,self.stress,self.boredom)

        colors={"alegre":"#f6cf57","estressado":"#f07c58","triste":"#75bad5",
                "sonolento":"#7599bb","observando":self.CYAN}
        accent=colors.get(self.mode,self.CYAN)
        self.itemconfigure(self.socket,outline=accent)
        self.itemconfigure(self.outer_iris,outline=accent)
        self.itemconfigure(self.state_text,text="> STATE: "+self.mode.upper(),fill=accent)
        self.itemconfigure(self.activity_text,
            text="IRIS // ALERT" if self.mode=="estressado" else "IRIS // LIVE",fill=accent)

        blink=self._blink(now)
        if self.mode=="alegre":
            laugh=max(0.,math.sin(now*5.2))
            upper=.92-.20*laugh*self.happiness
            lower=.99-.07*laugh
        elif self.mode=="estressado":
            upper=.85+.06*math.sin(now*23)
            lower=.91+.035*math.sin(now*19+.7)
        elif self.mode=="triste":
            upper,lower=.66,.92
        elif self.mode=="sonolento":
            upper,lower=.60,.82
        else:
            upper=.73+self.energy*.27
            lower=.79+self.energy*.21
        upper*=1.-blink*(.91 if self.mode=="estressado" else .98)
        lower*=1.-blink*(.91 if self.mode=="estressado" else .98)

        tx=self.gaze[0]*12+(self.curiosity-.5)*8
        ty=self.gaze[1]*7+(.5-self.energy)*5
        if self.mode=="triste":
            ty+=13
        if self.mode=="estressado":
            tx+=math.sin(now*37)*2.8
            ty+=math.sin(now*29)*2.2
        ox,oy=self.pupil_offset
        px=ox+(tx-ox)*.22
        py=oy+(ty-oy)*.22
        self.pupil_offset=(px,py)

        pr=self.iris_radius*(.26 if self.mode=="estressado" else
                             .34 if self.mode in {"alegre","triste"} else .30)
        self.coords(self.pupil,self.cx+px-pr,self.cy+py-pr*1.12,
                    self.cx+px+pr,self.cy+py+pr*1.12)
        self.coords(self.glint_a,self.cx+px-pr*.58,self.cy+py-pr*.78,
                    self.cx+px-pr*.18,self.cy+py-pr*.36)
        self.coords(self.glint_b,self.cx+px+pr*.37,self.cy+py+pr*.35,
                    self.cx+px+pr*.55,self.cy+py+pr*.53)

        rotation=now*(.19 if self.mode=="alegre" else .12)
        if self.mode=="estressado":
            rotation+=math.sin(now*17)*.025
        for item,angle,inner,outer in self.rotating_ticks:
            a=angle+rotation
            self.coords(item,self.cx+math.cos(a)*inner,self.cy+math.sin(a)*inner,
                        self.cx+math.cos(a)*outer,self.cy+math.sin(a)*outer)

        scan_offset=math.sin(now*(1.6 if self.mode=="estressado" else .85))*self.ry*.64
        span=self.rx*math.sqrt(max(0.,1.-(scan_offset/self.ry)**2))*.91
        scan_y=self.cy+scan_offset
        if self.mode=="estressado":
            scan_y+=math.sin(now*31)*2
        self.coords(self.scan,self.cx-span,scan_y,self.cx+span,scan_y)
        self.itemconfigure(self.scan,fill=accent)
        gx=self.cx+span*.66
        self.coords(self.scan_glint,gx-2,scan_y-2,gx+2,scan_y+2)

        sparkle_on=self.mode=="alegre" and math.sin(now*7.)>.08
        for i,item in enumerate(self.sparkles):
            a=math.tau*i/len(self.sparkles)+now*.35
            r=self.iris_radius*(1.22+.04*math.sin(now*5+i))
            self.coords(item,self.cx+math.cos(a)*r,self.cy+math.sin(a)*r)
            self.itemconfigure(item,state="normal" if sparkle_on else "hidden")

        for drop,glint,side,phase0 in self.tears:
            phase=(now+phase0)%3.5
            visible=self.mode=="triste" and phase<1.5
            x=self.cx+side*self.iris_radius*1.10
            y=self.cy+15+phase*12
            self.coords(drop,x-3,y-5,x+3,y+7)
            self.coords(glint,x-1,y-3,x+.5,y+1)
            self.itemconfigure(drop,state="normal" if visible else "hidden")
            self.itemconfigure(glint,state="normal" if visible else "hidden")

        for item,phase in self.stars:
            twinkle=math.sin(now*2+phase)>.50
            self.itemconfigure(item,fill=accent if self.mode=="estressado" and
                               math.sin(now*8+phase)>.85 else
                               "#46a8b0" if twinkle else "#1b4650")
        self._set_lids(upper,lower)
