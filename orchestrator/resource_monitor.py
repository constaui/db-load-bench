"""
Семплирующий монитор ресурсов поверх psutil.

Запускается в отдельном треде с момента старта дочернего процесса (по PID)
и собирает CPU%, RSS, диск-I/O, число тредов и ctx-switches. По остановке
возвращает агрегированный словарь, готовый к подмешиванию в MethodRun.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import psutil


def _safe(call, default=None):
    """Выполняет вызов psutil, перехватывая «процесс умер / нет прав»."""
    try:
        return call()
    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        psutil.ZombieProcess,
        AttributeError,
        NotImplementedError,
        OSError,
    ):
        return default


class ResourceMonitor:
    """
    Снимает метрики процесса (и его дочерних) с заданным интервалом.

    Жизненный цикл:
        m = ResourceMonitor(pid).start()
        ... ждём пока subprocess завершится ...
        metrics = m.stop()
    """

    def __init__(self, pid: int, interval_s: float = 0.05):
        self.pid = pid
        self.interval_s = interval_s

        self._stop_evt = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

        self._cpu_samples: list[float] = []
        self._rss_samples: list[int] = []
        self._max_threads: int = 0
        self._n_samples: int = 0

        self._final_cpu_times: Optional[tuple[float, float]] = None
        self._final_io: Optional[tuple[int, int, int, int]] = None
        self._final_ctx: Optional[tuple[int, int]] = None

        self._proc: Optional[psutil.Process] = None
        self._primed_pids: set[int] = set()

    def start(self) -> "ResourceMonitor":
        try:
            self._proc = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            self._proc = None
            return self

        self._prime(self._proc)
        self._thread.start()
        return self

    def stop(self) -> dict[str, float]:
        self._stop_evt.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        return self._collect()

    def _prime(self, p: psutil.Process) -> None:
        """Первый вызов cpu_percent у psutil всегда возвращает 0 —
        прогреваем счётчик, чтобы следующие семплы были валидными."""
        if p.pid in self._primed_pids:
            return
        _safe(lambda: p.cpu_percent(None))
        self._primed_pids.add(p.pid)

    def _run(self) -> None:
        if self._proc is None:
            return

        proc = self._proc
        while not self._stop_evt.is_set():
            if not _safe(proc.is_running, False):
                break

            kids = _safe(lambda: proc.children(recursive=True), []) or []
            tree = [proc, *kids]

            for p in tree:
                self._prime(p)

            cpu = 0.0
            rss = 0
            threads = 0
            alive = 0
            for p in tree:
                if not _safe(p.is_running, False):
                    continue
                alive += 1
                cpu += _safe(lambda p=p: p.cpu_percent(None), 0.0) or 0.0
                mem = _safe(lambda p=p: p.memory_info(), None)
                if mem is not None:
                    rss += mem.rss
                threads += _safe(lambda p=p: p.num_threads(), 0) or 0

            if alive == 0:
                break

            self._cpu_samples.append(cpu)
            self._rss_samples.append(rss)
            self._max_threads = max(self._max_threads, threads)
            self._n_samples += 1

            cpu_times = _safe(lambda: proc.cpu_times(), None)
            if cpu_times is not None:
                self._final_cpu_times = (cpu_times.user, cpu_times.system)

            io = _safe(lambda: proc.io_counters(), None)
            if io is not None:
                self._final_io = (
                    io.read_bytes,
                    io.write_bytes,
                    io.read_count,
                    io.write_count,
                )

            ctx = _safe(lambda: proc.num_ctx_switches(), None)
            if ctx is not None:
                self._final_ctx = (ctx.voluntary, ctx.involuntary)

            self._stop_evt.wait(self.interval_s)

    def _collect(self) -> dict[str, float]:
        cpu_avg = (
            sum(self._cpu_samples) / len(self._cpu_samples)
            if self._cpu_samples
            else 0.0
        )
        cpu_peak = max(self._cpu_samples) if self._cpu_samples else 0.0
        rss_avg = (
            sum(self._rss_samples) / len(self._rss_samples)
            if self._rss_samples
            else 0
        )
        rss_peak = max(self._rss_samples) if self._rss_samples else 0

        cpu_user, cpu_system = self._final_cpu_times or (0.0, 0.0)
        read_b, write_b, read_n, write_n = self._final_io or (0, 0, 0, 0)
        ctx_vol, ctx_invol = self._final_ctx or (0, 0)

        return {
            "cpu_percent_avg": round(cpu_avg, 2),
            "cpu_percent_peak": round(cpu_peak, 2),
            "cpu_time_user_s": round(cpu_user, 6),
            "cpu_time_system_s": round(cpu_system, 6),
            "cpu_time_total_s": round(cpu_user + cpu_system, 6),
            "rss_avg_bytes": int(rss_avg),
            "rss_peak_bytes": int(rss_peak),
            "read_bytes": int(read_b),
            "write_bytes": int(write_b),
            "read_count": int(read_n),
            "write_count": int(write_n),
            "max_threads": int(self._max_threads),
            "ctx_switches_voluntary": int(ctx_vol),
            "ctx_switches_involuntary": int(ctx_invol),
            "samples": int(self._n_samples),
            "sampling_interval_s": round(self.interval_s, 4),
            "io_available": 1 if self._final_io is not None else 0,
        }
