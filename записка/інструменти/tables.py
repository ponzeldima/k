"""Таблиці записки, що будуються з результатів експериментів (results/*.csv).

Запуск: python tables.py <каталог results> <каталог для .md>
Кожна таблиця записується в окремий файл і вставляється в розділ рядком «@include таблиці/<файл>».
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

from scipy import stats

BASE = {"in_arrival": "exp(40)", "in_m1": "norm(60,10)", "in_m2": "exp(100)", "in_handling": "unif(8,1)",
        "in_m2_capacity": "3", "in_travel": "×1"}
INPUT_NAME = {"in_arrival": r"\tau_A", "in_m1": r"t_{\text{обр}1}", "in_m2": r"t_{\text{обр}2}",
              "in_handling": r"t_{\text{зх}},\ t_{\text{вив}}", "in_m2_capacity": "m_2", "in_travel": "k_d"}


# очікувана реакція моделі на зміну вхідних змінних (формулювання для записки, за номером сценарію)
EXPECTED = {
    1: "базовий прогін для порівняння",
    2: "система недовантажена: $\\Lambda \\approx 3600 / 80 = 45$ дет./год, черга на площадці мала, "
       "коефіцієнти використання менші, ніж у базовому прогоні",
    3: "перевантаження сильніше: $\\Lambda$ не зростає, бо її обмежує M2; черга і час проходження більші, "
       "ніж у базовому прогоні",
    4: "M2 перестає бути вузьким місцем: $\\Lambda \\approx 90$ дет./год, черга не накопичується, час "
       "проходження різко менший",
    5: "вузьким місцем стає M1: $\\rho_{\\mathrm{M1}} \\approx 1$, $\\Lambda$ менша, ніж у базовому прогоні",
    6: "як у сценарії 4: $\\Lambda \\approx 90$ дет./год, черга не накопичується",
    7: "роботи швидші: їх коефіцієнт використання менший, $\\Lambda$ більша",
    8: "роботи повільніші: їх коефіцієнт використання більший, $\\Lambda$ менша, час проходження більший",
    9: "$\\Lambda = 3600 / 300 = 12$ дет./год; у варіанті 1 кожна деталь проходить систему за 226 с, у варіанті 2 – "
       "перші три за 226, 232 і 239 с, наступні за 244 с (розрахунок у підрозділі 3.9)",
}


def num(v: float, digits: int) -> str:
    """Число з десятковою комою і знаком «−»; групи розрядів від 10 000 – через нерозривний пробіл."""
    v = float(v)
    if round(v, digits) == 0:
        v = 0.0  # без «−0,00»
    text = f"{v:,.{digits}f}" if abs(v) >= 10_000 else f"{v:.{digits}f}"
    return text.replace(",", "\u00a0").replace(".", ",").replace("-", "\u2212")


def mnum(v: float, digits: int) -> str:
    """Те саме для формули: кома без пробілу після неї ({,}), звичайний мінус."""
    return num(v, digits).replace(",", "{,}").replace("\u2212", "-")


def pm(mean: float, ci: float, digits: int) -> str:
    return f"{num(mean, digits)} ± {num(ci, digits)}"


def pm_auto(mean: float, ci: float, digits: int) -> str:
    """Середнє ± півширина; більше знаків, якщо півширина інакше округлюється до нуля."""
    while 0 < ci < 0.5 * 10 ** -digits and digits < 4:
        digits += 1
    return pm(mean, ci, digits)


def ci95(values: list[float]) -> tuple[float, float]:
    """Середнє і півширина 95 %-го довірчого інтервалу (розподіл Стьюдента)."""
    n = len(values)
    mean = sum(values) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    return mean, stats.t.ppf(0.975, n - 1) * std / math.sqrt(n)


def fnum(f: float) -> str:
    """Значення критерію Фішера: від дуже малих до дуже великих."""
    if f >= 1000:
        return num(round(f), 0)
    if f >= 10:
        return num(f, 1)
    if f >= 0.01:
        return num(f, 2)
    mant, exp_ = f"{f:.1e}".split("e")
    return f"${mant.replace('.', '{,}')}\\cdot 10^{{{int(exp_)}}}$"


def write(out: Path, name: str, lines: list[str]) -> None:
    (out / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def dist_tex(s: str) -> str:
    """exp(40) -> \\exp(40); norm(60,10) -> \\mathrm{norm}(60, 10); unif(2,0.5) -> \\mathrm{unif}(2;\\ 0{,}5)."""
    if s.startswith("×"):
        return s[1:]
    if "(" not in s:
        return s
    name, args = s.split("(", 1)
    parts = [a.strip() for a in args.rstrip(")").split(",")]
    has_frac = any("." in a for a in parts)
    parts = [a.replace(".", "{,}") for a in parts]
    sep = r";\ " if has_frac else ", "
    head = r"\exp" if name == "exp" else rf"\mathrm{{{name}}}"
    return f"{head}({sep.join(parts)})"


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def verification(results: Path, out: Path) -> None:
    rows = read(results / "verification.csv")
    by = {}
    for r in rows:
        by.setdefault(r["strategy"], []).append(r)
    ded = by["dedicated"]
    # сценарії (вхідні змінні) – однакові для обох варіантів
    lines = ["Таблиця 3.4 – Сценарії верифікації: змінені вхідні змінні та очікувана реакція моделі", "",
             "| № | Змінена вхідна змінна | Очікувана реакція моделі |", "|:-:|---|---|"]
    for k, r in enumerate(ded, start=1):
        changed = [f"${INPUT_NAME[c]} = {dist_tex(r[c])}$" for c in BASE if r[c] != BASE[c]]
        if r["scenario"].startswith("детерміновані"):
            changed = ["усі часи детерміновані: $\\tau_A = 300$, $t_{\\text{обр}1} = 60$, $t_{\\text{обр}2} = 100$, "
                       "$t_{\\text{зх}} = t_{\\text{вив}} = 8$ с"]
        text = "; ".join(changed) if changed else "базові значення (таблиця 1.2)"
        lines.append(f"| {k} | {text} | {EXPECTED[k]} |")
    (out / "verification_scenarios.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for strategy, no, label in (("dedicated", "3.5", "варіант 1"), ("nearest", "3.6", "варіант 2")):
        lines = [f"Таблиця {no} – Результати верифікації, {label}", "",
                 r"| № | $\Lambda$, дет./год | $\bar\tau$, с | $L_{max}$, шт. | $\bar L_A$, од. | $\rho_{\mathrm{M1}}$ "
                 r"| $\rho_{\mathrm{M2}}$ | $\bar\rho_{\mathrm{R}}$ | $N_{\text{кін}}$, шт. |",
                 "|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|"]
        for k, r in enumerate(by[strategy], start=1):
            lines.append(
                f"| {k} | {num(r['throughput_per_hour'], 1)} | {num(r['sojourn_mean'], 0)} | "
                f"{num(r['buffer_max'], 1)} | {num(r['buffer_mean'], 1)} | {num(r['M1_occupied'], 3)} | "
                f"{num(r['M2_occupied'], 3)} | {num(r['robots_util_mean'], 3)} | {num(r['wip_end'], 1)} |")
        (out / f"verification_{strategy}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- розділ 4

VARIANTS = (("dedicated", "варіант 1"), ("nearest", "варіант 2"))
ARRIVALS = ("40", "60")
# відгук -> (позначення в записці, кількість знаків після коми)
RESPONSE = {
    "throughput_per_hour": (r"$\Lambda$, дет./год", 2),
    "sojourn_mean": (r"$\bar\tau$, с", 1),
    "sojourn_p90": (r"90%-квантиль $\tau$, с", 1),
    "buffer_max": (r"$L_{max}$, шт.", 1),
    "buffer_mean": (r"$\bar L_A$, од.", 2),
    "buffer_q99": (r"99%-квантиль $L_A$, шт.", 1),
    "M1_occupied": (r"$\rho_{\mathrm{M1}}$", 3),
    "M2_occupied": (r"$\rho_{\mathrm{M2}}$", 3),
    "robot1_util": (r"$\rho_{\mathrm{R1}}$", 3),
    "robot2_util": (r"$\rho_{\mathrm{R2}}$", 3),
    "robot3_util": (r"$\rho_{\mathrm{R3}}$", 3),
    "robots_util_mean": (r"$\bar\rho_{\mathrm{R}}$", 3),
}
# відгуки, які при exp(40) не мають сталого значення (зростають з часом моделювання)
GROWING = {"sojourn_mean", "sojourn_p90", "buffer_max", "buffer_mean", "buffer_q99"}


def level(metric: str, v: float) -> str:
    """Рівень відгуку для таблиці перехідного періоду."""
    if metric == "buffer_mean":
        return num(v, 2 if v < 10 else 1)
    digits = {"throughput_per_hour": 1, "sojourn_mean": 0}.get(metric, RESPONSE[metric][1])
    return num(v, digits)


def warmup(results: Path, out: Path) -> None:
    lines = ["Таблиця 4.2 – Тривалість перехідного періоду за умовою (4.1), 5 прогонів, $\\varepsilon$ = 5% від рівня "
             "відгуку", "",
             "| Відгук | Інтервал надходження | Варіант 1: рівень | Варіант 1: $T$, тис. с | Варіант 2: рівень "
             "| Варіант 2: $T$, тис. с |",
             "|---|:-:|:-:|:-:|:-:|:-:|"]
    for metric in ("throughput_per_hour", "sojourn_mean", "buffer_mean", "M2_occupied", "robots_util_mean"):
        for a in ARRIVALS:
            rows = {r["strategy"]: r for r in read(results / f"warmup_summary_a{a}.csv") if r["metric"] == metric}
            cells = []
            for strategy, _ in VARIANTS:
                r = rows[strategy]
                T = float(r["T_transient"])
                cells += [level(metric, float(r["final_mean"])),
                          "не досягається" if math.isnan(T) else num(T / 1000, 0)]
            lines.append(f"| {RESPONSE[metric][0]} | $\\exp({a})$ | " + " | ".join(cells) + " |")
    write(out, "warmup.md", lines)


def replications(results: Path, out: Path) -> None:
    lines = ["Таблиця 4.3 – Кількість прогонів за формулою (2.11), пілотна серія з 20 прогонів, "
             "$\\varepsilon$ = 2% від середнього", "",
             "| Відгук | Інтервал надходження | Варіант 1: $\\bar x$ | Варіант 1: $\\sigma$ | Варіант 1: $p$ "
             "| Варіант 2: $\\bar x$ | Варіант 2: $\\sigma$ | Варіант 2: $p$ |",
             "|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|"]
    for metric in ("throughput_per_hour", "sojourn_mean", "buffer_max", "M2_occupied", "robots_util_mean"):
        for a in ARRIVALS:
            rows = {r["strategy"]: r for r in read(results / f"replications_a{a}.csv") if r["response"] == metric}
            cells = []
            for strategy, _ in VARIANTS:
                r = rows[strategy]
                digits = RESPONSE[metric][1]
                p = "—" if a == "40" and metric in GROWING else num(float(r["p_chebyshev"]), 0)
                cells += [num(float(r["mean"]), digits), num(float(r["std"]), digits), p]
            lines.append(f"| {RESPONSE[metric][0]} | $\\exp({a})$ | " + " | ".join(cells) + " |")
    write(out, "replications.md", lines)


def compare(results: Path, out: Path) -> None:
    raw = {a: read(results / f"compare_a{a}_raw.csv") for a in ARRIVALS}
    lines = ["Таблиця 4.4 – Вихідні характеристики ГВС для двох способів закріплення роботів "
             "(середнє ± півширина 95%-го довірчого інтервалу за 30 прогонами)", "",
             "| Характеристика | $\\exp(40)$: варіант 1 | $\\exp(40)$: варіант 2 | $\\exp(60)$: варіант 1 "
             "| $\\exp(60)$: варіант 2 |",
             "|---|:-:|:-:|:-:|:-:|"]
    for metric in RESPONSE:
        cells = []
        for a in ARRIVALS:
            for strategy, _ in VARIANTS:
                if a == "40" and metric in GROWING:
                    cells.append("зростає")
                    continue
                mean, ci = ci95([float(r[metric]) for r in raw[a] if r["strategy"] == strategy])
                cells.append(pm(mean, ci, RESPONSE[metric][1]))
        lines.append(f"| {RESPONSE[metric][0]} | " + " | ".join(cells) + " |")
    write(out, "compare.md", lines)


def anova(results: Path, out: Path) -> None:
    lines = ["Таблиця 4.5 – Дисперсійний аналіз впливу способу закріплення роботів ($q = 2$, $p = 30$, "
             "$F_{\\text{кр}} = 4{,}01$)", "",
             "| Відгук | Інтервал надходження | $\\bar y_1$ | $\\bar y_2$ | $\\bar y_2 - \\bar y_1$ | $F$ "
             "| Вплив фактора |",
             "|---|:-:|:-:|:-:|:-:|:-:|:-:|"]
    for a in ARRIVALS:
        for r in read(results / f"compare_a{a}_anova.csv"):
            metric = r["response"]
            if a == "40" and metric in GROWING:
                continue
            digits = RESPONSE[metric][1]
            sig = "значущий" if r["significant"] == "True" else "незначущий"
            lines.append(
                f"| {RESPONSE[metric][0]} | $\\exp({a})$ | {num(float(r['mean_dedicated']), digits)} | "
                f"{num(float(r['mean_nearest']), digits)} | "
                f"{pm_auto(float(r['paired_diff_mean']), float(r['paired_diff_ci']), digits)} | "
                f"{fnum(float(r['F_classic']))} | {sig} |")
    write(out, "anova.md", lines)


def capacity(results: Path, out: Path) -> None:
    rows = read(results / "capacity.csv")
    by = {(r["strategy"], r["arrival_mean"]): r for r in rows}
    arrivals = sorted({int(r["arrival_mean"]) for r in rows})
    lines = ["Таблиця 4.6 – Пропускна здатність ГВС залежно від інтервалу надходження деталей (10 прогонів)", "",
             "| $\\tau_A$, с | $\\lambda$, дет./год | Варіант 1: $\\Lambda$, дет./год | Варіант 1: $N_{\\text{кін}}$, шт. "
             "| Варіант 1: режим | Варіант 2: $\\Lambda$, дет./год | Варіант 2: $N_{\\text{кін}}$, шт. "
             "| Варіант 2: режим |",
             "|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|"]
    for a in arrivals:
        cells = [str(a), num(3600 / a, 1)]
        for strategy, _ in VARIANTS:
            r = by[(strategy, str(a))]
            cells += [num(float(r["throughput_per_hour"]), 1), num(float(r["wip_end"]), 0),
                      "стійкий" if r["stable"] == "True" else "нестійкий"]
        lines.append("| " + " | ".join(cells) + " |")
    write(out, "capacity.md", lines)


LAW = {
    "normal": "нормальний",
    "exponential (shifted)": "експоненціальний зі зсувом",
    "gamma (shifted)": "гамма зі зсувом",
    "lognormal (shifted)": "логнормальний зі зсувом",
    "erlang/gamma (loc=0)": "гамма без зсуву",
}


def law_params(law: str, p: list[float]) -> str:
    """Оцінки параметрів у позначеннях записки (параметри scipy -> формули (4.6), (4.7))."""
    if law == "normal":
        return f"$\\mu = {mnum(p[0], 1)};\\ \\sigma = {mnum(p[1], 1)}$"
    if law == "exponential (shifted)":
        return f"$c = {mnum(p[0], 1)};\\ m = {mnum(p[1], 1)}$"
    if law == "gamma (shifted)":
        return f"$k = {mnum(p[0], 3)};\\ c = {mnum(p[1], 1)};\\ \\theta = {mnum(p[2], 1)}$"
    if law == "lognormal (shifted)":
        return f"$s = {mnum(p[0], 3)};\\ c = {mnum(p[1], 1)};\\ \\mu = {mnum(math.log(p[2]), 3)}$"
    return f"$k = {mnum(p[0], 3)};\\ \\theta = {mnum(p[2], 1)}$"


def distribution(results: Path, out: Path) -> None:
    desc = {s: json.loads((results / f"dist_describe_{s}_a60.json").read_text(encoding="utf-8")) for s, _ in VARIANTS}
    lines = ["Таблиця 4.7 – Статистичні характеристики вибірки часу проходження деталей, $\\exp(60)$", "",
             "| Характеристика | Варіант 1 | Варіант 2 |", "|---|:-:|:-:|"]
    for key, label, digits in (("n", "обсяг вибірки $n$", 0), ("mean", "середнє $\\bar\\tau$, с", 1),
                               ("std", "середнє квадратичне відхилення $s_\\tau$, с", 1),
                               ("cv", "коефіцієнт варіації $s_\\tau / \\bar\\tau$", 3),
                               ("min", "найменше значення, с", 1), ("p50", "медіана, с", 1),
                               ("p90", "90%-квантиль, с", 1), ("p95", "95%-квантиль, с", 1),
                               ("max", "найбільше значення, с", 1), ("skew", "коефіцієнт асиметрії", 2)):
        lines.append(f"| {label} | " + " | ".join(num(desc[s][key], digits) for s, _ in VARIANTS) + " |")
    write(out, "dist_describe.md", lines)

    lines = ["Таблиця 4.8 – Перевірка гіпотез про закон розподілу часу проходження за критерієм $\\chi^2$ "
             "($\\alpha = 0{,}05$)", "",
             "| Варіант | Закон розподілу | Оцінка параметрів | $\\chi^2$ | $\\nu$ | $\\chi^2_{\\text{кр}}$ | Гіпотеза |",
             "|:-:|---|---|:-:|:-:|:-:|:-:|"]
    for strategy, label in VARIANTS:
        for r in read(results / f"dist_fits_{strategy}_a60.csv"):
            lines.append(
                f"| {label[-1]} | {LAW[r['law']]} | {law_params(r['law'], json.loads(r['params_raw']))} | "
                f"{num(float(r['chi2']), 2)} | {r['df']} | {num(float(r['chi2_crit_0.05']), 2)} | "
                f"{'приймається' if r['accepted'] == 'True' else 'відхиляється'} |")
    write(out, "dist_fits.md", lines)


# --- розділ 5

def m2_cycle(results: Path, out: Path) -> None:
    """Складові циклу місця M2 на одну оброблену деталь і холостий хід роботів, exp(40)."""
    raw = read(results / "compare_a40_raw.csv")

    def mean_of(strategy: str, f) -> float:
        vals = [f(r) for r in raw if r["strategy"] == strategy]
        return sum(vals) / len(vals)

    def cycle(r: dict) -> float:  # 3T / N_W – час, за який одне місце M2 обробляє одну деталь
        return 3 * (float(r["t_end"]) - float(r["t_warmup"])) / float(r["completed"])

    groups = [
        ("Цикл місця M2 на одну деталь, с", [
            ("обробка", lambda r: float(r["M2_processing"]) * cycle(r)),
            ("вивільнення і захоплення роботом", lambda r: float(r["M2_handling"]) * cycle(r)),
            ("блокування: оброблена деталь чекає на робота", lambda r: float(r["M2_blocked"]) * cycle(r)),
            ("простій: місце вільне, нову деталь ще не доставлено",
             lambda r: (1 - float(r["M2_occupied"])) * cycle(r)),
            ("разом, $3T / N_W$", cycle),
        ]),
        ("Холостий хід робота на одне перевезення (у варіанті 1 – повернення), с", [
            ("шлях 1: до пункту прибуття A", lambda r: float(r["empty_route1_mean"])),
            ("шлях 2: до верстата M1", lambda r: float(r["empty_route2_mean"])),
            ("шлях 3: до верстата M2", lambda r: float(r["empty_route3_mean"])),
            ("разом на одну деталь", lambda r: sum(float(r[f"empty_route{k}_mean"]) for k in (1, 2, 3))),
        ]),
        ("Частка часу, коли біля верстата чекає робот з деталлю", [
            ("біля M1", lambda r: float(r["M1_robot_waiting"])),
            ("біля M2", lambda r: float(r["M2_robot_waiting"])),
        ]),
    ]
    lines = ["Таблиця 5.1 – Складові циклу місця верстата M2 і робота роботів при $\\exp(40)$ (середнє за 30 прогонами)",
             "", "| Величина | Варіант 1 | Варіант 2 |", "|---|:-:|:-:|"]
    for title, rows in groups:
        lines.append(f"| *{title}* | | |")
        digits = 2 if title.startswith("Частка") else 1
        for label, f in rows:
            lines.append(f"| {label} | " + " | ".join(num(mean_of(s, f), digits) for s, _ in VARIANTS) + " |")
    write(out, "m2_cycle.md", lines)


def improvement(results: Path, out: Path) -> None:
    lines = ["Таблиця 5.2 – Результати пробних запусків пропозицій, $\\exp(40)$, 20 прогонів", "",
             "| Пропозиція | Варіант | $\\Lambda$, дет./год | Режим | $\\bar\\tau$, с | $L_{max}$, шт. "
             "| $\\rho_{\\mathrm{M2}}$ | $\\bar\\rho_{\\mathrm{R}}$ |",
             "|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|"]
    rows = read(results / "improvement_a40.csv")

    def group(r: dict) -> int:  # базова система, 4 місця на M2, 4-й робот, обидві зміни
        name = r["scenario"]
        return 0 if name == "базова система" else 3 if " і " in name else 2 if "робот" in name else 1

    # у групі «4-й робот» спершу всі рядки варіанта 1, потім варіант 2
    rows.sort(key=lambda r: (group(r), r["strategy"] != "dedicated"))
    for r in rows:
        stable = r["stable"] == "True"
        mark = "" if stable else "*"
        lines.append(
            f"| {r['scenario']} | {'1' if r['strategy'] == 'dedicated' else '2'} | "
            f"{pm(float(r['throughput_per_hour']), float(r['throughput_per_hour_ci']), 1)} | "
            f"{'стійкий' if stable else 'нестійкий'} | {num(float(r['sojourn_mean']), 0)}{mark} | "
            f"{num(float(r['buffer_max']), 1)}{mark} | {num(float(r['M2_occupied']), 3)} | "
            f"{num(float(r['robots_util_mean']), 3)} |")
    write(out, "improvement.md", lines)


if __name__ == "__main__":
    results, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    verification(results, out)
    for build in (warmup, replications, compare, anova, capacity, distribution, m2_cycle, improvement):
        build(results, out)
    for p in sorted(out.glob("*.md")):
        print(p.name)
