"""
Снимок окружения для воспроизводимости результатов.

Делается один раз при старте сессии — добавляется к каждому MethodRun,
чтобы спустя время можно было сказать «на какой машине / какой версии БД
получены эти цифры». Все вызовы безопасны: ошибки не пробрасываются,
а ставят пустое значение в соответствующее поле.
"""

from __future__ import annotations

import platform
import socket
import subprocess
from pathlib import Path
from typing import Optional

import psutil


def _safe(fn, default=""):
    try:
        return fn()
    except Exception:
        return default


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).resolve().parent.parent,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def capture_environment(db_version: Optional[str] = None) -> dict:
    """Снимок хоста + опционально версия СУБД, полученная вызывающим кодом."""
    return {
        "hostname": _safe(socket.gethostname, ""),
        "platform": _safe(platform.platform, ""),
        "system": _safe(platform.system, ""),
        "release": _safe(platform.release, ""),
        "python": _safe(platform.python_version, ""),
        "cpu_brand": _safe(platform.processor, ""),
        "cpu_count_logical": _safe(lambda: psutil.cpu_count(logical=True), 0),
        "cpu_count_physical": _safe(lambda: psutil.cpu_count(logical=False), 0),
        "ram_total_bytes": _safe(lambda: psutil.virtual_memory().total, 0),
        "git_commit": _git_commit(),
        "db_version": db_version or "",
    }
