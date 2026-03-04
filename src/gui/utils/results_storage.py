import json
from pathlib import Path

from .chart_data import ChartStore, MethodRun

RESULTS_FILE = Path("results.json")


def save_results(store: ChartStore) -> None:
    """Сохранение результатов в файл"""
    data = [
        {
            "engine": r.engine,
            "db_type": r.db_type,
            "method": r.method,
            "experiment_config": r.experiment_config,
            "method_config": r.method_config,
            "metrics": r.metrics,
        }
        for r in store
    ]
    RESULTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_results() -> ChartStore:
    """Загрузка результатов из файла"""
    if not RESULTS_FILE.exists():
        return []

    data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))

    return [
        MethodRun(
            engine=r["engine"],
            db_type=r["db_type"],
            method=r["method"],
            experiment_config=r["experiment_config"],
            method_config=r["method_config"],
            metrics=r["metrics"],
        )
        for r in data
    ]


def clear_results_file() -> None:
    """Удаление выполненных тестов из файла"""
    if RESULTS_FILE.exists():
        RESULTS_FILE.unlink()
