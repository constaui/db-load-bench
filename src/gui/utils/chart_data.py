from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Optional

from orchestrator.protocol import MethodRun


ChartStore = list[MethodRun]

GroupKey = tuple[str, str, str, Optional[int]]


def _group_key(run: MethodRun) -> GroupKey:
    return (
        run.engine,
        run.db_type,
        run.method,
        run.batch_size,
    )


def _average_run(runs: list[MethodRun]) -> MethodRun:
    """Усредняет метрики результатов с одинаковым GroupKey"""
    base = runs[0]
    n = len(runs)
    return MethodRun(
        engine=base.engine,
        db_type=base.db_type,
        method=base.method,
        experiment_config=base.experiment_config,
        method_config=base.method_config,
        metrics={
            "elapsed": round(sum(r.elapsed for r in runs) / n, 6),
            "rps": round(sum(r.rps for r in runs) / n, 1),
        },
    )


def get_aggregated(store: ChartStore) -> dict[GroupKey, MethodRun]:
    """
    Группирует результаты по (engine, db_type, method, batch_size)
    и возвращает усреднённый MethodRun для каждой группы
    """
    groups: dict[GroupKey, list[MethodRun]] = {}
    for run in store:
        groups.setdefault(_group_key(run), []).append(run)

    return {key: _average_run(runs) for key, runs in groups.items()}


def group_runs(store: ChartStore) -> dict[GroupKey, list[MethodRun]]:
    """Группирует все запуски (без агрегации) по GroupKey"""
    groups: dict[GroupKey, list[MethodRun]] = {}
    for run in store:
        groups.setdefault(_group_key(run), []).append(run)
    return groups


def filter_runs(
    store: ChartStore,
    engines: Iterable[str] | None = None,
    db_types: Iterable[str] | None = None,
    methods: Iterable[str] | None = None,
) -> ChartStore:
    """
    Мульти-фильтр: для каждой оси None = «без фильтра», иначе оставить
    только запуски, чьё значение входит в переданный набор.
    Пустое (но не None) множество отфильтрует всё.
    """
    e_set = set(engines) if engines is not None else None
    d_set = set(db_types) if db_types is not None else None
    m_set = set(methods) if methods is not None else None

    return [
        r
        for r in store
        if (e_set is None or r.engine in e_set)
        and (d_set is None or r.db_type in d_set)
        and (m_set is None or r.method in m_set)
    ]


def add_run(store: ChartStore, run: MethodRun) -> None:
    store.append(run)


def series_label(run: MethodRun) -> str:
    """
    Формирование подписи для диаграмм
    """
    base = f"{run.engine} / {run.db_type} / {run.method}"
    if run.method == "bulk_insert" and run.batch_size is not None:
        return f"{base} (batch={run.batch_size})"
    return base


def _percentile(values: list[float], p: float) -> float:
    """Линейная интерполяция перцентиля, p в [0, 1]."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = p * (len(s) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def stats_for(values: list[float]) -> dict[str, float]:
    """Статистические сводки по списку значений (mean, median, std, min, max, q1, q3, n)."""
    n = len(values)
    if n == 0:
        return {
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "n": 0,
        }
    mean = sum(values) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    return {
        "mean": mean,
        "median": _percentile(values, 0.5),
        "std": std,
        "min": min(values),
        "max": max(values),
        "q1": _percentile(values, 0.25),
        "q3": _percentile(values, 0.75),
        "n": n,
    }
