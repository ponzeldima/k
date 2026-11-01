"""Генерує SVG-схему мережі МО для варіанта 1 (роботи закріплені за шляхами)."""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(sys.argv[1])
FONT = "Times New Roman"
R = 24           # радіус пристрою
DY = 64          # відстань між каналами багатоканальної СМО
TRI_W, TRI_H = 22, 26
Y1, Y2 = 150, 480
Y_MID = 330      # перехід з першого ряду в другий

els: list[str] = []


def add(s: str) -> None:
    els.append(s)


def seg(x1, y1, x2, y2, dashed=False):
    st = 'stroke="#000" stroke-width="1.2" stroke-dasharray="5 4"' if dashed else 'stroke="#000" stroke-width="1.4"'
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {st} fill="none"/>')


def head(x, y, direction):
    """Вістря стрілки з вершиною в (x, y): r – вправо, d – вниз."""
    L, Wd = 10, 4
    pts = f"{x},{y} {x - L},{y - Wd} {x - L},{y + Wd}" if direction == "r" else f"{x},{y} {x - Wd},{y - L} {x + Wd},{y - L}"
    add(f'<polygon points="{pts}" fill="#000"/>')


def arrow(x1, x2, y):
    seg(x1, y, x2 - 6, y)
    head(x2, y, "r")


def rich(x, y, runs, size=16, anchor="middle", fill="#000"):
    """runs: (текст, вид), вид: n – прямий, i – курсив, s – нижній індекс, si – індекс курсивом."""
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


def caption(x, y, text, size=14):
    rich(x, y, [(text, "n")], size=size, fill="#333")


def device(cx, cy, name, idx=None):
    add(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#fff" stroke="#000" stroke-width="1.4"/>')
    rich(cx, cy + 6, [(name, "n")] + ([(idx, "s")] if idx else []), size=16)


def blocking(x, y):
    add(f'<polygon points="{x},{y - TRI_H / 2} {x},{y + TRI_H / 2} {x + TRI_W},{y}" '
        f'fill="#808080" stroke="#000" stroke-width="1.2"/>')


def control(x_from, y_from, x_tri, y_tri, y_top, label_runs):
    """Керуючий зв'язок: пунктир від елемента вгору, ліворуч і вниз до трикутника блокування."""
    xt = x_tri + 4
    tip = y_tri - TRI_H / 2 + 3
    seg(x_from, y_from, x_from, y_top, dashed=True)
    seg(x_from, y_top, xt, y_top, dashed=True)
    seg(xt, y_top, xt, tip - 9, dashed=True)
    head(xt, tip, "d")
    rich((xt + x_from) / 2, y_top - 7, label_runs, size=16)


def multi(x_in, cx, x_out, y, name, unlimited=False):
    """Багатоканальна СМО: три пристрої або (unlimited) пристрої 1 … ∞."""
    ys = [y - DY, y, y + DY]
    seg(x_in, ys[0], x_in, ys[-1])
    seg(x_out, ys[0], x_out, ys[-1])
    for k, yk in enumerate(ys, start=1):
        if unlimited and k == 2:
            for dy in (-12, 0, 12):
                add(f'<circle cx="{cx}" cy="{yk + dy}" r="2.2" fill="#000"/>')
            continue
        seg(x_in, yk, cx - R, yk)
        seg(cx + R, yk, x_out, yk)
        device(cx, yk, name, "∞" if unlimited and k == 3 else str(k if not unlimited else 1))


def labels(cx, y_top, lines):
    """Підписи під елементом: (runs, розмір, сірий)."""
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


def robot(cx, y, d, k):
    device(cx, y, f"R{k}")
    labels(cx, y + R + 22, [(t_eq(*TZX, (f" + {d}", "n")), 16, False),
                            (tzv_eq(*TVYV, (f" + {d}", "n")), 16, False),
                            ([(f"робот {k}", "n")], 14, True)])


def machine(x_in, cx, x_out, y, k, law):
    multi(x_in, cx, x_out, y, f"M{k}")
    labels(cx, y + DY + R + 22, [(t_eq(*TVYV, (f" + {law}", "n")), 16, False),
                                 (tzv_eq(*TZX), 16, False),
                                 ([(f"верстат {k}, ", "n"), ("m", "i"), (" = 3", "n")], 14, True)])


# ------------------------------------------------------------------ перший ряд
arrow(8, 108, Y1)
caption(58, Y1 - 10, "деталі")
rich(58, Y1 + 22, [("t", "i"), (" = exp(40)", "n")])
multi(108, 158, 208, Y1, "A", unlimited=True)
labels(158, Y1 + DY + R + 22, [(t_eq(("0, ", "n"), ("t", "i"), ("зв", "s"), (" = ", "n"), *TZX), 16, False),
                               ([("площадка A, ", "n"), ("m", "i"), (" = ∞", "n")], 14, True)])
seg(208, Y1, 238, Y1)
blocking(238, Y1)
arrow(238 + TRI_W, 318 - R, Y1)
robot(318, Y1, 6, 1)
control(318, Y1 - R, 238, Y1, Y1 - R - 34, B(0))
seg(318 + R, Y1, 364, Y1)
blocking(364, Y1)
arrow(364 + TRI_W, 420, Y1)
machine(420, 470, 520, Y1, 1, "norm(60, 10)")
control(470, Y1 - DY - R, 364, Y1, Y1 - DY - R - 24, B(1))
seg(520, Y1, 550, Y1)
blocking(550, Y1)
arrow(550 + TRI_W, 640 - R, Y1)
robot(640, Y1, 7, 2)
control(640, Y1 - R, 550, Y1, Y1 - R - 34, B(2))

# ------------------------------------------------------------------ перехід до другого ряду
seg(640 + R, Y1, 700, Y1)
seg(700, Y1, 700, Y_MID)
seg(700, Y_MID, 40, Y_MID)
seg(40, Y_MID, 40, Y2)
seg(40, Y2, 70, Y2)

# ------------------------------------------------------------------ другий ряд
blocking(70, Y2)
arrow(70 + TRI_W, 140, Y2)
machine(140, 190, 240, Y2, 2, "exp(100)")
control(190, Y2 - DY - R, 70, Y2, Y2 - DY - R - 24, B(3))
seg(240, Y2, 270, Y2)
blocking(270, Y2)
arrow(270 + TRI_W, 360 - R, Y2)
robot(360, Y2, 5, 3)
control(360, Y2 - R, 270, Y2, Y2 - R - 34, B(4))
arrow(360 + R, 440, Y2)
multi(440, 490, 540, Y2, "W", unlimited=True)
labels(490, Y2 + DY + R + 22, [(t_eq(*TVYV), 16, False),
                               ([("склад, ", "n"), ("m", "i"), (" = ∞", "n")], 14, True)])
arrow(540, 600, Y2)
rich(606, Y2 + 6, [("вихід", "n")], size=16, anchor="start")

# ------------------------------------------------------------------ пояснення
W, H = 730, 700
rich(W / 2, 652, [("t", "i"), (" – час обслуговування в пристрої; ", "n"), ("t", "i"), ("зв", "s"),
                  (" – затримка звільнення пристрою після виходу деталі;", "n")], size=14, fill="#333")
rich(W / 2, 672, [("t", "i"), ("зх", "s"), (", ", "n"), ("t", "i"), ("вив", "s"),
                  (" = unif(8, 1) – захоплення і вивільнення деталі роботом", "n")], size=14, fill="#333")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
       f'<title>Мережа МО, варіант 1</title>'
       f'<rect width="{W}" height="{H}" fill="#fff"/>' + "".join(els) + "</svg>\n")
OUT.write_text(svg, encoding="utf-8")
print(W, H)
