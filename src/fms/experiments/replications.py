"""Визначення кількості повторних прогонів.

За нерівністю Чебишова (3.4): p = σ² / (ε²(1 − β)); при β = 0.95 p = 20(σ/ε)².
Для порівняння наводиться також оцінка за ЦГТ: p = (t_β·σ/ε)², t_0.95 = 1.96.
σ оцінюється за пілотною серією прогонів.
"""

from __future__ import annotations

import math

from ..params import Params
from .common import replicate, summarize

RESPONSES = ("throughput_per_hour", "sojourn_mean", "buffer_max", "M2_occupied", "robots_util_mean")


def run(params: Params, pilot: int, t_end: float, t_warmup: float, eps_rel: float,
        beta: float, jobs: int) -> list[dict]:
    results, _ = replicate(params, pilot, t_end, t_warmup, jobs=jobs)
    rows = []
    for resp in RESPONSES:
        s = summarize([r[resp] for r in results], beta)
        eps = eps_rel * abs(s["mean"])
        sigma = s["std"]
        p_cheb = math.ceil(sigma ** 2 / (eps ** 2 * (1 - beta))) if eps > 0 else math.nan
        p_clt = math.ceil((1.959964 * sigma / eps) ** 2) if eps > 0 else math.nan
        rows.append({
            "strategy": params.strategy, "arrival_mean": params.arrival.mean, "response": resp,
            "pilot_runs": pilot, "mean": s["mean"], "std": sigma, "eps": eps,
            "p_chebyshev": p_cheb, "p_clt": p_clt,
        })
    return rows
