"""Збирання пояснювальної записки у формат .docx.

Markdown-розділи з формулами LaTeX об'єднуються в один документ: розгортаються вставки таблиць
(@include), посилання [@ключ] замінюються номерами джерел, формули з \\tag{N.M} розділяються на
формулу і її номер, ширини стовпців таблиць оцінюються за вмістом, додатки формуються з протоколів
подій і коду програми. Pandoc перетворює документ у .docx (формули – в об'єкти редактора формул
Word), після чого оформлення доводиться до вимог методичних рекомендацій (ДСТУ 3008): титульний
аркуш, стилі, таблиці з рамками, номер формули праворуч, зміст, нумерація сторінок.

Запуск з каталогу k:
  uv run --no-project --with pypandoc_binary --with python-docx python -I записка/інструменти/build_docx.py
"""
from __future__ import annotations

import ast
import copy
import io
import re
import struct
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

import pypandoc
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from lxml import etree

HERE = Path(__file__).resolve().parent
NOTE = HERE.parent      # записка
ROOT = NOTE.parent      # k
OUT = NOTE / "пояснювальна_записка.docx"

FRONT = ["завдання.md", "анотація.md"]
BODY = ["вступ.md", "розділ1.md", "розділ2.md", "розділ3.md", "розділ4.md", "розділ5.md", "висновки.md"]
UNLISTED = ("ЗАВДАННЯ", "АНОТАЦІЯ", "ЗМІСТ")   # заголовки, яких немає у змісті
TOPIC = ("Імітаційна модель роботизованої гнучкої виробничої системи на основі формального опису "
         "мережею масового обслуговування")
YEAR = "2026"
TRACE_UNTIL = 300.0     # протоколи подій у додатку А – до цього моменту, с
CODE_PT = 10            # фрагменти коду в тексті
LISTING_PT = 9          # лістинги в додатках: 89 символів у рядку
TEXT_TW = 9638          # ширина тексту 17 см, twips
FIG_MAX_H_CM = 19.0     # найбільша висота рисунка, см

ALGORITHM = [
    ("rng.py", "генератори випадкових величин"),
    ("params.py", "вхідні змінні та параметри моделі"),
    ("elements.py", "елементи мережі масового обслуговування"),
    ("model.py", "алгоритм імітації"),
]
EXPERIMENTS = [
    ("common.py", "спільні засоби для серій прогонів"),
    ("verification.py", "верифікація моделі"),
    ("warmup.py", "тривалість перехідного періоду"),
    ("replications.py", "кількість прогонів"),
    ("compare.py", "порівняння способів закріплення роботів"),
    ("capacity.py", "межа стійкості"),
    ("distribution.py", "розподіл часу проходження деталей"),
    ("improvement.py", "пробні запуски пропозицій"),
]


# ---------------------------------------------------------------- підготовка Markdown

def read_sources() -> dict[str, str]:
    sources = {}
    for line in (NOTE / "джерела.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([\w-]+):\s+(.+)$", line)
        if m:
            sources[m.group(1)] = m.group(2)
    return sources


def expand_includes(text: str) -> str:
    def repl(m: re.Match) -> str:
        return (NOTE / m.group(1)).read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    return re.sub(r"^@include\s+(\S+)\s*$", repl, text, flags=re.M)


def number_citations(text: str, sources: dict, order: list) -> str:
    """[@ключ, с. 63; @ключ2] -> [N, с. 63; M]; номери – за порядком першого посилання."""
    def repl(m: re.Match) -> str:
        parts = []
        for part in re.split(r";\s*", m.group(1)):
            key, rest = re.match(r"^@([\w-]+)(.*)$", part).groups()
            if key not in sources:
                raise KeyError(f"Невідоме джерело: {key}")
            if key not in order:
                order.append(key)
            parts.append(f"{order.index(key) + 1}{rest}")
        return "[" + "; ".join(parts) + "]"
    return re.sub(r"\[(@[^\]]+)\]", repl, text)


def div(style: str, lines: list[str]) -> list[str]:
    return ["", f'::: {{custom-style="{style}"}}', *lines, ":::", ""]


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def figure(line: str) -> str | None:
    """Рисунок із шириною у відсотках; якщо ширину не задано, рисунок обмежується за висотою."""
    m = re.match(r"^!\[(.*)\]\(([^)]+)\)(?:\{width=(\d+)%\})?\s*$", line)
    if not m:
        return None
    caption, rel, width = m.groups()
    if width is None:
        w, h = png_size(NOTE / rel)
        width = str(round(min(17.0, FIG_MAX_H_CM * w / h) / 17.0 * 100))
    return f"![{caption}]({rel}){{width={width}%}}"


def plain(cell: str) -> str:
    """Приблизний видимий текст комірки: формула рахується за кількістю символів без команд."""
    cell = re.sub(r"\$([^$]*)\$",
                  lambda m: "x" * max(1, len(re.sub(r"\\[a-zA-Z]+|[{}_^\\\s]", "", m.group(1)))), cell)
    return re.sub(r"[*`]", "", cell).strip()


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


CHAR_CM = 0.22          # середня ширина символу Times New Roman 12 пт, см
CELL_PAD_CM = 0.35      # поля комірки і запас, см


def widen(table: list[str]) -> list[str]:
    """Ширини стовпців (кількість рисок у рядку-роздільнику, 10 рисок = 1 см) за вмістом.

    Ширина тексту (17 см) розподіляється пропорційно до бажаної ширини стовпця за довжиною тексту,
    але кожен стовпець отримує щонайменше ширину свого найдовшого слова, щоб слова не розривались.
    """
    rows = [split_row(line) for line in table]
    head, sep, body = rows[0], rows[1], rows[2:]
    need, want = [], []
    for j in range(len(head)):
        cells = [plain(r[j]) for r in body if j < len(r)] or [""]
        lens = [len(c) for c in cells]
        # слова розділяє лише звичайний пробіл: «18 214» з нерозривним пробілом – одне слово
        word = max([len(w) for c in [plain(head[j]), *cells] for w in c.split(" ")] or [1])
        need.append(CELL_PAD_CM + CHAR_CM * word)
        want.append(max(CELL_PAD_CM + CHAR_CM * (0.7 * min(max(lens), 70) + 0.3 * sum(lens) / len(lens)),
                        need[-1]))
    total = TEXT_TW / 567
    fixed: dict[int, float] = {}       # стовпці, яким дісталась лише мінімальна ширина
    while True:
        free = [j for j in range(len(want)) if j not in fixed]
        rest = total - sum(fixed.values())
        scale = rest / sum(want[j] for j in free) if free else 0.0
        short = [j for j in free if want[j] * scale < need[j]]
        if not short or len(fixed) + len(short) == len(want):
            break
        fixed.update({j: need[j] for j in short})
    widths = [fixed.get(j, want[j] * scale) for j in range(len(want))]
    if sum(widths) > total + 1e-6:     # навіть мінімальні ширини не вміщуються – пропорційно до них
        widths = [n * total / sum(need) for n in need]
    marks = []
    for j, s in enumerate(sep):
        d = max(3, round(widths[j] * 10))
        marks.append((":" if s.startswith(":") else "-") + "-" * (d - 2) + (":" if s.endswith(":") else "-"))
    return [table[0], "|" + "|".join(marks) + "|", *table[2:]]


def transform(text: str) -> str:
    """Блокові перетворення одного файлу Markdown."""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i, after_eq = 0, False
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):                       # код – без змін
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            out += lines[i:j + 1]
            i, after_eq = j + 1, False
            continue
        if line.startswith("$$"):                        # формула з номером
            j = i + 1
            while not lines[j].startswith("$$"):
                j += 1
            body = "\n".join(lines[i + 1:j])
            tag = re.search(r"\\tag\{([^}]*)\}", body)
            body = re.sub(r"\s*\\tag\{[^}]*\}", "", body).strip()
            out += ["", "$$", body, "$$", ""]
            if tag:
                out += [f"⟦EQ {tag.group(1)} {'M' if chr(92) * 2 in body else 'S'}⟧", ""]
            i, after_eq = j + 1, True
            continue
        if line.startswith("|"):                         # таблиця
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            out += widen(lines[i:j])
            i, after_eq = j, False
            continue
        if not line.strip():
            out.append(line)
            i += 1
            continue
        h = re.match(r"^#\s+(.*)$", line)
        if h and h.group(1).strip() in UNLISTED:
            out += div("Заголовок поза змістом", [h.group(1).strip()])
        elif re.match(r"^(Таблиця [0-9А-ЯІЇЄҐ]+\.\d+ – |Продовження таблиці )", line):
            out += div("Назва таблиці", [line])
        elif after_eq and line.startswith("де "):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            out += div("Пояснення до формули", lines[i:j])
            i = j
            after_eq = False
            continue
        elif (fig := figure(line)) is not None:
            out.append(fig)
        else:
            out.append(line)
        after_eq = False
        i += 1
    return "\n".join(out)


def load(name: str, sources: dict, order: list) -> str:
    text = expand_includes((NOTE / name).read_text(encoding="utf-8"))
    if name == "анотація.md":
        text = text.replace("⟨N⟩", "⟦NUMPAGES⟧")
    return transform(number_citations(text, sources, order))


def trace(path: Path) -> list[str]:
    """Протокол подій у стислому вигляді: момент, елемент, подія (до TRACE_UNTIL)."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[2:]:
        m = re.match(r"^\s*(\d+\.\d+)?\s*(\S+)\s+(.*)$", line)
        if not m:
            continue
        t, elem, text = m.groups()
        if t is not None and float(t) > TRACE_UNTIL:
            break
        out.append(f"{t or '':>8} {elem:<9} {text}")
    return out


def listing(source: str) -> str:
    """Код без рядків документації і коментарів в окремих рядках (вони є в репозиторії)."""
    drop: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0]
            if (len(node.body) > 1 and isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                drop.update(range(first.lineno, first.end_lineno + 1))
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and not tok.line[:tok.start[1]].strip():
            drop.add(tok.start[0])
    lines = [line for k, line in enumerate(source.split("\n"), start=1) if k not in drop]
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines)).strip("\n")


def code(path: Path) -> list[str]:
    return ["```python", *listing(path.read_text(encoding="utf-8")).split("\n"), "```", ""]


def appendices() -> str:
    md = [
        "# ДОДАТОК А. ПРОТОКОЛИ ПОДІЙ", "",
        "Протоколи отримано командою `uv run fms trace --until 600` при значеннях параметрів і вхідних "
        "змінних з таблиць 1.1 і 1.2 та початковому значенні генераторів 1. Наведено події до моменту "
        f"{TRACE_UNTIL:.0f} с. Кожен рядок містить момент події в секундах, пристрій мережі, у якому "
        "сталася подія, і зміст події. Пристрої позначено так: A.k, M1.k, M2.k, W.k – k-й пристрій СМО A, "
        "M1, M2, W; R1, R2, R3 – СМО роботів у варіанті 1; T1.r, T2.r, T3.r – пристрої $\\mathrm{T1}_r$, "
        "$\\mathrm{T2}_r$, $\\mathrm{T3}_r$ СМО перевезень у варіанті 2, П.r і Х.r – пристрої $\\text{П}_r$ і "
        "$\\text{Х}_r$ фрагмента руху роботів (пристрій з номером r – робот R$r$); Create – надходження "
        "деталей, вихід – вихід з мережі. Запис «затримка звільнення до t» означає, що пристрій передав "
        "деталь далі, але залишається зайнятим до моменту t. Запис «П -> Х відкрито (BХ = 0)» означає, що "
        "для пристрою робота знято блокування маршруту П → Х за правилом (2.5) і робот рушає холостим ходом. "
        "Після кожної групи "
        "одночасних подій виведено стан мережі: кількість зайнятих пристроїв СМО A і стан K кожного "
        "пристрою інших СМО (0 – вільний, 1 – зайнятий, 2 – блокований), а у варіанті 2 також точку "
        "кожного робота, у якій він звільнився або куди прибув холостим ходом (R1@A – робот R1 у точці A).",
        "",
        "## А.1 Протокол подій для варіанта 1", "",
        "```text", *trace(ROOT / "results" / "trace_dedicated.txt"), "```", "",
        "## А.2 Протокол подій для варіанта 2", "",
        "```text", *trace(ROOT / "results" / "trace_nearest.txt"), "```", "",
        "# ДОДАТОК Б. ЛІСТИНГ КОДУ АЛГОРИТМУ ІМІТАЦІЇ", "",
        "Наведено модулі пакета `fms`, що реалізують алгоритм імітації (таблиця 3.1). Повний код програми, "
        "зокрема командний інтерфейс, автоматичні тести і побудову рисунків, розміщено в репозиторії проєкту.",
        "",
    ]
    for k, (name, title) in enumerate(ALGORITHM, start=1):
        md += [f"## Б.{k} Модуль {name} – {title}", "", *code(ROOT / "src" / "fms" / name)]
    md += [
        "# ДОДАТОК В. ЛІСТИНГ КОДУ ЕКСПЕРИМЕНТАЛЬНОГО ДОСЛІДЖЕННЯ", "",
        "Наведено модулі пакета `fms.experiments`, які виконують серії експериментів з таблиці 4.1. "
        "Команди для їх запуску наведено в підрозділі 4.8.", "",
    ]
    for k, (name, title) in enumerate(EXPERIMENTS, start=1):
        md += [f"## В.{k} Модуль {name} – {title}", "", *code(ROOT / "src" / "fms" / "experiments" / name)]
    return "\n".join(md)


def build_markdown() -> tuple[str, list[str], dict]:
    sources = read_sources()
    order: list[str] = []
    parts = [load(name, sources, order) for name in FRONT]
    parts.append("\n".join(div("Заголовок поза змістом", ["ЗМІСТ"]) + ["⟦TOC⟧", ""]))
    parts += [load(name, sources, order) for name in BODY]
    refs = ["# СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ", ""]
    for k, key in enumerate(order, start=1):
        refs += [f"{k}\\. {sources[key]}", ""]
    parts.append("\n".join(refs))
    parts.append(appendices())
    return "\n\n".join(parts) + "\n", order, sources


def check_counts(md: str, order: list, sources: dict) -> None:
    """Звірити кількість рисунків, таблиць, джерел і додатків з анотацією."""
    figures = len(re.findall(r"^!\[Рисунок \d+\.\d+", md, flags=re.M))
    tables = len(set(re.findall(r"^Таблиця (\d+\.\d+) – ", md, flags=re.M)))
    annexes = len(re.findall(r"^# ДОДАТОК ", md, flags=re.M))
    abstract = (NOTE / "анотація.md").read_text(encoding="utf-8")
    expected = {f"з {len(order)} найменувань": len(order), f"{annexes} додатків": annexes,
                f"{figures} рисунків": figures, f"{tables} таблиць": tables}
    for phrase in expected:
        if phrase not in abstract:
            print(f"УВАГА: в анотації немає «{phrase}» – оновіть кількість")
    unused = [k for k in sources if k not in order]
    if unused:
        print("УВАГА: джерела без посилань:", ", ".join(unused))
    print(f"рисунків {figures}, таблиць {tables}, джерел {len(order)}, додатків {annexes}")


# ---------------------------------------------------------------- pandoc

def pandoc() -> str:
    return pypandoc.get_pandoc_path()


def reference_doc(path: Path) -> None:
    """Типовий reference.docx pandoc з розміром сторінки A4 і полями 2 см."""
    data = subprocess.run([pandoc(), "--print-default-data-file", "reference.docx"],
                          capture_output=True, check=True).stdout
    path.write_bytes(data)
    doc = Document(str(path))
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2)
    doc.save(str(path))


def run_pandoc(md: str, tmp: Path) -> Path:
    src, ref, raw = tmp / "записка.md", tmp / "reference.docx", tmp / "raw.docx"
    src.write_text(md, encoding="utf-8")
    reference_doc(ref)
    args = [pandoc(), str(src), "-f", "markdown-citations", "-t", "docx", "--reference-doc", str(ref),
            "--resource-path", str(NOTE), "--columns", "10", "-o", str(raw)]
    res = subprocess.run(args + ["--syntax-highlighting=none"], cwd=NOTE, capture_output=True,
                         text=True, encoding="utf-8")
    if res.returncode != 0 and "syntax-highlighting" in res.stderr:
        res = subprocess.run(args + ["--no-highlight"], cwd=NOTE, capture_output=True, text=True, encoding="utf-8")
    if res.stderr.strip():
        print(res.stderr.strip())
    if res.returncode != 0:
        raise SystemExit(f"pandoc завершився з кодом {res.returncode}")
    return raw


# ---------------------------------------------------------------- оформлення .docx

PPR = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
       "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
       "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid",
       "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
       "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"]
RPR = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline", "shadow",
       "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
       "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
       "em", "lang", "eastAsianLayout", "specVanish", "oMath"]
TBLPR = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize", "tblW",
         "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
         "tblCaption", "tblDescription"]
TRPR = ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter", "cantSplit", "trHeight",
        "tblHeader", "tblCellSpacing", "jc", "hidden"]
LVL = ["start", "numFmt", "lvlRestart", "pStyle", "isLgl", "suff", "lvlText", "lvlPicBulletId", "legacy",
       "lvlJc", "pPr", "rPr"]
SETTINGS_AFTER = {"hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars", "rsids", "mathPr",
                  "attachedSchema", "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats",
                  "doNotAutoCompressPictures", "forceUpgrade", "captions", "readModeInkLockDown", "smartTagType",
                  "schemaLibrary", "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator"}
FONT = "Times New Roman"
MONO = "Courier New"
BUILTIN = {"toc 1": "TOC1", "toc 2": "TOC2", "Header": "Header"}


def W(tag: str) -> str:
    return qn("w:" + tag)


def el(tag: str, **attrs) -> etree._Element:
    e = OxmlElement("w:" + tag)
    for k, v in attrs.items():
        e.set(W(k), str(v))
    return e


def local(e) -> str:
    return e.tag.split("}")[1]


def put(parent, child, order: list[str]):
    """Вставити або замінити дочірній елемент у порядку, якого вимагає схема OOXML."""
    name = local(child)
    for old in parent.findall(child.tag):
        parent.remove(old)
    pos = order.index(name)
    for existing in parent:
        n = local(existing)
        if n in order and order.index(n) > pos:
            existing.addprevious(child)
            return child
    parent.append(child)
    return child


def sub(parent, tag: str, order: list[str]):
    """Наявний дочірній елемент або новий, вставлений у правильному місці."""
    found = parent.find(W(tag))
    return found if found is not None else put(parent, el(tag), order)


def tw(cm: float) -> int:
    return round(cm * 567)


def fonts(rpr, font: str) -> None:
    put(rpr, el("rFonts", ascii=font, hAnsi=font, cs=font, eastAsia=font), RPR)


def para_style(doc, name: str, *, base: str | None = "Normal", font: str = FONT, size: float = 14,
               bold: bool = False, jc: str = "both", first: float = 1.25, left: float = 0.0,
               line: float = 1.5, before: float = 0, after: float = 0, keep_next: bool = False,
               page_break: bool = False, outline: int | None = None, tabs=None) -> str:
    """Задати стиль абзацу повністю (наявні властивості стилю замінюються). Повертає ідентифікатор."""
    try:
        st = doc.styles[name]
    except KeyError:
        st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    if name in BUILTIN:                 # вбудований стиль Word: його ідентифікатор, а не користувацький
        st.style_id = BUILTIN[name]
        st.element.attrib.pop(qn("w:customStyle"), None)
    st.base_style = doc.styles[base] if base else None
    e = st.element
    for tag in ("pPr", "rPr"):
        for old in e.findall(W(tag)):
            e.remove(old)
    p = el("pPr")
    if keep_next:
        put(p, el("keepNext"), PPR)
    if page_break:
        put(p, el("pageBreakBefore"), PPR)
    put(p, el("widowControl"), PPR)
    if tabs:
        t = el("tabs")
        for val, pos, leader in tabs:
            t.append(el("tab", val=val, pos=pos, leader=leader))
        put(p, t, PPR)
    put(p, el("spacing", before=round(before * 20), after=round(after * 20), line=round(240 * line),
              lineRule="auto"), PPR)
    put(p, el("ind", left=tw(left), right=0, firstLine=tw(first)), PPR)
    put(p, el("jc", val=jc), PPR)
    put(p, el("outlineLvl", val=9 if outline is None else outline), PPR)
    e.append(p)
    r = el("rPr")
    fonts(r, font)
    put(r, el("b", val=1 if bold else 0), RPR)
    put(r, el("bCs", val=1 if bold else 0), RPR)
    put(r, el("i", val=0), RPR)
    put(r, el("iCs", val=0), RPR)
    put(r, el("color", val="000000"), RPR)
    put(r, el("sz", val=round(size * 2)), RPR)
    put(r, el("szCs", val=round(size * 2)), RPR)
    e.append(r)
    return st.style_id


def char_style(doc, name: str, font: str, size: float) -> None:
    try:
        st = doc.styles[name]
    except KeyError:
        st = doc.styles.add_style(name, WD_STYLE_TYPE.CHARACTER)
    e = st.element
    for old in e.findall(W("rPr")):
        e.remove(old)
    r = el("rPr")
    fonts(r, font)
    put(r, el("color", val="000000"), RPR)
    put(r, el("sz", val=round(size * 2)), RPR)
    put(r, el("szCs", val=round(size * 2)), RPR)
    e.append(r)


def setup_styles(doc) -> dict[str, str]:
    root = doc.styles.element
    rpr = root.find(W("docDefaults")).find(W("rPrDefault")).find(W("rPr"))
    fonts(rpr, FONT)
    put(rpr, el("sz", val=28), RPR)
    put(rpr, el("szCs", val=28), RPR)
    put(rpr, el("lang", val="uk-UA", eastAsia="uk-UA", bidi="ar-SA"), RPR)
    ids = {"normal": para_style(doc, "Normal", base=None)}
    for name in ("Body Text", "First Paragraph", "Compact"):
        para_style(doc, name)
    para_style(doc, "Heading 1", bold=True, jc="center", first=0, after=12, keep_next=True, page_break=True,
               outline=0)
    para_style(doc, "Heading 2", bold=True, jc="left", before=12, after=6, keep_next=True, outline=1)
    para_style(doc, "Heading 3", bold=True, jc="left", before=6, after=6, keep_next=True, outline=2)
    ids["unlisted"] = para_style(doc, "Заголовок поза змістом", bold=True, jc="center", first=0, after=12,
                                 keep_next=True, page_break=True)
    for name in ("Captioned Figure", "Figure"):
        para_style(doc, name, jc="center", first=0, line=1.0, before=6, keep_next=True)
    para_style(doc, "Image Caption", jc="center", first=0, after=6)
    para_style(doc, "Назва таблиці", jc="both", first=0, before=6, keep_next=True)
    ids["cell"] = para_style(doc, "Текст таблиці", size=12, jc="left", first=0, line=1.0)
    ids["eq"] = para_style(doc, "Формула", jc="center", first=0, line=1.0, before=3, after=3)
    para_style(doc, "Пояснення до формули", first=0)
    ids["code"] = para_style(doc, "Source Code", font=MONO, size=CODE_PT, jc="left", first=0, line=1.0,
                             before=3, after=6)
    char_style(doc, "Verbatim Char", MONO, 12)
    ids["title"] = para_style(doc, "Титульний", jc="center", first=0, line=1.15)
    ids["toc1"] = para_style(doc, "toc 1", jc="left", first=0, tabs=[("right", TEXT_TW, "dot")])
    para_style(doc, "toc 2", jc="left", first=0, left=0.5, tabs=[("right", TEXT_TW, "dot")])
    ids["header"] = para_style(doc, "Header", jc="right", first=0, line=1.0)
    return ids


def text_of(p) -> str:
    return "".join(t.text or "" for t in p.iter(W("t")))


def set_pstyle(p, style_id: str) -> None:
    ppr = p.find(W("pPr"))
    if ppr is None:
        ppr = el("pPr")
        p.insert(0, ppr)
    put(ppr, el("pStyle", val=style_id), PPR)


def equations(doc, ids) -> list:
    """Абзац формули + маркер номера -> таблиця без рамок: [порожньо | формула | (N.M)]."""
    made = []
    for p in list(doc.element.body.iter(W("p"))):
        m = re.fullmatch(r"⟦EQ (\S+) ([MS])⟧", text_of(p).strip())
        if not m:
            continue
        number, kind = m.groups()
        math_p = p.getprevious()
        tbl = el("tbl")
        pr = el("tblPr")
        pr.append(el("tblW", w=5000, type="pct"))
        pr.append(el("jc", val="center"))
        borders = el("tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(el(side, val="nil"))
        pr.append(borders)
        pr.append(el("tblLayout", type="fixed"))
        mar = el("tblCellMar")
        mar.append(el("left", w=0, type="dxa"))
        mar.append(el("right", w=0, type="dxa"))
        pr.append(mar)
        pr.append(el("tblLook", val="0000", firstRow=0, lastRow=0, firstColumn=0, lastColumn=0, noHBand=1,
                     noVBand=1))
        tbl.append(pr)
        widths = [round(TEXT_TW * 0.1), TEXT_TW - 2 * round(TEXT_TW * 0.1), round(TEXT_TW * 0.1)]
        grid = el("tblGrid")
        for w in widths:
            grid.append(el("gridCol", w=w))
        tbl.append(grid)
        tr = el("tr")
        trpr = el("trPr")
        trpr.append(el("cantSplit"))
        tr.append(trpr)
        num_p = el("p")
        num_r = el("r")
        num_t = el("t")
        num_t.text = f"({number})"
        num_r.append(num_t)
        num_p.append(num_r)
        empty_p = el("p")
        tbl.append(tr)
        math_p.addprevious(tbl)
        for w, content, valign in ((widths[0], empty_p, "center"), (widths[1], math_p, "center"),
                                   (widths[2], num_p, "bottom" if kind == "M" else "center")):
            set_pstyle(content, ids["eq"])
            tc = el("tc")
            tcpr = el("tcPr")
            tcpr.append(el("tcW", w=w, type="dxa"))
            tcpr.append(el("vAlign", val=valign))
            tc.append(tcpr)
            tc.append(content)
            tr.append(tc)
        put(num_p.find(W("pPr")), el("jc", val="right"), PPR)
        p.getparent().remove(p)
        made.append(tbl)
    return made


def format_tables(doc, ids, skip) -> None:
    for tbl in doc.element.body.iter(W("tbl")):
        if tbl in skip or tbl.getparent().tag != W("body"):
            continue
        pr = sub(tbl, "tblPr", ["tblPr", "tblGrid", "tr"])
        borders = el("tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(el(side, val="single", sz=4, space=0, color="000000"))
        put(pr, borders, TBLPR)
        mar = el("tblCellMar")
        mar.append(el("left", w=57, type="dxa"))
        mar.append(el("right", w=57, type="dxa"))
        put(pr, mar, TBLPR)
        # сітка pandoc розрахована на іншу ширину сторінки: ті самі пропорції на 17 см
        cols = tbl.find(W("tblGrid")).findall(W("gridCol"))
        grid = [int(c.get(W("w"))) for c in cols]
        widths = [round(g * TEXT_TW / sum(grid)) for g in grid]
        for c, w in zip(cols, widths):
            c.set(W("w"), str(w))
        put(pr, el("tblW", w=sum(widths), type="dxa"), TBLPR)
        for tr in tbl.findall(W("tr")):
            for tc, w in zip(tr.findall(W("tc")), widths):
                tcpr = tc.find(W("tcPr"))
                if tcpr is None:
                    tcpr = el("tcPr")
                    tc.insert(0, tcpr)
                put(tcpr, el("tcW", w=w, type="dxa"), ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge",
                                                     "tcBorders", "shd", "noWrap", "tcMar", "textDirection",
                                                     "tcFitText", "vAlign", "hideMark"])
        for k, tr in enumerate(tbl.findall(W("tr"))):
            trpr = tr.find(W("trPr"))
            if trpr is None:
                trpr = el("trPr")
                first_tc = tr.find(W("tc"))
                first_tc.addprevious(trpr)
            put(trpr, el("cantSplit"), TRPR)
            if k == 0:
                put(trpr, el("tblHeader"), TRPR)
        for p in tbl.iter(W("p")):
            set_pstyle(p, ids["cell"])


def merge_runs(doc) -> None:
    """Об'єднати сусідні текстові фрагменти з однаковим форматуванням."""
    def key(r):
        rpr = r.find(W("rPr"))
        return b"" if rpr is None else etree.tostring(rpr)

    for p in doc.element.body.iter(W("p")):
        prev = None
        for r in list(p):
            kids = [c for c in r if local(c) != "rPr"] if r.tag == W("r") else []
            if len(kids) != 1 or kids[0].tag != W("t"):
                prev = None
                continue
            if prev is not None and key(prev) == key(r):
                t = prev.find(W("t"))
                t.text = (t.text or "") + (kids[0].text or "")
                t.set(qn("xml:space"), "preserve")
                p.remove(r)
            else:
                prev = r


def split_runs(doc, pattern: str, make) -> None:
    """Виділити збіги шаблону в окремі елементи: make(run_copy, текст) повертає елемент для вставки."""
    rx = re.compile(pattern)
    for t in list(doc.element.body.iter(W("t"))):
        if not t.text or not rx.search(t.text):
            continue
        r = t.getparent()
        if r.tag != W("r"):
            continue
        for piece in rx.split(t.text):
            if not piece:
                continue
            nr = copy.deepcopy(r)
            nr.find(W("t")).text = piece
            nr.find(W("t")).set(qn("xml:space"), "preserve")
            r.addprevious(make(nr, piece) if rx.fullmatch(piece) else nr)
        r.getparent().remove(r)


def highlight(run, _text):
    put(sub(run, "rPr", ["rPr", "t"]), el("highlight", val="yellow"), RPR)
    return run


def numpages(run, _text):
    fld = el("fldSimple", instr=" NUMPAGES ")
    run.find(W("t")).text = "—"
    fld.append(run)
    return fld


def toc(doc, ids) -> None:
    for p in doc.element.body.iter(W("p")):
        if text_of(p).strip() != "⟦TOC⟧":
            continue
        for r in p.findall(W("r")):
            p.remove(r)
        set_pstyle(p, ids["toc1"])
        instr = el("instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = ' TOC \\o "1-2" \\h \\z \\u '
        note = el("t")
        note.text = "Зміст формується під час оновлення полів (Word запропонує це при відкритті або натисніть F9)."
        for child in (el("fldChar", fldCharType="begin", dirty="true"), instr,
                      el("fldChar", fldCharType="separate"), note, el("fldChar", fldCharType="end")):
            r = el("r")
            r.append(child)
            p.append(r)
        return


def lists(doc) -> None:
    """Переліки: номер або риска з абзацного відступу, текст далі з лівого поля."""
    part = doc.part.numbering_part.element
    for lvl in part.iter(W("lvl")):
        ilvl = int(lvl.get(W("ilvl")))
        fmt = lvl.find(W("numFmt"))
        if fmt is not None and fmt.get(W("val")) == "bullet":
            sub(lvl, "lvlText", LVL).set(W("val"), "–")
            fonts(sub(lvl, "rPr", LVL), FONT)
        put(lvl, el("suff", val="space"), LVL)
        put(sub(lvl, "pPr", LVL), el("ind", left=tw(1.25 * ilvl), firstLine=tw(1.25)), PPR)


def code_size(doc, ids) -> None:
    """Розмір шрифту коду: у тексті CODE_PT, у додатках LISTING_PT."""
    in_appendix = False
    for p in doc.element.body.iter(W("p")):
        if text_of(p).startswith("ДОДАТОК "):
            in_appendix = True
        ppr = p.find(W("pPr"))
        st = ppr.find(W("pStyle")) if ppr is not None else None
        if st is None or st.get(W("val")) != ids["code"]:
            continue
        size = round((LISTING_PT if in_appendix else CODE_PT) * 2)
        for r in p.iter(W("r")):
            rpr = sub(r, "rPr", ["rPr", "t", "br", "tab"])
            put(rpr, el("sz", val=size), RPR)
            put(rpr, el("szCs", val=size), RPR)


def references(doc) -> None:
    """Список джерел вирівнюється ліворуч, щоб довгі URL не розтягували попередній рядок."""
    inside = False
    for p in doc.element.body.iter(W("p")):
        text = text_of(p).strip()
        if text == "СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ":
            inside = True
        elif inside and text.startswith("ДОДАТОК "):
            return
        elif inside and text:
            ppr = p.find(W("pPr"))
            if ppr is None:
                ppr = el("pPr")
                p.insert(0, ppr)
            put(ppr, el("jc", val="left"), PPR)


def protocol_breaks(doc) -> None:
    """Протоколи подій А.1 і А.2 – з нової сторінки."""
    for p in doc.element.body.iter(W("p")):
        style = p.find(f"{W('pPr')}/{W('pStyle')}")
        if style is not None and style.get(W("val")).startswith("Heading") and re.match(r"А\.\d ", text_of(p)):
            put(p.find(W("pPr")), el("pageBreakBefore"), PPR)


def title_page(doc, ids) -> None:
    body = doc.element.body
    anchor = body[0]

    def para(text: str = "", bold: bool = False, jc: str = "center"):
        p = doc.add_paragraph()
        set_pstyle(p._p, ids["title"])
        put(p._p.find(W("pPr")), el("jc", val=jc), PPR)
        if text:
            run = p.add_run(text)
            run.bold = bold
        anchor.addprevious(p._p)
        return p

    pic = para()
    pic.add_run().add_picture(str(NOTE / "рисунки" / "kpi_title.png"), width=Cm(10.5))
    para()
    for line in ("МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ", "НАЦІОНАЛЬНИЙ ТЕХНІЧНИЙ УНІВЕРСИТЕТ УКРАЇНИ",
                 "«КИЇВСЬКИЙ ПОЛІТЕХНІЧНИЙ ІНСТИТУТ імені ІГОРЯ СІКОРСЬКОГО»",
                 "КАФЕДРА ІНФОРМАТИКИ ТА ПРОГРАМНОЇ ІНЖЕНЕРІЇ"):
        para(line)
    for _ in range(3):
        para()
    para("Курсова робота з освітнього компоненту")
    para("«Комп’ютерне моделювання дискретно-подійних систем.")
    para("Курсова робота»")
    para(f"Тема: {TOPIC}")
    para()
    rows = [
        ("Керівник:", "Виконавець:"),
        ("д.т.н., професор", "Понзель Тетяна Юріївна"),
        ("Стеценко Інна Вячеславівна", "студентка групи ІП-31"),
        ("", "залікова книжка №"),
        ("«Допущено до захисту»", "______________________"),
        ("______________________", ""),
        ("", ""),
        ("«___» __________ 2026 р.", "«11» листопада 2026 р."),
        ("", ""),
        ("Захищено з оцінкою", ""),
        ("______________________", ""),
        ("", ""),
        ("Члени комісії:", ""),
        ("", ""),
        ("______________________", "Інна СТЕЦЕНКО"),
        ("", ""),
        ("______________________", "Дмитро КОРИНЕЦЬКИЙ"),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    tbl = table._tbl
    pr = tbl.find(W("tblPr"))
    put(pr, el("tblW", w=5000, type="pct"), TBLPR)
    borders = el("tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(el(side, val="nil"))
    put(pr, borders, TBLPR)
    for (left, right), row in zip(rows, table.rows):
        for text, cell in ((left, row.cells[0]), (right, row.cells[1])):
            p = cell.paragraphs[0]
            set_pstyle(p._p, ids["title"])
            put(p._p.find(W("pPr")), el("jc", val="left"), PPR)
            if text:
                p.add_run(text).bold = text in ("Керівник:", "Виконавець:")
    anchor.addprevious(tbl)
    for _ in range(3):
        para()
    para(f"Київ – {YEAR}", bold=True)


def page_numbers(doc, ids) -> None:
    for s in doc.sections:
        s.page_width, s.page_height = Cm(21), Cm(29.7)
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(2)
        s.header_distance = s.footer_distance = Cm(1.25)
        s.different_first_page_header_footer = True
        s.header.is_linked_to_previous = False
        p = s.header.paragraphs[0]
        set_pstyle(p._p, ids["header"])
        fld = el("fldSimple", instr=" PAGE ")
        r = el("r")
        t = el("t")
        t.text = "1"
        r.append(t)
        fld.append(r)
        p._p.append(fld)


def settings(doc) -> None:
    root = doc.settings.element
    upd = el("updateFields", val="true")
    for old in root.findall(upd.tag):
        root.remove(old)
    for child in root:
        if local(child) in SETTINGS_AFTER:
            child.addprevious(upd)
            break
    else:
        root.append(upd)


def postprocess(raw: Path, out: Path) -> None:
    doc = Document(str(raw))
    ids = setup_styles(doc)
    eq_tables = equations(doc, ids)
    format_tables(doc, ids, set(eq_tables))
    merge_runs(doc)
    code_size(doc, ids)
    toc(doc, ids)
    lists(doc)
    references(doc)
    protocol_breaks(doc)
    title_page(doc, ids)
    split_runs(doc, r"(⟦NUMPAGES⟧)", numpages)
    split_runs(doc, r"(⟨[^⟩]*⟩)", highlight)
    page_numbers(doc, ids)
    settings(doc)
    left = [text_of(p) for p in doc.element.body.iter(W("p")) if "⟦" in text_of(p)]
    if left:
        print("УВАГА: необроблені маркери:", left[:5])
    try:
        doc.save(str(out))
    except PermissionError:
        raise SystemExit(f"Не вдалося записати {out.name}: файл відкрито в іншій програмі")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    md, order, sources = build_markdown()
    check_counts(md, order, sources)
    with tempfile.TemporaryDirectory() as tmp:
        if "--keep" in sys.argv:            # проміжні файли – для перевірки
            tmp = sys.argv[sys.argv.index("--keep") + 1]
            Path(tmp).mkdir(parents=True, exist_ok=True)
        raw = run_pandoc(md, Path(tmp))
        postprocess(raw, OUT)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
