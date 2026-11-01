"""Генерує SVG-схему мережі МО для варіанта 2 (будь-який робот на будь-якому шляху, найближчий вільний).

Фрагмент деталей: A -> T1 -> M1 -> T2 -> M2 -> T3 -> W; T1–T3 – СМО перевезення, пристрій r – робот r.
Фрагмент руху роботів: П <-> Х (запити – роботи). К – керування роботами (правило (2.4)).
"""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(sys.argv[1])
FONT = "Times New Roman"
R = 24
DY = 64
TRI_W, TRI_H = 22, 26
Y1, Y2, Y3 = 170, 510, 860
Y_MID = 360

els: list[str] = []


def add(s: str) -> None:
    els.append(s)


def seg(x1, y1, x2, y2, dashed=False):
    st = 'stroke="#000" stroke-width="1.2" stroke-dasharray="5 4"' if dashed else 'stroke="#000" stroke-width="1.4"'
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {st} fill="none"/>')


def head(x, y, direction):
    L, Wd = 10, 4
    if direction == "r":
        pts = f"{x},{y} {x - L},{y - Wd} {x - L},{y + Wd}"
    elif direction == "u":
        pts = f"{x},{y} {x - Wd},{y + L} {x + Wd},{y + L}"
    else:
        pts = f"{x},{y} {x - Wd},{y - L} {x + Wd},{y - L}"
    add(f'<polygon points="{pts}" fill="#000"/>')


def arrow(x1, x2, y):
    seg(x1, y, x2 - 6, y)
    head(x2, y, "r")


def rich(x, y, runs, size=16, anchor="middle", fill="#000"):
    out = [f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
           f'text-anchor="{anchor}" fill="{fill}" xml:space="preserve">']
    shifted = False
    for text, kind in runs:
        a = []
        if kind in ("i", "si"):
            a.append('font-style="italic"')
        if kind in ("s", "si"):
            if not shifted:
                a.append(f'dy="{size * 0.3:.1f}"')
                shifted = True
            a.append(f'font-size="{size * 0.72:.1f}"')
        elif shifted:
            a.append(f'dy="{-size * 0.3:.1f}"')
            shifted = False
        out.append(f'<tspan {" ".join(a)}>{escape(text)}</tspan>')
    out.append("</text>")
    add("".join(out))


def caption(x, y, text, size=14, anchor="middle"):
    rich(x, y, [(text, "n")], size=size, anchor=anchor, fill="#333")


def device(cx, cy, runs):
    add(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#fff" stroke="#000" stroke-width="1.4"/>')
    rich(cx, cy + 6, runs, size=16)


def blocking(x, y):
    add(f'<polygon points="{x},{y - TRI_H / 2} {x},{y + TRI_H / 2} {x + TRI_W},{y}" '
        f'fill="#808080" stroke="#000" stroke-width="1.2"/>')


def control(x_from, y_from, x_tri, y_tri, y_top, label_runs):
    xt = x_tri + 4
    tip = y_tri - TRI_H / 2 + 3
    seg(x_from, y_from, x_from, y_top, dashed=True)
    seg(x_from, y_top, xt, y_top, dashed=True)
    seg(xt, y_top, xt, tip - 9, dashed=True)
    head(xt, tip, "d")
    rich((xt + x_from) / 2, y_top - 7, label_runs, size=16)


def ctl(x_tri, y, label_runs):
    """Блокування, умову якого задає керування роботами К: квадрат «К» над трикутником."""
    xt = x_tri + 4
    tip = y - TRI_H / 2 + 3
    add(f'<rect x="{xt - 13}" y="{y - 92}" width="26" height="26" fill="#fff" stroke="#000" '
        f'stroke-width="1.2" stroke-dasharray="4 3"/>')
    rich(xt, y - 73, [("К", "n")], size=15)
    seg(xt, y - 66, xt, tip - 9, dashed=True)
    head(xt, tip, "d")
    rich(xt, y - 100, label_runs, size=15)


def multi(x_in, cx, x_out, y, names, unlimited=False):
    ys = [y - DY, y, y + DY]
    seg(x_in, ys[0], x_in, ys[-1])
    seg(x_out, ys[0], x_out, ys[-1])
    for k, yk in enumerate(ys):
        if unlimited and k == 1:
            for dy in (-12, 0, 12):
                add(f'<circle cx="{cx}" cy="{yk + dy}" r="2.2" fill="#000"/>')
            continue
        seg(x_in, yk, cx - R, yk)
        seg(cx + R, yk, x_out, yk)
        device(cx, yk, names[k])


def labels(cx, y_top, lines):
    yy = y_top
    for runs, size, gray in lines:
        rich(cx, yy, runs, size=size, fill="#333" if gray else "#000")
        yy += 19


def B(k):
    return [("B", "i"), (str(k), "s"), ("(", "n"), ("S", "i"), (", ", "n"), ("t", "i"), (")", "n")]


def t_eq(*runs):
    return [("t", "i"), (" = ", "n"), *runs]


def tzv_eq(*runs):
    return [("t", "i"), ("зв", "s"), (" = ", "n"), *runs]


TZX = [("t", "i"), ("зх", "s")]
TVYV = [("t", "i"), ("вив", "s")]
ROBOTS = [[("R1", "n")], [("R2", "n")], [("R3", "n")]]


def inf_names(name):
    return [[(name, "n"), ("1", "s")], None, [(name, "n"), ("∞", "s")]]


def m_names(k):
    return [[(f"M{k}", "n"), (str(j), "s")] for j in (1, 2, 3)]


def transport(x_in, cx, x_out, y, S, d, path):
    multi(x_in, cx, x_out, y, ROBOTS)
    labels(cx, y + DY + R + 22, [(t_eq(*TZX, (f" + {d}", "n")), 16, False),
                                 (tzv_eq(*TVYV), 16, False),
                                 ([(f"T{S}: {path}, ", "n"), ("m", "i"), (" = 3", "n")], 14, True)])


def machine(x_in, cx, x_out, y, k, law):
    multi(x_in, cx, x_out, y, m_names(k))
    labels(cx, y + DY + R + 22, [(t_eq(*TVYV, (f" + {law}", "n")), 16, False),
                                 (tzv_eq(*TZX), 16, False),
                                 ([(f"верстат {k}, ", "n"), ("m", "i"), (" = 3", "n")], 14, True)])


# ------------------------------------------------------------------ фрагмент деталей, перший ряд
caption(10, 26, "Фрагмент деталей", size=16, anchor="start")
arrow(8, 108, Y1)
caption(58, Y1 - 10, "деталі")
rich(58, Y1 + 22, [("t", "i"), (" = exp(40)", "n")])
multi(108, 158, 208, Y1, inf_names("A"), unlimited=True)
labels(158, Y1 + DY + R + 22, [(t_eq(("0, ", "n"), ("t", "i"), ("зв", "s"), (" = ", "n"), *TZX), 16, False),
                               ([("площадка A, ", "n"), ("m", "i"), (" = ∞", "n")], 14, True)])
seg(208, Y1, 238, Y1)
blocking(238, Y1)
ctl(238, Y1, B(0))
arrow(238 + TRI_W, 300, Y1)
transport(300, 350, 400, Y1, 1, 6, "A → M1")
seg(400, Y1, 430, Y1)
blocking(430, Y1)
arrow(430 + TRI_W, 490, Y1)
machine(490, 540, 590, Y1, 1, "norm(60, 10)")
control(540, Y1 - DY - R, 430, Y1, Y1 - DY - R - 24, B(1))
seg(590, Y1, 620, Y1)
blocking(620, Y1)
ctl(620, Y1, B(2))
arrow(620 + TRI_W, 680, Y1)
transport(680, 730, 780, Y1, 2, 7, "M1 → M2")

# перехід до другого ряду
seg(780, Y1, 820, Y1)
seg(820, Y1, 820, Y_MID)
seg(820, Y_MID, 40, Y_MID)
seg(40, Y_MID, 40, Y2)
seg(40, Y2, 70, Y2)

# ------------------------------------------------------------------ фрагмент деталей, другий ряд
blocking(70, Y2)
arrow(70 + TRI_W, 140, Y2)
machine(140, 190, 240, Y2, 2, "exp(100)")
control(190, Y2 - DY - R, 70, Y2, Y2 - DY - R - 24, B(3))
seg(240, Y2, 270, Y2)
blocking(270, Y2)
ctl(270, Y2, B(4))
arrow(270 + TRI_W, 330, Y2)
transport(330, 380, 430, Y2, 3, 5, "M2 → W")
arrow(430, 490, Y2)
multi(490, 540, 590, Y2, inf_names("W"), unlimited=True)
labels(540, Y2 + DY + R + 22, [(t_eq(*TVYV), 16, False),
                               ([("склад, ", "n"), ("m", "i"), (" = ∞", "n")], 14, True)])
arrow(590, 650, Y2)
rich(656, Y2 + 6, [("вихід", "n")], size=16, anchor="start")

# ------------------------------------------------------------------ фрагмент руху роботів
y_box = Y3 - 150
add(f'<rect x="20" y="{y_box}" width="780" height="320" fill="none" stroke="#000" stroke-width="1.0" '
    f'stroke-dasharray="8 5"/>')
caption(34, y_box + 22, "Фрагмент руху роботів: замкнена мережа, запити – роботи R1, R2, R3", size=16,
        anchor="start")
multi(170, 220, 270, Y3, ROBOTS)
labels(220, Y3 + DY + R + 22, [(t_eq(("0", "n")), 16, False),
                               ([("П: роботи в пунктах, ", "n"), ("m", "i"), (" = 3", "n")], 14, True)])
seg(270, Y3, 300, Y3)
blocking(300, Y3)
ctl(300, Y3, [("B", "i"), ("Х", "s"), ("(", "n"), ("S", "i"), (", ", "n"), ("t", "i"), (")", "n")])
arrow(300 + TRI_W, 360, Y3)
multi(360, 410, 460, Y3, ROBOTS)
labels(410, Y3 + DY + R + 22, [(t_eq(("d", "i"), ("(", "n"), ("pos", "i"), ("r", "si"), (", ", "n"),
                                     ("src", "i"), ("S", "si"), (")", "n")), 16, False),
                               ([("Х: холостий хід, ", "n"), ("m", "i"), (" = 3", "n")], 14, True)])
# повернення робота з Х у П (кінець холостого ходу)
y_back = Y3 + DY + R + 60
seg(460, Y3, 500, Y3)
seg(500, Y3, 500, y_back)
seg(500, y_back, 120, y_back)
seg(120, y_back, 120, Y3)
arrow(120, 170, Y3)
caption(512, Y3 + 30, "кінець холостого ходу:", size=14, anchor="start")
rich(512, Y3 + 50, [("pos", "i"), ("r", "si"), (" := ", "n"), ("src", "i"), ("S", "si")], size=15, anchor="start")

# ------------------------------------------------------------------ пояснення
W, H = 840, 1130
lines = [
    [("К", "n"), (" – керування роботами: за станом пристроїв T1–T3, П, Х і верстатів задає умови ", "n"),
     ("B", "i"), ("0", "s"), (", ", "n"), ("B", "i"), ("2", "s"), (", ", "n"), ("B", "i"), ("4", "s"),
     (", ", "n"), ("B", "i"), ("Х", "s"), (" за (2.3)-(2.5);", "n")],
    [("пристрій ", "n"), ("r", "i"), (" СМО T1, T2, T3, П, Х – робот ", "n"), ("r", "i"), ("; ", "n"),
     ("t", "i"), ("зв", "s"), (" – затримка звільнення пристрою після виходу деталі;", "n")],
    [("t", "i"), ("зх", "s"), (", ", "n"), ("t", "i"), ("вив", "s"),
     (" = unif(8, 1) – захоплення і вивільнення деталі роботом", "n")],
]
for k, runs in enumerate(lines):
    rich(W / 2, H - 70 + 21 * k, runs, size=14, fill="#333")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
       f'<title>Мережа МО, варіант 2</title>'
       f'<rect width="{W}" height="{H}" fill="#fff"/>' + "".join(els) + "</svg>\n")
OUT.write_text(svg, encoding="utf-8")
print(W, H)
