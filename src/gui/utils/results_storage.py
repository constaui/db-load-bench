"""
Чтение, запись и выбор файла результатов (`results.json`).

Путь к файлу хранится в QSettings и поэтому переживает перезапуск приложения.
Если настройка не задана — используется `results.json` в корне проекта (как
было исторически).
"""

import json
from pathlib import Path

from PyQt6.QtCore import QSettings

from .chart_data import ChartStore, MethodRun


_DEFAULT_PATH = Path("results.json").resolve()
_SETTINGS_ORG = "db-load-bench"
_SETTINGS_APP = "db-load-bench"
_SETTINGS_KEY = "results_path"


def _settings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


def default_path() -> Path:
    """Путь по умолчанию (корень проекта)."""
    return _DEFAULT_PATH


def get_results_path() -> Path:
    """Текущий активный путь к results.json (из QSettings или дефолт)."""
    val = _settings().value(_SETTINGS_KEY)
    if val:
        return Path(str(val))
    return _DEFAULT_PATH


def set_results_path(path: Path | str) -> None:
    """Сохраняет новый путь в QSettings; используется при последующих save/load."""
    _settings().setValue(_SETTINGS_KEY, str(Path(path).expanduser().resolve()))


def reset_results_path() -> None:
    """Возвращает путь к значению по умолчанию (корень проекта)."""
    _settings().remove(_SETTINGS_KEY)


def is_default_path() -> bool:
    return get_results_path() == _DEFAULT_PATH


def save_results(store: ChartStore) -> None:
    """Сохраняет результаты в текущий активный файл."""
    path = get_results_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.to_dict() for r in store]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_results() -> ChartStore:
    """Загружает результаты из текущего активного файла (или пустой список)."""
    return load_results_from(get_results_path())


def load_results_from(path: Path) -> ChartStore:
    """Загружает результаты из указанного пути. Не меняет активный путь."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    data = json.loads(text)
    return [MethodRun.from_dict(r) for r in data]


def clear_results_file() -> None:
    """Удаляет файл по текущему активному пути."""
    path = get_results_path()
    if path.exists():
        path.unlink()
