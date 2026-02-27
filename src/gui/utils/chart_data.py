from dataclasses import dataclass


@dataclass
class MethodRun:
    rows: int
    elapsed: float
    rps: float
    batch_size: int | None = None  # None для default_insert и file_insert


ChartStore = dict[str, dict[str, list[MethodRun]]]


def add_run(
    store: ChartStore,
    db_type: str,
    method: str,
    rows: int,
    elapsed: float,
    batch_size: int | None = None,
) -> None:
    rps = round(rows / elapsed, 1) if elapsed > 0 else 0
    run = MethodRun(rows=rows, elapsed=elapsed, rps=rps, batch_size=batch_size)
    store.setdefault(db_type, {}).setdefault(method, []).append(run)


def get_latest(store: ChartStore) -> dict[str, dict[str, MethodRun]]:
    return {
        db_type: {method: runs[-1] for method, runs in methods.items() if runs}
        for db_type, methods in store.items()
    }


def series_label(db_type: str, method: str, run: MethodRun) -> str:
    """Формирует подпись линии/бара с учётом batch_size."""
    if method == "bulk_insert" and run.batch_size is not None:
        return f"{db_type} / {method} (batch={run.batch_size})"
    return f"{db_type} / {method}"
