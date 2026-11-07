"""Елементи мережі масового обслуговування (табл. 3.1 і 3.5 методичних рекомендацій).

  Create  – надходження запитів ззовні: момент наступного надходження;
  QS      – система масового обслуговування з m ідентичних пристроїв без черги
            (m = None – кількість пристроїв не обмежена);
  Channel – пристрій СМО: стан K (0 – вільний, 1 – зайнятий, 2 – блокований) і момент
            завершення обслуговування; після виходу запиту пристрій може звільнятися
            із затримкою (затримка звільнення); j-й пристрій СМО E називається E.j;
  Route   – дуга мережі з умовою блокування B(S, t), спільною для всіх пристроїв СМО-джерела
            або окремою для кожного пристрою (маршрут П -> Х у варіанті 2);
  Exit    – вихід з мережі.

Запити мережі – деталі (Part), а у варіанті 2 також роботи (Robot) у фрагменті руху роботів.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .model import Model

INF = math.inf
FREE, BUSY, BLOCKED = 0, 1, 2


@dataclass(eq=False)
class Part:
    """Запит фрагмента деталей."""

    id: int
    t_arrival: float
    t_ready: dict[int, float] = field(default_factory=dict)  # шлях -> момент готовності до перевезення
    t_grab: dict[int, float] = field(default_factory=dict)   # шлях -> початок захоплення
    t_done: float = INF

    def __str__(self) -> str:
        return f"деталь #{self.id}"


@dataclass(eq=False)
class Robot:
    """Запит фрагмента руху роботів: робот і точка, де він стоїть або куди їде."""

    id: int
    pos: str
    target: str = ""

    def __str__(self) -> str:
        return f"R{self.id}"


class Channel:
    """Пристрій (канал) СМО."""

    __slots__ = ("qs", "index", "K", "tnext", "request", "t_from", "t_split", "seq")

    def __init__(self, qs: "QS", index: int):
        self.qs = qs
        self.index = index
        self.K = FREE
        self.tnext = INF
        self.request = None
        self.t_from = 0.0     # початок поточного стану
        self.t_split = 0.0    # кінець захоплення або вивільнення в поточному стані
        self.seq = 0          # номер запису в календарі подій

    @property
    def name(self) -> str:
        qs = self.qs
        return qs.name if len(qs.channels) == 1 and not qs.unlimited else f"{qs.name}.{self.index + 1}"


# категорії часу каналу для статистики
CATS = ("free", "busy_h", "busy", "post_h", "post", "blocked")


class QS:
    """СМО з m ідентичних пристроїв без черги.

    service(запит, h) – час обслуговування; release(запит, h) – затримка звільнення пристрою
    після виходу запиту; h – тривалість захоплення або вивільнення, згенерована в момент
    переходу деталі між місцем і роботом (вона зайнята і місцем, і роботом).
    """

    def __init__(self, model: "Model", name: str, m: int | None,
                 service: Callable, release: Callable | None = None,
                 on_done: Callable | None = None, on_free: Callable | None = None):
        self.model = model
        self.name = name
        self.unlimited = m is None
        self.channels: list[Channel] = [] if m is None else [Channel(self, j) for j in range(m)]
        self._spare: list[Channel] = []
        self.service = service
        self.release = release or (lambda req, h: 0.0)
        self.on_done = on_done
        self.on_free = on_free
        self.route: Route | None = None
        self.n = [len(self.channels), 0, 0]   # кількість каналів у станах 0, 1, 2
        self.requests = 0                     # кількість запитів у СМО
        self.reset_stats()

    # --- стан
    def set_state(self, ch: Channel, K: int, t: float) -> None:
        self.n[ch.K] -= 1
        self.n[K] += 1
        ch.K = K
        ch.t_from = t

    def free_channel(self) -> Channel | None:
        if self.unlimited:
            if self._spare:
                return self._spare.pop()
            ch = Channel(self, len(self.channels))
            self.channels.append(ch)
            self.n[FREE] += 1
            return ch
        return next((ch for ch in self.channels if ch.K == FREE), None)

    def occupied(self) -> int:
        return self.n[BUSY] + self.n[BLOCKED]

    # --- надходження запиту в пристрій
    def accept(self, req, t: float, h: float = 0.0, ch: Channel | None = None) -> Channel:
        ch = ch or self.free_channel()
        ch.request = req
        self.requests += 1
        self.set_state(ch, BUSY, t)
        d = self.service(req, h)
        ch.t_split = t + h
        if d > 0:
            self.model.schedule(ch, t + d)
            if isinstance(req, Part):
                self.model.log(t, ch.name, f"{req}: обслуговування до {t + d:.3f}")
        else:                              # нульова затримка: запит одразу намагається вийти
            ch.tnext = t
            self.end_of_service(ch, t)
        return ch

    # --- подія «завершення обслуговування в каналі»
    def end_of_service(self, ch: Channel, t: float) -> None:
        ch.tnext = INF
        if ch.request is None:             # кінець затримки звільнення: пристрій вільний
            self._vacated(ch, t, delayed=True)
            return
        if self.on_done:
            self.on_done(ch.request, t)
        route = self.route
        if route.closed():                 # B(S, t) = 1: запит лишається в пристрої
            self.set_state(ch, BLOCKED, t)
            route.waiting.append(ch)
            if isinstance(ch.request, Part):
                self.model.log(t, ch.name, f"{ch.request}: маршрут {route.name} заблоковано ({route.label})")
        else:
            route.transfer(ch, t)

    def vacate(self, ch: Channel, t: float, h: float) -> None:
        """Запит вийшов з пристрою: пристрій звільняється одразу або із затримкою."""
        req = ch.request
        ch.request = None
        self.requests -= 1
        delay = self.release(req, h)
        if delay > 0:
            self.set_state(ch, BUSY, t)
            ch.t_split = t + h
            self.model.schedule(ch, t + delay)
            self.model.log(t, ch.name, f"затримка звільнення до {t + delay:.3f}")
        else:
            self._vacated(ch, t)

    def _vacated(self, ch: Channel, t: float, delayed: bool = False) -> None:
        if delayed and not self.on_free:
            self.model.log(t, ch.name, "пристрій вільний")
        self.set_state(ch, FREE, t)
        if self.unlimited:
            self._spare.append(ch)
        if self.on_free:
            self.on_free(ch, t)

    # --- статистика: тривалість станів кожного каналу на [t1; t2]
    def reset_stats(self) -> None:
        self.time = {ch.index: dict.fromkeys(CATS, 0.0) for ch in self.channels} if not self.unlimited else {}

    def update_stats(self, t1: float, t2: float) -> None:
        if self.unlimited:
            return
        for ch in self.channels:
            acc = self.time[ch.index]
            dt = t2 - t1
            if ch.K == FREE:
                acc["free"] += dt
            elif ch.K == BLOCKED:
                acc["blocked"] += dt
            else:
                h = max(0.0, min(t2, ch.t_split) - t1)     # частина інтервалу до кінця захоплення/вивільнення
                if ch.request is not None:
                    acc["busy_h"] += h
                    acc["busy"] += dt - h
                else:
                    acc["post_h"] += h
                    acc["post"] += dt - h

    def share(self, period: float, cats, channels=None) -> float:
        """Частка часу (на один канал), яку канали перебували в категоріях cats."""
        chs = channels if channels is not None else [ch.index for ch in self.channels]
        if period <= 0 or not chs:
            return math.nan
        return sum(self.time[j][c] for j in chs for c in cats) / (period * len(chs))

    def state_str(self) -> str:
        return f"{self.name}[{''.join(str(ch.K) for ch in self.channels)}]"


class Route:
    """Дуга мережі: запит переходить із СМО src у СМО dst, якщо умова блокування B(S, t) = 0.

    blocked – предикат B(S, t), однаковий для всіх пристроїв СМО src;
    opened – предикат, що залежить від пристрою (маршрут П -> Х, формула (2.5)): повертає
             заблокований пристрій src, для якого B(S, t) = 0, або None; перевіряється під час
             зняття блокувань, коли оброблено всі події моменту;
    handling – назва дії робота (захоплення, вивільнення), що супроводжує перехід;
    select – правило вибору пристрою в dst (за замовчуванням вільний з найменшим номером).
    """

    def __init__(self, model: "Model", src, dst, blocked: Callable[[], bool] | None = None,
                 label: str = "", handling: str = "", select: Callable | None = None,
                 on_transfer: Callable | None = None, opened: Callable[[], Channel | None] | None = None):
        self.model = model
        self.src, self.dst = src, dst
        self.blocked = blocked or (lambda: False)
        self.opened = opened
        self.label = label
        self.handling = handling      # «захоплення» або «вивільнення», якщо перехід їх супроводжує
        self.select = select
        self.on_transfer = on_transfer
        self.waiting: deque[Channel] = deque()   # заблоковані канали src у порядку блокування
        self.name = f"{src.name} -> {dst.name}"
        src.route = self

    def closed(self) -> bool:
        """B(S, t) = 1 у момент завершення обслуговування в пристрої src.

        Предикат, що залежить від пристрою, перевіряється пізніше, під час зняття блокувань.
        """
        return self.opened is not None or self.blocked()

    def transfer(self, ch: Channel, t: float) -> None:
        req = ch.request
        h = self.model.handling_time() if self.handling else 0.0
        dst_ch = self.select(req) if self.select else None
        if isinstance(req, Part) and self.dst is not self.model.exit:
            self.model.log(t, ch.name, f"{req}: перехід {self.name}" + (f", {self.handling} {h:.3f}" if h else ""))
        if self.on_transfer:
            self.on_transfer(req, ch, dst_ch, t)
        self.src.vacate(ch, t, h)
        self.dst.accept(req, t, h, dst_ch)

    def unblock(self, t: float) -> bool:
        """Перевести запити із заблокованих пристроїв, для яких B(S, t) = 0.

        Спільний предикат: пристрої виходять у порядку блокування, поки маршрут відкритий.
        Предикат, що залежить від пристрою: виходить пристрій, для якого маршрут відкритий.
        """
        moved = False
        while self.waiting:
            if self.opened is not None:
                ch = self.opened()
                if ch is None:
                    break
                self.waiting.remove(ch)
            elif self.blocked():
                break
            else:
                ch = self.waiting.popleft()
            if isinstance(ch.request, Part):
                self.model.log(t, ch.name, f"{ch.request}: маршрут {self.name} відкрито ({self.label} = 0)")
            self.transfer(ch, t)
            moved = True
        return moved


class Create:
    """Надходження деталей ззовні."""

    def __init__(self, model: "Model", name: str, dist, stream):
        self.model = model
        self.name = name
        self.dist = dist
        self.stream = stream
        self.tnext = dist.sample(stream)
        self.created = 0
        self.route: Route | None = None

    def arrival(self, t: float) -> None:
        self.created += 1
        part = Part(id=self.created, t_arrival=t)
        self.model.log(t, self.name, f"надходження деталі #{part.id}")
        self.route.dst.accept(part, t)
        self.tnext = t + self.dist.sample(self.stream)


class Exit:
    """Вихід з мережі: деталь на складі."""

    name = "вихід"

    def __init__(self, model: "Model"):
        self.model = model

    def accept(self, part: Part, t: float, h: float = 0.0, ch=None) -> None:
        self.model.record_completion(part, t)
