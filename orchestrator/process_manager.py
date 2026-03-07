import json
import subprocess
import sys
from pathlib import Path

from orchestrator.protocol import MethodRun


ENGINES = {
    "Python": [sys.executable, str(Path("engines/python/insert_engine.py"))],
}


class ProcessManager:

    def __init__(self, engine: str, conn_params: dict):
        if engine not in ENGINES:
            raise ValueError(f"Unknown engine: {engine}")
        self.engine = engine
        self.conn_params = conn_params

    def run(
        self, method: str, csv_file: str, table_name: str, batch_size: int = 1000
    ) -> MethodRun:
        cmd = self._build_cmd(method, csv_file, table_name, batch_size)

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if proc.returncode != 0:
            raise RuntimeError(
                f"[{self.engine}] process failed:\n{proc.stderr.strip()}"
            )

        try:
            result = MethodRun.from_dict(json.loads(proc.stdout))
            return result
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(
                f"[{self.engine}] invalid output: {proc.stdout!r}"
            ) from e

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
