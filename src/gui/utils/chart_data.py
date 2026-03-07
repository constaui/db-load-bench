from typing import Optional

from orchestrator.protocol import MethodRun


ChartStore = list[MethodRun]

GroupKey = tuple[str, str, str, Optional[int]]


def _group_key(run: MethodRun) -> GroupKey:
    return (run.engine, run.db_type, run.method, run.batch_size)


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


def filter_runs(
    store: ChartStore,
    engine: str | None = None,
    db_type: str | None = None,
    method: str | None = None,
) -> ChartStore:
    """
    Фильтрация результатов
    """
    return [
        r
        for r in store
        if (engine is None or r.engine == engine)
        and (db_type is None or r.db_type == db_type)
        and (method is None or r.method == method)
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
