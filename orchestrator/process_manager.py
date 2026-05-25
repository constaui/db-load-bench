import json
import os
import subprocess
import sys
from pathlib import Path

from orchestrator.protocol import MethodRun
from orchestrator.resource_monitor import ResourceMonitor


class RunCancelled(Exception):
    """Прогон отменён пользователем (Stop). Не считается ошибкой."""


ENGINES = {
    "Python": [sys.executable, str(Path("engines/python/main.py"))],
    "Go": [str(Path("engines/go/insert_engine"))],
    "Java": ["java", "-jar", str(Path("engines/java/target/insert_engine.jar"))],
    "Rust": [str(Path("engines/rust/target/release/insert_engine"))],
}


# Инструкции по сборке — попадают в сообщение об ошибке, если бинарник не найден.
BUILD_HINTS = {
    "Go":   "cd engines/go && go build -o insert_engine",
    "Java": "cd engines/java && mvn -q package -DskipTests",
    "Rust": "cd engines/rust && cargo build --release",
}


def _resolve_engine_cmd(engine: str, base_cmd: list[str]) -> list[str]:
    """Резолвит команду запуска движка.

    Если первый аргумент — путь к файлу:
      - на Windows ПРИОРИТЕТ у `.exe`-варианта (защита от случая, когда
        в репозитории лежит чужой бинарь без расширения, скажем,
        macOS/Linux ELF, который Windows не запустит);
      - если ничего не подходит — FileNotFoundError с подсказкой и списком
        проверенных путей.

    Если первый аргумент — команда из PATH (`java`, `python`), не трогает её.
    """
    if not base_cmd:
        raise ValueError(f"Пустая команда для движка '{engine}'")

    first = base_cmd[0]
    p = Path(first)

    # Команда из PATH (без директории): пусть ОС резолвит сама.
    if not p.parent or str(p.parent) in ("", "."):
        return base_cmd

    # Какие пути проверять — в порядке приоритета:
    #   На Windows: insert_engine.exe → insert_engine
    #   На *nix:    insert_engine
    candidates: list[Path] = []
    if os.name == "nt" and p.suffix == "":
        candidates.append(p.with_suffix(".exe"))
    candidates.append(p)

    for cand in candidates:
        if cand.exists():
            return [str(cand)] + base_cmd[1:]

    # Ничего не нашли — диагностическое сообщение со списком путей.
    tried = "\n".join(f"  - {c.resolve() if c.parent.exists() else c}" for c in candidates)
    msg = (
        f"Бинарник движка '{engine}' не найден.\n"
        f"Проверены пути:\n{tried}"
    )
    hint = BUILD_HINTS.get(engine)
    if hint:
        msg += f"\nСоберите движок командой:\n  {hint}"
    raise FileNotFoundError(msg)


class ProcessManager:

    def __init__(
        self,
        engine: str,
        conn_params: dict,
        sampling_interval_s: float = 0.05,
    ):
        if engine not in ENGINES:
            raise ValueError(f"Unknown engine: {engine}")
        self.engine = engine
        self.conn_params = conn_params
        self.sampling_interval_s = sampling_interval_s
        self._current_proc: subprocess.Popen | None = None
        self._terminated_by_user: bool = False

    def terminate_current(self) -> None:
        """Прерывает текущий subprocess (используется из UI Stop)."""
        proc = self._current_proc
        if proc is None:
            return
        self._terminated_by_user = True
        try:
            proc.kill()
        except OSError:
            pass

    def run(
        self, method: str, csv_file: str, table_name: str, batch_size: int = 1000
    ) -> MethodRun:
        cmd = self._build_cmd(method, csv_file, table_name, batch_size)
        self._terminated_by_user = False

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._current_proc = proc

        monitor = ResourceMonitor(
            pid=proc.pid, interval_s=self.sampling_interval_s
        ).start()

        try:
            stdout, stderr = proc.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            monitor.stop()
            raise RuntimeError(f"[{self.engine}] timeout after 600s")
        finally:
            resource_metrics = monitor.stop()
            self._current_proc = None

        if self._terminated_by_user:
            raise RunCancelled(f"[{self.engine}] прервано пользователем")

        if proc.returncode != 0:
            raise RuntimeError(
                f"[{self.engine}] process failed:\n{stderr.strip()}"
            )

        try:
            result = MethodRun.from_dict(json.loads(stdout))
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(
                f"[{self.engine}] invalid output: {stdout!r}"
            ) from e

        # Метрики окружения замеряются оркестратором, движок про них не знает.
        result.resource_metrics = resource_metrics
        return result

    def _build_cmd(
        self, method: str, csv_file: str, table_name: str, batch_size: int
    ) -> list[str]:
        # Резолвим путь к бинарнику движка (с подсказкой про сборку
        # вместо невнятного «WinError 2» от subprocess).
        base = _resolve_engine_cmd(self.engine, ENGINES[self.engine])
        cmd = base + [
            "--method",
            method,
            "--csv",
            csv_file,
            "--table",
            table_name,
            "--db-type",
            self.conn_params["db_type"],
            "--host",
            self.conn_params["host"],
            "--port",
            str(self.conn_params["port"]),
            "--user",
            self.conn_params["user"],
            "--password",
            self.conn_params["password"],
            "--database",
            self.conn_params["database"],
        ]
        if method == "bulk_insert":
            cmd += ["--batch-size", str(batch_size)]
        return cmd
