"""
Диагностический скрипт. Запускать из корня проекта на Windows:
    python check_go.py

Выводит, что именно лежит в engines/go/, какой путь резолвер пробует
и почему запуск может падать.
"""

import os
import subprocess
import sys
from pathlib import Path

print(f"CWD: {Path.cwd()}")
print(f"OS: {os.name} ({sys.platform})")
print()

# 1. Что лежит в engines/go/
go_dir = Path("engines/go")
print(f"=== Содержимое {go_dir.resolve()} ===")
if not go_dir.exists():
    print("  ❌ Папки нет! Возможно, неправильная CWD.")
    sys.exit(1)
for item in sorted(go_dir.iterdir()):
    marker = "📁" if item.is_dir() else "📄"
    size = f"{item.stat().st_size:>10} байт" if item.is_file() else ""
    print(f"  {marker} {item.name:30s} {size}")
print()

# Особый случай для Windows: бинарь без расширения
no_ext = go_dir / "insert_engine"
exe = go_dir / "insert_engine.exe"
if os.name == "nt" and no_ext.exists() and not exe.exists():
    print("  ⚠ Обнаружен 'insert_engine' БЕЗ расширения .exe.")
    print("    Windows такой файл запустить не может.")
    print("    Самый быстрый фикс — переименовать:")
    print("       cd engines\\go")
    print("       ren insert_engine insert_engine.exe")
    print()

# 2. Что говорит резолвер
print("=== Резолвер process_manager._resolve_engine_cmd ===")
try:
    from orchestrator.process_manager import _resolve_engine_cmd, ENGINES
    cmd = _resolve_engine_cmd("Go", ENGINES["Go"])
    print(f"  Возвращает команду: {cmd}")
    abs_path = Path(cmd[0]).resolve()
    print(f"  Абсолютный путь:    {abs_path}")
    print(f"  Существует:         {abs_path.exists()}")
except FileNotFoundError as e:
    print(f"  ❌ Резолвер бросил ошибку:")
    for line in str(e).split("\n"):
        print(f"     {line}")
    sys.exit(1)
print()

# 3. Пробуем запустить бинарник
print("=== Тестовый запуск бинарника ===")
try:
    proc = subprocess.run(
        [cmd[0], "--csv", "nonexistent.csv"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    print(f"  ✓ Запустился! returncode={proc.returncode}")
    if proc.stderr:
        print(f"  stderr: {proc.stderr.strip()[:200]}")
    if proc.stdout:
        print(f"  stdout: {proc.stdout.strip()[:200]}")
except FileNotFoundError as e:
    print(f"  ❌ subprocess.Popen: {e}")
    print(f"  Файл существует, но Windows не может его запустить.")
    print(f"  Вероятная причина: файл не имеет расширения .exe.")
except subprocess.TimeoutExpired:
    print("  ⚠ Зависло на 5 сек (значит запустился и куда-то залез)")
except OSError as e:
    print(f"  ❌ OSError: {e}")
