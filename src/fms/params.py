"""Вхідні змінні та параметри моделі (усі часи — у секундах)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .rng import Dist, exp, norm, unif

# Стратегії закріплення роботів
DEDICATED = "dedicated"  # 1) по одному роботу на кожний шлях переміщення
NEAREST = "nearest"      # 2) будь-який робот на будь-якому шляху, займається найближчий

# Місце на верстаті зайняте від початку вивільнення деталі до кінця її захоплення наступним
# роботом. Якщо вільного місця немає, робот чекає біля верстата, тримаючи деталь.

# Розташування пунктів на лінії A – M1 – M2 – W (сек ходу робота від пункту прибуття).
# Відстань між пунктами = різниця координат: A–M1 = 6, M1–M2 = 7, M2–W = 5,
# A–M2 = 13, M1–W = 12, A–W = 18.
DEFAULT_POSITIONS = {"A": 0.0, "M1": 6.0, "M2": 13.0, "W": 18.0}


@dataclass(frozen=True)
class Params:
    # вхідні змінні
    arrival: Dist = exp(40.0)        # інтервал надходження деталей
    m1_time: Dist = norm(60.0, 10.0)  # час обробки на першому верстаті
    m2_time: Dist = exp(100.0)        # час обробки на другому верстаті
    handling: Dist = unif(8.0, 1.0)   # час захоплення або вивільнення деталі роботом

    # параметри
    m1_capacity: int = 3
    m2_capacity: int = 3
    n_robots: int = 3
    positions: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_POSITIONS))

    # варіант організації системи
    strategy: str = DEDICATED
    # варіант 1: маршрут кожного робота (за замовчуванням роботи 1, 2, 3 – маршрути 1, 2, 3);
    # якщо роботів більше трьох, тут задається, на якому маршруті працює кожен
    dedicated_routes: tuple[int, ...] | None = None

    def distance(self, a: str, b: str) -> float:
        return abs(self.positions[a] - self.positions[b])

    def with_(self, **changes) -> "Params":
        return replace(self, **changes)

    def scaled_travel(self, factor: float) -> "Params":
        return replace(self, positions={k: v * factor for k, v in self.positions.items()})

    def robot_routes(self) -> list[tuple[int, ...]]:
        """Маршрути, які може обслуговувати кожен робот."""
        if self.strategy == NEAREST:
            return [(1, 2, 3)] * self.n_robots
        if self.strategy == DEDICATED:
            routes = self.dedicated_routes or tuple(k % 3 + 1 for k in range(self.n_robots))
            if len(routes) != self.n_robots or set(routes) != {1, 2, 3}:
                raise ValueError(f"dedicated_routes має покривати маршрути 1–3 для кожного з "
                                 f"{self.n_robots} роботів: {routes}")
            return [(r,) for r in routes]
        raise ValueError(f"Невідома стратегія: {self.strategy}")

    def describe(self) -> str:
        pos = ", ".join(f"{k}={v:g}" for k, v in self.positions.items())
        return (
            f"strategy={self.strategy}, "
            f"arrival={self.arrival}, M1={self.m1_time}, M2={self.m2_time}, "
            f"handling={self.handling}, cap=({self.m1_capacity},{self.m2_capacity}), "
            f"robots={self.n_robots}"
            + (f", routes={self.dedicated_routes}" if self.dedicated_routes else "")
            + f", positions[{pos}]"
        )
