"""Рисунки пояснювальної записки, що малюються (не обчислюються): схема розташування обладнання,
BPMN-діаграми процесу і підпроцесу перевезення, UML-діаграма класів.

Запуск: python diagrams.py <каталог для SVG>; PNG рендериться окремо (headless Chrome, 3×).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

FONT = "Arial"
INK = "#000000"
INK_2 = "#333333"
GRAY = "#808080"
FILL = "#ffffff"
SOFT = "#f2f2f2"


class Svg:
    def __init__(self, w: int, h: int, title: str):
        self.w, self.h, self.title = w, h, title
        self.els: list[str] = []

    def add(self, s: str) -> None:
        self.els.append(s)

    # --- примітиви
    def line(self, x1, y1, x2, y2, width=1.4, dash=None, color=INK):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                 f'stroke-width="{width}"{d} fill="none"/>')

    def poly(self, pts, width=1.4, dash=None, color=INK):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polyline points="{p}" stroke="{color}" stroke-width="{width}"{d} fill="none" '
                 f'stroke-linejoin="round"/>')

    def rect(self, x, y, w, h, rx=0, width=1.4, fill=FILL, dash=None, color=INK):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" '
                 f'stroke="{color}" stroke-width="{width}"{d}/>')

    def circle(self, cx, cy, r, width=1.4, fill=FILL, color=INK):
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}" stroke="{color}" stroke-width="{width}"/>')

    def polygon(self, pts, fill=INK, width=0, color=INK):
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polygon points="{p}" fill="{fill}" stroke="{color}" stroke-width="{width}"/>')

    def text(self, x, y, s, size=16, anchor="middle", weight="normal", style="normal", color=INK, lh=1.25):
        """Багаторядковий текст: рядки розділяються \\n; y – базова лінія першого рядка."""
        lines = s.split("\n")
        out = [f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" text-anchor="{anchor}" '
               f'font-weight="{weight}" font-style="{style}" fill="{color}" xml:space="preserve">']
        for k, ln in enumerate(lines):
            dy = 0 if k == 0 else size * lh
            out.append(f'<tspan x="{x:.1f}" dy="{dy:.1f}">{escape(ln)}</tspan>')
        out.append("</text>")
        self.add("".join(out))

    def ctext(self, cx, cy, s, size=16, **kw):
        """Текст, центрований по вертикалі навколо cy."""
        n = s.count("\n") + 1
        lh = kw.pop("lh", 1.25)
        y0 = cy - (n - 1) * size * lh / 2 + size * 0.35
        self.text(cx, y0, s, size=size, lh=lh, **kw)

    def head(self, x, y, angle_deg, size=11, filled=True):
        a = math.radians(angle_deg)
        bx, by = x - size * math.cos(a), y - size * math.sin(a)
        nx, ny = -math.sin(a) * size * 0.42, math.cos(a) * size * 0.42
        pts = [(x, y), (bx + nx, by + ny), (bx - nx, by - ny)]
        if filled:
            self.polygon(pts)
        else:
            self.add('<polygon points="{}" fill="#ffffff" stroke="#000" stroke-width="1.3"/>'.format(
                " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)))

    def arrow(self, pts, width=1.4, dash=None, head=11, filled=True):
        """Ламана зі стрілкою в кінці (останній відрізок визначає напрям)."""
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        trim = head * 0.9
        ex, ey = x2 - trim * math.cos(math.radians(ang)), y2 - trim * math.sin(math.radians(ang))
        self.poly(pts[:-1] + [(ex, ey)], width=width, dash=dash)
        self.head(x2, y2, ang, size=head, filled=filled)

    def save(self, path: Path) -> None:
        body = "".join(self.els)
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}"><title>{escape(self.title)}</title>'
            f'<rect width="{self.w}" height="{self.h}" fill="#fff"/>{body}</svg>\n', encoding="utf-8")


# =========================================================================== рис. 1.1
def layout(out: Path) -> Path:
    """Схема розташування обладнання ГВС і закріплення роботів для двох варіантів."""
    W, H = 1000, 600
    s = Svg(W, H, "Схема розташування обладнання ГВС")
    k = 40.0
    X = {"A": 140.0, "M1": 140 + 6 * k, "M2": 140 + 13 * k, "W": 140 + 18 * k}
    rows = (175.0, 465.0)

    def stations(y):
        s.line(X["A"], y, X["W"], y, width=3, color=GRAY)  # трек переміщення роботів
        # пункт прибуття: площадка (черга)
        s.rect(X["A"] - 46, y - 92, 92, 52, fill=FILL)
        for i in range(7):
            xl = X["A"] - 30 + i * 9
            s.line(xl, y - 86, xl, y - 46, width=1.2)
        s.ctext(X["A"], y - 112, "A – пункт прибуття", size=16)
        s.text(X["A"] - 52, y - 58, "площадка", size=14, anchor="end", color=INK_2)
        for name, label in (("M1", "M1 – верстат 1"), ("M2", "M2 – верстат 2")):
            x = X[name]
            s.rect(x - 58, y - 92, 116, 52, rx=4)
            for j in range(3):
                s.rect(x - 46 + j * 32, y - 82, 26, 32, fill=SOFT, width=1.1)
            s.ctext(x, y - 112, label, size=16)
            s.text(x + 64, y - 58, "3 місця", size=14, anchor="start", color=INK_2)
        s.rect(X["W"] - 46, y - 92, 92, 52, rx=4, fill=SOFT)
        s.ctext(X["W"], y - 66, "W", size=18, weight="bold")
        s.ctext(X["W"], y - 112, "W – склад", size=16)
        for name in X:
            s.line(X[name], y - 40, X[name], y, width=1.4)  # точки завантаження/вивантаження на треку
            s.circle(X[name], y, 4, fill=INK)

    def robot(x, y, name):
        s.circle(x, y, 17, width=1.6)
        s.ctext(x, y, name, size=14, weight="bold")

    # --- а) варіант 1
    y = rows[0]
    s.text(20, 32, "а) варіант 1: кожен робот закріплений за своїм шляхом переміщення", size=17, anchor="start",
           weight="bold")
    stations(y)
    for (a, b), d, name in ((("A", "M1"), 6, "R1"), (("M1", "M2"), 7, "R2"), (("M2", "W"), 5, "R3")):
        xa, xb = X[a], X[b]
        robot((xa + xb) / 2, y, name)
        s.arrow([(xa + 8, y + 32), (xb - 8, y + 32)])  # з деталлю
        s.arrow([(xb - 8, y + 52), (xa + 8, y + 52)], dash="6 4")  # порожнім назад
        s.ctext((xa + xb) / 2, y + 76, f"{name}: {a} ⇄ {b}, {d} с", size=15)
    s.arrow([(X["A"], y + 104), (X["A"] + 40, y + 104)])
    s.text(X["A"] + 48, y + 109, "переміщення з деталлю;", size=14, anchor="start", color=INK_2)
    s.arrow([(X["A"] + 250, y + 104), (X["A"] + 290, y + 104)], dash="6 4")
    s.text(X["A"] + 298, y + 109, "повернення порожнім (той самий час переміщення)", size=14, anchor="start",
           color=INK_2)
    # --- б) варіант 2
    y = rows[1]
    s.text(20, 326, "б) варіант 2: будь-який робот на будь-якому шляху, призначається найближчий вільний",
           size=17, anchor="start", weight="bold")
    stations(y)
    for name, pos in (("R1", "M1"), ("R2", "M2"), ("R3", "W")):
        robot(X[pos], y, name)
    # приклад: деталь надійшла на A, відстані до вільних роботів
    for (name, pos, d), dy in ((("R1", "M1", 6), 36), (("R2", "M2", 13), 62), (("R3", "W", 18), 88)):
        s.arrow([(X[pos], y + 17), (X[pos], y + dy), (X["A"] + 6, y + dy)],
                dash="2 4" if name != "R1" else None, width=1.6 if name == "R1" else 1.2)
        s.text(X[pos] + 8, y + dy - 5, f"{d} с", size=14, anchor="start", color=INK_2)
    s.text(X["A"], y + 118, "приклад: деталь надійшла на A, вільні роботи стоять у M1, M2, W; призначається R1 "
           "– найменший холостий хід (6 с)", size=14, anchor="start", color=INK_2)
    svg = out / "fig_1_1_layout.svg"
    s.save(svg)
    return svg


# =========================================================================== BPMN
def bpmn_task(s: Svg, cx, cy, w, h, label, sub=False, size=16):
    s.rect(cx - w / 2, cy - h / 2, w, h, rx=10, width=1.6)
    s.ctext(cx, cy - (6 if sub else 0), label, size=size)
    if sub:  # маркер згорнутого підпроцесу [+]
        s.rect(cx - 8, cy + h / 2 - 18, 16, 16, width=1.2)
        s.line(cx - 5, cy + h / 2 - 10, cx + 5, cy + h / 2 - 10, width=1.2)
        s.line(cx, cy + h / 2 - 15, cx, cy + h / 2 - 5, width=1.2)


def bpmn_event(s: Svg, cx, cy, kind="start", r=20):
    if kind == "start":
        s.circle(cx, cy, r, width=1.6)
    elif kind == "end":
        s.circle(cx, cy, r, width=4.0)
    else:  # проміжна умовна подія очікування: подвійне коло + значок умови
        s.circle(cx, cy, r, width=1.4)
        s.circle(cx, cy, r - 4, width=1.4)
        s.rect(cx - 7, cy - 9, 14, 18, width=1.1)
        for dy in (-4, 0, 4):
            s.line(cx - 4, cy + dy, cx + 4, cy + dy, width=1.0)


def bpmn_gateway(s: Svg, cx, cy, r=26):
    s.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=FILL, width=1.6)
    d = r * 0.38
    s.line(cx - d, cy - d, cx + d, cy + d, width=2.4)
    s.line(cx - d, cy + d, cx + d, cy - d, width=2.4)


def bpmn_main(out: Path) -> Path:
    """Процес проходження деталі через ГВС (смуги-доріжки вертикальні)."""
    lanes = [("Площадка A", 170), ("Роботи R1–R3", 230), ("Верстат M1\n(3 місця)", 200),
             ("Верстат M2\n(3 місця)", 200), ("Склад W", 160)]
    head_h, top = 64, 40
    W = 40 + sum(w for _, w in lanes) + 10
    rows = [top + head_h + 56 + 86 * k for k in range(10)]
    H = rows[-1] + 140
    s = Svg(W, H, "BPMN-діаграма процесу проходження деталі")
    # пул і доріжки
    x0 = 40
    hp = H - top - 70
    s.rect(x0 - 30, top, W - x0 + 20, hp, width=1.6)
    s.add(f'<text x="{x0 - 15}" y="{top + hp / 2}" font-family="{FONT}" font-size="16" text-anchor="middle" '
          f'transform="rotate(-90 {x0 - 15} {top + hp / 2})">ГВС: проходження деталі</text>')
    cx = {}
    x = x0
    for name, w in lanes:
        s.rect(x, top, w, hp, width=1.2)
        s.rect(x, top, w, head_h, width=1.2, fill=SOFT)
        s.ctext(x + w / 2, top + head_h / 2, name, size=16, weight="bold")
        cx[name.split("\n")[0]] = x + w / 2
        x += w
    A, R, M1, M2, WH = (cx["Площадка A"], cx["Роботи R1–R3"], cx["Верстат M1"], cx["Верстат M2"], cx["Склад W"])
    A -= 38  # події площадки ліворуч, підписи праворуч від них
    tw, th = 178, 66
    # вузли
    bpmn_event(s, A, rows[0], "start")
    s.text(A + 26, rows[0] - 12, "надійшла\nдеталь,\nτ = exp(40) с", size=13, anchor="start", color=INK_2, lh=1.2)
    bpmn_event(s, A, rows[1], "catch")
    s.text(A, rows[1] + 40, "робота\nпризначено", size=14, color=INK_2)
    bpmn_task(s, R, rows[2], tw, th, "Перевезення\nA → M1", sub=True)
    bpmn_task(s, M1, rows[3], 170, th, "Обробка\nnorm(60, 10) с")
    bpmn_event(s, M1, rows[4], "catch")
    s.text(M1, rows[4] + 40, "робота\nпризначено", size=14, color=INK_2)
    bpmn_task(s, R, rows[5], tw, th, "Перевезення\nM1 → M2", sub=True)
    bpmn_task(s, M2, rows[6], 170, th, "Обробка\nexp(100) с")
    bpmn_event(s, M2, rows[7], "catch")
    s.text(M2, rows[7] + 40, "робота\nпризначено", size=14, color=INK_2)
    bpmn_task(s, R, rows[8], tw, th, "Перевезення\nM2 → W", sub=True)
    bpmn_event(s, WH, rows[9], "end")
    s.text(WH, rows[9] + 42, "деталь\nна складі", size=14, color=INK_2)
    # потоки (ортогональні): з події – вбік, із задачі – праворуч і вниз
    s.arrow([(A, rows[0] + 20), (A, rows[1] - 20)])
    s.arrow([(A + 20, rows[1]), (R, rows[1]), (R, rows[2] - th / 2)])
    s.arrow([(R + tw / 2, rows[2]), (M1, rows[2]), (M1, rows[3] - th / 2)])
    s.arrow([(M1, rows[3] + th / 2), (M1, rows[4] - 20)])
    s.arrow([(M1 - 20, rows[4]), (R, rows[4]), (R, rows[5] - th / 2)])
    s.arrow([(R + tw / 2, rows[5]), (M2, rows[5]), (M2, rows[6] - th / 2)])
    s.arrow([(M2, rows[6] + th / 2), (M2, rows[7] - 20)])
    s.arrow([(M2 - 20, rows[7]), (R, rows[7]), (R, rows[8] - th / 2)])
    s.arrow([(R + tw / 2, rows[8]), (WH, rows[8]), (WH, rows[9] - 20)])
    # легенда під пулом
    yl = H - 6
    s.text(x0 - 30, yl - 30, "◎ – проміжна подія очікування: деталь чекає на робота, займаючи місце на площадці A "
           "або на верстаті;", size=14, anchor="start", color=INK_2)
    s.text(x0 - 30, yl - 8, "[+] – підпроцес перевезення (рис. 1.3); робота призначає правило варіанта 1 "
           "(закріплений робот) або варіанта 2 (найближчий вільний).", size=14, anchor="start", color=INK_2)
    svg = out / "fig_1_2_bpmn_main.svg"
    s.save(svg)
    return svg


def bpmn_transport(out: Path) -> Path:
    """Розгорнутий підпроцес «Перевезення деталі шляхом S» (перший ряд – праворуч, другий – ліворуч)."""
    W, H = 1000, 615
    s = Svg(W, H, "BPMN-діаграма підпроцесу перевезення деталі роботом")
    s.rect(10, 10, W - 20, H - 20, rx=16, width=1.8)
    s.text(30, 40, "Перевезення деталі шляхом S (S = 1: A → M1; 2: M1 → M2; 3: M2 → W) роботом r", size=17,
           anchor="start", weight="bold")
    y1, y2 = 150, 330
    tw, th = 170, 86
    # перший ряд: холостий хід (лише якщо робот не в точці завантаження), захоплення, переміщення
    bpmn_event(s, 60, y1, "start")
    s.text(60, y1 + 42, "робота r\nпризначено", size=13, color=INK_2)
    bpmn_gateway(s, 165, y1)
    s.text(165, y1 + 48, "робот у\nточці src_S?", size=13, color=INK_2)
    bpmn_task(s, 330, y1, tw, th, "Холостий хід\nдо src_S\nd(pos_r, src_S)", size=15)
    bpmn_gateway(s, 490, y1)
    bpmn_task(s, 640, y1, tw, th, "Захоплення\nдеталі\nunif(8, 1) с", size=15)
    bpmn_task(s, 840, y1, tw, th, "Переміщення\nз деталлю\nd_S = 6; 7; 5 с", size=15)
    s.arrow([(80, y1), (139, y1)])
    s.arrow([(191, y1), (330 - tw / 2, y1)])
    s.text(200, y1 - 8, "ні", size=14, anchor="start")
    s.arrow([(165, y1 - 26), (165, y1 - 70), (490, y1 - 70), (490, y1 - 26)])
    s.text(173, y1 - 46, "так", size=14, anchor="start")
    s.arrow([(330 + tw / 2, y1), (464, y1)])
    s.arrow([(516, y1), (640 - tw / 2, y1)])
    s.arrow([(640 + tw / 2, y1), (840 - tw / 2, y1)])
    # другий ряд: очікування місця, вивільнення, повернення (варіант 1)
    s.arrow([(840, y1 + th / 2), (840, y2 - 26)])
    bpmn_gateway(s, 840, y2)
    s.text(876, y2 - 30, "на dst_S є\nвільне місце?", size=14, anchor="start")
    bpmn_task(s, 640, y2, tw, th, "Вивільнення\nдеталі\nunif(8, 1) с", size=15)
    s.arrow([(814, y2), (640 + tw / 2, y2)])
    s.text(800, y2 - 8, "так", size=14, anchor="end")
    yc = y2 + 120
    bpmn_event(s, 840, yc, "catch")
    s.arrow([(840, y2 + 26), (840, yc - 20)])
    s.text(848, y2 + 52, "ні", size=14, anchor="start")
    s.text(866, yc + 5, "місце\nзвільнилося", size=13, anchor="start", color=INK_2)
    s.arrow([(820, yc), (640, yc), (640, y2 + th / 2)])
    bpmn_gateway(s, 470, y2)
    s.text(470, y2 - 34, "варіант", size=14, color=INK_2)
    s.arrow([(640 - tw / 2, y2), (496, y2)])
    bpmn_task(s, 300, y2, tw, th, "Повернення\nдо src_S\nd_S с", size=15)
    s.arrow([(444, y2), (300 + tw / 2, y2)])
    s.text(436, y2 - 8, "1", size=14, anchor="end")
    bpmn_event(s, 120, y2, "end")
    s.arrow([(300 - tw / 2, y2), (140, y2)])
    s.text(120, y2 + 44, "робот вільний\nу точці src_S", size=13, color=INK_2)
    bpmn_event(s, 300, yc, "end")
    s.arrow([(470, y2 + 26), (470, yc), (320, yc)])
    s.text(478, y2 + 52, "2", size=14, anchor="start")
    s.text(300, yc + 44, "робот вільний\nу точці dst_S", size=13, color=INK_2)
    # примітки
    s.text(30, H - 52, "Варіант 1: робот закріплений за шляхом S і повертається до src_S одразу після вивільнення, тому "
           "холостого ходу перед захопленням немає.", size=14, anchor="start", color=INK_2)
    s.text(30, H - 30, "Варіант 2: призначається найближчий вільний робот. Місце-джерело звільняється в кінці "
           "захоплення; поки місця немає, робот тримає деталь.", size=14, anchor="start", color=INK_2)
    svg = out / "fig_1_3_bpmn_transport.svg"
    s.save(svg)
    return svg


# =========================================================================== UML
def uml_class(s: Svg, x, y, w, name, attrs, ops, stereotype=None, size=14, italic=False):
    """Клас UML: ім'я, атрибути, операції. Повертає (x, y, w, h)."""
    lh = size * 1.32
    head = (2 if stereotype else 1) * lh + 10
    h_attr = max(1, len(attrs)) * lh + 8
    h_ops = max(1, len(ops)) * lh + 8 if ops else 14
    h = head + h_attr + h_ops
    s.rect(x, y, w, h, width=1.4)
    yy = y + lh
    if stereotype:
        s.text(x + w / 2, yy, f"«{stereotype}»", size=size - 1, color=INK_2)
        yy += lh
    s.text(x + w / 2, yy, name, size=size + 1, weight="bold", style="italic" if italic else "normal")
    s.line(x, y + head, x + w, y + head, width=1.2)
    for k, a in enumerate(attrs):
        s.text(x + 8, y + head + 4 + lh * (k + 0.78), a, size=size, anchor="start")
    s.line(x, y + head + h_attr, x + w, y + head + h_attr, width=1.2)
    for k, o in enumerate(ops):
        s.text(x + 8, y + head + h_attr + 4 + lh * (k + 0.78), o, size=size, anchor="start")
    return (x, y, w, h)


def diamond(s: Svg, x, y, ang, filled=True, size=14):
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    pts = [(x, y), (x + ux * size / 2 + nx * size / 3.2, y + uy * size / 2 + ny * size / 3.2),
           (x + ux * size, y + uy * size), (x + ux * size / 2 - nx * size / 3.2, y + uy * size / 2 - ny * size / 3.2)]
    s.add('<polygon points="{}" fill="{}" stroke="#000" stroke-width="1.3"/>'.format(
        " ".join(f"{px:.1f},{py:.1f}" for px, py in pts), "#000" if filled else "#fff"))


def uml(out: Path) -> Path:
    """UML-діаграма класів: ширина 1030 px, шрифт 15 px (≈ 7 пт при ширині рисунка 17 см)."""
    W, H = 1030, 1090
    fs = 15
    s = Svg(W, H, "UML-діаграма класів імітаційної моделі")
    B = {}
    B["Params"] = uml_class(s, 10, 10, 290, "Params", [
        "+ arrival, handling: Dist", "+ m1_time, m2_time: Dist", "+ m1_capacity, m2_capacity: int",
        "+ n_robots: int", "+ strategy: str"],
        ["+ distance(a, b): float", "+ robot_routes(): list"], stereotype="dataclass", size=fs)
    B["Model"] = uml_class(s, 340, 10, 350, "Model", [
        "+ params: Params", "+ tcurr: float", "+ calendar: list", "+ A, M1, M2, W: QS", "+ T: dict[int, QS]",
        "+ routes: list[Route]", "+ robots: list[Robot]"],
        ["+ run(t_end, t_warmup)", "+ transition(t)", "+ update_blockings(t)", "+ B0() … B4(): bool",
         "+ control(t): bool", "+ results(): dict"], size=fs)
    B["RandomStreams"] = uml_class(s, 730, 10, 290, "RandomStreams", [
        "+ arrivals, m1, m2: Stream", "+ handling, ties: Stream"], [], size=fs)
    B["Stream"] = uml_class(s, 730, 170, 290, "Stream", ["- _rnd: random.Random"], [
        "+ zeta(): float", "+ exponential(mean)", "+ uniform(d, s)", "+ normal(d, s)", "+ choice(items)"], size=fs)
    B["Dist"] = uml_class(s, 10, 300, 290, "Dist", ["+ kind: str", "+ a, b: float"],
                          ["+ sample(stream): float"], stereotype="dataclass", size=fs)
    yr = 500
    B["QS"] = uml_class(s, 10, yr, 245, "QS", ["+ name: str", "+ channels: list[Channel]",
                                              "+ service, release", "+ route: Route", "+ n: list[int]"],
                        ["+ accept(req, t, h, ch)", "+ end_of_service(ch, t)", "+ vacate(ch, t, h)",
                         "+ update_stats(t1, t2)"], size=fs)
    B["Route"] = uml_class(s, 315, yr, 270, "Route", ["+ src, dst", "+ blocked(): bool  – B(S, t)",
                                                     "+ waiting: deque[Channel]"],
                           ["+ transfer(ch, t)", "+ unblock(t): bool"], size=fs)
    B["Create"] = uml_class(s, 625, yr, 180, "Create", ["+ tnext: float", "+ route: Route"], ["+ arrival(t)"],
                            size=fs)
    B["Exit"] = uml_class(s, 845, yr, 175, "Exit", [], ["+ accept(part, t)"], size=fs)
    yb = 840
    B["Channel"] = uml_class(s, 10, yb, 250, "Channel", ["+ K: int  – 0, 1, 2", "+ tnext: float",
                                                         "+ request: Part | Robot"], [], size=fs)
    B["Part"] = uml_class(s, 545, yb, 230, "Part", ["+ id: int", "+ t_arrival: float", "+ t_ready, t_grab: dict",
                                                   "+ t_done: float"], [], stereotype="dataclass", size=fs)
    B["Robot"] = uml_class(s, 805, yb, 215, "Robot", ["+ id: int", "+ pos: str", "+ target: str"], [],
                           stereotype="dataclass", size=fs)

    def label(x, y, t, anchor="start"):
        s.text(x, y, t, size=14, anchor=anchor, color=INK_2)

    mx, my, mw, mh = B["Model"]
    px, py, pw, ph = B["Params"]
    rx, ry, rw, rh = B["RandomStreams"]
    sx, sy, sw, sh = B["Stream"]
    dx, dy, dw, dh = B["Dist"]
    # Model -> Params, Model ◆— RandomStreams ◆— Stream, Params -> Dist
    s.arrow([(mx, my + 44), (px + pw, my + 44)], width=1.3, head=11)
    s.line(mx + mw + 13, my + 44, rx, my + 44, width=1.3)
    diamond(s, mx + mw, my + 44, 0)
    s.line(rx + rw / 2, ry + rh + 13, rx + rw / 2, sy, width=1.3)
    diamond(s, rx + rw / 2, ry + rh, 90)
    label(rx + rw / 2 + 8, sy - 8, "5")
    s.arrow([(px + pw / 2, py + ph), (px + pw / 2, dy)], width=1.3)
    label(px + pw / 2 + 8, dy - 8, "4")
    # Model ◆— Create, QS, Route, Exit: модель складається з елементів мережі МО
    bus = yr - 34
    xs_sub = [B[n][0] + B[n][2] / 2 for n in ("Create", "QS", "Route", "Exit")]
    s.line(min(xs_sub), bus, max(xs_sub), bus, width=1.3)
    for xk in xs_sub:
        s.line(xk, bus, xk, yr, width=1.3)
    xm = mx + mw / 2
    s.line(xm, my + mh + 13, xm, bus, width=1.3)
    diamond(s, xm, my + mh, 90)
    label(B["QS"][0] + B["QS"][2] / 2 + 8, yr - 8, "1..*")
    label(B["Route"][0] + B["Route"][2] / 2 + 8, yr - 8, "1..*")
    # QS ◆— Channel
    qx, qy, qw, qh = B["QS"]
    cx_, cy_, cw_, ch_ = B["Channel"]
    s.line(cx_ + cw_ / 2, qy + qh + 13, cx_ + cw_ / 2, cy_, width=1.3)
    diamond(s, cx_ + cw_ / 2, qy + qh, 90)
    label(cx_ + cw_ / 2 + 8, cy_ - 8, "1..*")
    # Route -> QS (src, dst)
    ox, oy, ow, oh = B["Route"]
    s.arrow([(ox, oy + 60), (qx + qw, oy + 60)], width=1.3)
    label(ox - 6, oy + 52, "src, dst", anchor="end")
    # Channel -> Part, Robot (запит у пристрої)
    ax_, ay_, aw_, ah_ = B["Part"]
    bx_, by_, bw_, bh_ = B["Robot"]
    s.arrow([(cx_ + cw_, cy_ + 70), (ax_, cy_ + 70)], width=1.3)
    label((cx_ + cw_ + ax_) / 2, cy_ + 62, "0..1", anchor="middle")
    s.arrow([(cx_ + cw_ / 2, cy_ + ch_), (cx_ + cw_ / 2, H - 22), (bx_ + bw_ / 2, H - 22),
             (bx_ + bw_ / 2, by_ + bh_)], width=1.3)
    label(bx_ + bw_ / 2 + 8, by_ + bh_ + 18, "0..1")
    # Create -> Route
    cr_x, cr_y, cr_w, cr_h = B["Create"]
    s.arrow([(cr_x, cr_y + 60), (ox + ow, cr_y + 60)], width=1.3)
    svg = out / "fig_3_1_uml.svg"
    s.save(svg)
    return svg


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for f in (layout, bpmn_main, bpmn_transport, uml):
        p = f(out)
        print(p)
