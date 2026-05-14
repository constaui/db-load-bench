"""
Реестр «источников метрики» для срезов в GUI.

Каждый источник умеет:
- извлечь скалярное значение из MethodRun (или None, если метрика не замерена);
- отформатировать значение для ячейки таблицы / тултипа;
- сообщить, лучше ли когда значение меньше (для инверсии цветовой шкалы
  и интерпретации ускорения).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from orchestrator.protocol import MethodRun


@dataclass(frozen=True)
class MetricSource:
    key: str
    label: str
    extract: Callable[[MethodRun], Optional[float]]
    format: Callable[[float], str]
    lower_is_better: bool = False
    unit: str = ""


def _rps(r: MethodRun) -> Optional[float]:
    return r.rps if r.rps > 0 else None


def _elapsed(r: MethodRun) -> Optional[float]:
    return r.elapsed if r.elapsed > 0 else None


def _resource_field(field: str) -> Callable[[MethodRun], Optional[float]]:
    def f(r: MethodRun) -> Optional[float]:
        rm = r.resource_metrics
        if not rm:
            return None
        v = rm.get(field)
        if v is None:
            return None
        return float(v)

    return f


def _ctx_total(r: MethodRun) -> Optional[float]:
    rm = r.resource_metrics
    if not rm:
        return None
    return float(
        rm.get("ctx_switches_voluntary", 0) + rm.get("ctx_switches_involuntary", 0)
    )


def _fmt_int(v: float) -> str:
    return f"{v:,.0f}"


def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"


def _fmt_sec(v: float) -> str:
    return f"{v:.3f} с"


def _fmt_mb(v: float) -> str:
    return f"{v:.1f} МБ"


SOURCES: list[MetricSource] = [
    MetricSource(
        key="rps",
        label="RPS",
        extract=_rps,
        format=_fmt_int,
        lower_is_better=False,
        unit="строк/с",
    ),
    MetricSource(
        key="elapsed",
        label="Время вставки",
        extract=_elapsed,
        format=_fmt_sec,
        lower_is_better=True,
        unit="с",
    ),
    MetricSource(
        key="cpu_percent_avg",
        label="CPU % (avg)",
        extract=_resource_field("cpu_percent_avg"),
        format=_fmt_pct,
        lower_is_better=True,
        unit="% ядра",
    ),
    MetricSource(
        key="cpu_percent_peak",
        label="CPU % (peak)",
        extract=_resource_field("cpu_percent_peak"),
        format=_fmt_pct,
        lower_is_better=True,
        unit="% ядра",
    ),
    MetricSource(
        key="cpu_time_total_s",
        label="CPU time (sum)",
        extract=_resource_field("cpu_time_total_s"),
        format=_fmt_sec,
        lower_is_better=True,
        unit="с",
    ),
    MetricSource(
        key="rss_peak_mb",
        label="RSS peak",
        extract=lambda r: (
            None
            if not r.resource_metrics
            else float(r.resource_metrics.get("rss_peak_bytes", 0)) / 1024 / 1024
        ),
        format=_fmt_mb,
        lower_is_better=True,
        unit="МБ",
    ),
    MetricSource(
        key="rss_avg_mb",
        label="RSS avg",
        extract=lambda r: (
            None
            if not r.resource_metrics
            else float(r.resource_metrics.get("rss_avg_bytes", 0)) / 1024 / 1024
        ),
        format=_fmt_mb,
        lower_is_better=True,
        unit="МБ",
    ),
    MetricSource(
        key="write_mb",
        label="Disk write",
        extract=lambda r: (
            None
            if not r.resource_metrics
            else float(r.resource_metrics.get("write_bytes", 0)) / 1024 / 1024
        ),
        format=_fmt_mb,
        lower_is_better=True,
        unit="МБ",
    ),
    MetricSource(
        key="read_mb",
        label="Disk read",
        extract=lambda r: (
            None
            if not r.resource_metrics
            else float(r.resource_metrics.get("read_bytes", 0)) / 1024 / 1024
        ),
        format=_fmt_mb,
        lower_is_better=True,
        unit="МБ",
    ),
    MetricSource(
        key="max_threads",
        label="Threads (max)",
        extract=_resource_field("max_threads"),
        format=_fmt_int,
        lower_is_better=False,
        unit="шт",
    ),
    MetricSource(
        key="ctx_switches",
        label="Ctx switches",
        extract=_ctx_total,
        format=_fmt_int,
        lower_is_better=True,
        unit="шт",
    ),
]


SOURCES_BY_KEY: dict[str, MetricSource] = {s.key: s for s in SOURCES}


def get_source(key: str) -> MetricSource:
    return SOURCES_BY_KEY.get(key, SOURCES[0])
