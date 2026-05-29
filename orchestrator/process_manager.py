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
# На Windows важно указать .exe явно: некоторые версии Go не добавляют его сами.
BUILD_HINTS_POSIX = {
    "Go":   "cd engines/go && go build -o insert_engine",
    "Java": "cd engines/java && mvn -q package -DskipTests",
    "Rust": "cd engines/rust && cargo build --release",
}

BUILD_HINTS_WINDOWS = {
    "Go":   "cd engines\\go && go build -o insert_engine.exe",
    "Java": "cd engines\\java && mvn -q package -DskipTests",
    "Rust": "cd engines\\rust && cargo build --release",
}


def _build_hint(engine: str) -> str:
    table = BUILD_HINTS_WINDOWS if os.name == "nt" else BUILD_HINTS_POSIX
    return table.get(engine, "")


# Расширения исполняемых файлов на Windows. PE-loader запускает только их.
WIN_EXEC_EXTENSIONS = {".exe", ".bat", ".cmd", ".com"}


def _is_executable_on_this_os(path: Path) -> bool:
    """На Windows исполняемым считается файл с .exe/.bat/.cmd/.com.
    На *nix — любой существующий файл (биты исполняемости проверять
    не будем — это ответственность пользователя)."""
    if os.name == "nt":
        return path.suffix.lower() in WIN_EXEC_EXTENSIONS
    return True


def _resolve_engine_cmd(engine: str, base_cmd: list[str]) -> list[str]:
    """Резолвит команду запуска движка.

    Если первый аргумент — путь к файлу:
      - на Windows ПРИОРИТЕТ у `.exe`-варианта; файлы без исполняемого
        расширения отвергаются (Windows их не запустит);
      - если ничего не подходит — FileNotFoundError с диагностикой:
        что искалось, что было найдено, что нужно сделать.

    Если первый аргумент — команда из PATH (`java`, `python`), не трогает её.
    """
    if not base_cmd:
        raise ValueError(f"Пустая команда для движка '{engine}'")

    first = base_cmd[0]
    p = Path(first)

    # Команда из PATH (без директории): пусть ОС резолвит сама.
    if not p.parent or str(p.parent) in ("", "."):
        return base_cmd

    on_windows = os.name == "nt"

    # Пути-кандидаты в порядке приоритета:
    #   Windows: insert_engine.exe → insert_engine.bat → insert_engine.cmd → insert_engine
    #   POSIX:   insert_engine
    candidates: list[Path] = []
    if on_windows and p.suffix == "":
        for ext in (".exe", ".bat", ".cmd"):
            candidates.append(p.with_suffix(ext))
    candidates.append(p)

    for cand in candidates:
        if not cand.exists():
            continue
        if not _is_executable_on_this_os(cand):
            # На Windows файл без .exe (или подобного) запустить нельзя —
            # пропускаем, дальше упадём с понятной ошибкой.
            continue
        return [str(cand)] + base_cmd[1:]

    # Ничего не нашли. Строим диагностическое сообщение.
    tried_lines = []
    for cand in candidates:
        path_repr = cand.resolve() if cand.parent.exists() else cand
        if not cand.exists():
            tried_lines.append(f"  - {path_repr}  (нет)")
        elif not _is_executable_on_this_os(cand):
            tried_lines.append(
                f"  - {path_repr}  (есть, но Windows не запустит без .exe)"
            )
        else:
            # Сюда не должны попасть — такой бы уже прошёл проверку.
            tried_lines.append(f"  - {path_repr}  (?)")

    msg = (
        f"Бинарник движка '{engine}' не найден.\n"
        f"Проверены пути:\n" + "\n".join(tried_lines)
    )

    # Если на Windows есть файл без расширения — добавим явное объяснение.
    if on_windows and p.suffix == "" and p.exists():
        msg += (
            f"\n\nЗАМЕЧАНИЕ: файл '{p.name}' лежит на месте, но Windows не\n"
            f"может его исполнить без расширения .exe. Скорее всего, бинарь\n"
            f"был собран не на Windows, либо `go build` не добавил .exe.\n"
            f"Самый быстрый фикс — переименовать:\n"
            f"  ren {p} {p.name}.exe"
        )

    hint = _build_hint(engine)
    if hint:
        msg += f"\n\nИли пересобрать движок:\n  {hint}"

    raise FileNotFoundError(msg)


class ProcessManager:

    def __init__(
        self,
        engine: str,
        conn_params: dict,
        sampling_interval_s: float = 0.05,
        stderr_logger=None,  # Optional[Callable[[str], None]]
    ):
        if engine not in ENGINES:
            raise ValueError(f"Unknown engine: {engine}")
        self.engine = engine
        self.conn_params = conn_params
        self.sampling_interval_s = sampling_interval_s
        # Колбек получает каждую непустую строку из stderr движка. Нужен
        # чтобы диагностика (например, MySQL warnings после LOAD DATA)
        # дошла до GUI-лога, а не пропадала.
        self.stderr_logger = stderr_logger
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

        # stderr движка выводим всегда — даже при returncode == 0 туда могут
        # попасть диагностические сообщения (например, MySQL SHOW WARNINGS).
        if stderr and stderr.strip() and self.stderr_logger is not None:
            for line in stderr.strip().splitlines():
                self.stderr_logger(f"[{self.engine}] {line}")

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
