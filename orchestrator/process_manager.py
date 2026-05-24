import json
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
        cmd = ENGINES[self.engine] + [
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
