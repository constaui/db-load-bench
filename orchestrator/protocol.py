from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InsertCommand:
    method: str
    csv_file: str
    table_name: str
    db_type: str
    host: str
    port: int
    user: str
    password: str
    database: str
    batch_size: int = 1000

    def to_args(self) -> list[str]:
        return [
            "--method",
            self.method,
            "--csv",
            self.csv_file,
            "--table",
            self.table_name,
            "--db-type",
            self.db_type,
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--user",
            self.user,
            "--password",
            self.password,
            "--database",
            self.database,
            "--batch-size",
            str(self.batch_size),
        ]


@dataclass
class MethodRun:
    """Класс для сохраненного результата теста"""

    engine: str
    db_type: str
    method: str

    experiment_config: dict[str, int] = field(default_factory=dict)

    method_config: dict[str, Optional[int]] = field(default_factory=dict)

    db_config: dict[str, bool] = field(default_factory=dict)

    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return self.experiment_config.get("rows", 0)

    @property
    def elapsed(self) -> float:
        return self.metrics.get("elapsed", 0.0)

    @property
    def rps(self) -> float:
        return self.metrics.get("rps", 0.0)

    @property
    def batch_size(self) -> Optional[int]:
        return self.method_config.get("batch_size")

    @staticmethod
    def from_dict(data: dict) -> "MethodRun":
        """Десериализует JSON от движка."""
        required = {
            "engine",
            "db_type",
            "method",
            "experiment_config",
            "method_config",
            "metrics",
        }
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Отсутствуют поля: {missing}")

        return MethodRun(
            engine=data["engine"],
            db_type=data["db_type"],
            method=data["method"],
            experiment_config=data["experiment_config"],
            method_config=data["method_config"],
            metrics=data["metrics"],
        )

    def to_dict(self) -> dict:
        """Сериализует в dict для stdout и хранения."""
        return {
            "engine": self.engine,
            "db_type": self.db_type,
            "method": self.method,
            "experiment_config": self.experiment_config,
            "method_config": self.method_config,
            "metrics": self.metrics,
        }
