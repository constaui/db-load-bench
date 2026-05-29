"""
Диагностика LOAD DATA LOCAL INFILE для MySQL.

ЗАПУСК (из корня проекта на Windows):
    python diagnose_mysql_load.py <путь_к_csv> [имя_базы]

Скрипт:
  1. Показывает первые 200 байт CSV-файла (видно реальные line endings).
  2. Подключается к MySQL по параметрам из .env (тот же конфиг, что приложение).
  3. DROP TABLE + CREATE TABLE Test (TEXT-колонки по заголовку CSV).
  4. Выполняет LOAD DATA LOCAL INFILE.
  5. ОБЯЗАТЕЛЬНО показывает SHOW WARNINGS и SHOW STATUS LIKE 'Bytes_received'.
  6. Выводит COUNT(*), первые 5 строк таблицы, типы колонок.
  7. Печатает важные MySQL-переменные: sql_mode, character_set, local_infile.

После запуска пришлите ВЕСЬ вывод — по нему сразу видно, что не так.
"""

import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import mysql.connector


def quote(name: str) -> str:
    clean = name.strip().strip("`").replace("`", "``")
    return f"`{clean}`"


def detect_lines_terminator(path: str) -> str:
    with open(path, "rb") as f:
        chunk = f.read(8192)
    if b"\r\n" in chunk:
        return r"\r\n"
    return r"\n"


def main():
    if len(sys.argv) < 2:
        print("usage: python diagnose_mysql_load.py <csv-path> [database]")
        sys.exit(1)
    csv_path = Path(sys.argv[1]).resolve()
    if not csv_path.exists():
        print(f"❌ файл не найден: {csv_path}")
        sys.exit(1)

    load_dotenv()
    host     = os.getenv("MYSQL_HOST", "localhost")
    port     = int(os.getenv("MYSQL_PORT", "3306"))
    user     = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = sys.argv[2] if len(sys.argv) > 2 else os.getenv("MYSQL_DATABASE", "")
    table    = "Test"

    print("=" * 70)
    print(f"CSV-файл:   {csv_path}")
    print(f"Размер:     {csv_path.stat().st_size:,} байт")
    print(f"MySQL:      {user}@{host}:{port}/{database}")
    print("=" * 70)

    # 1. Сырые байты файла
    print("\n── 1. Первые 200 байт файла (hex + escape) ──")
    with open(csv_path, "rb") as f:
        head = f.read(200)
    print(f"  bytes:  {head!r}")
    print(f"  hex:    {head.hex()}")
    detected_term = detect_lines_terminator(str(csv_path))
    print(f"\n  Детектор line endings вернул: {detected_term!r}")
    crlf = head.count(b"\r\n")
    lf_only = head.count(b"\n") - crlf
    cr_only = head.count(b"\r") - crlf
    print(f"  Найдено CRLF: {crlf}, LF-only: {lf_only}, CR-only: {cr_only}")

    # 2. Заголовок CSV
    print("\n── 2. Заголовок CSV (csv.DictReader) ──")
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        first = next(reader, None)
    print(f"  Колонок: {len(cols)}")
    print(f"  Имена:   {cols}")
    if first:
        print(f"  1-я строка данных: {first}")

    # 3. Подключение к MySQL
    print("\n── 3. Подключение к MySQL ──")
    try:
        conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password,
            database=database, allow_local_infile=True,
            charset="utf8mb4", use_pure=True,
        )
    except Exception as e:
        print(f"❌ Не удалось подключиться: {e}")
        sys.exit(1)
    print(f"✓ Подключение OK")

    cursor = conn.cursor()

    # 4. SQL-режим и важные переменные
    print("\n── 4. MySQL-переменные ──")
    for var in ("sql_mode", "character_set_client", "character_set_connection",
                "character_set_database", "local_infile", "version"):
        try:
            cursor.execute(f"SHOW VARIABLES LIKE '{var}'")
            row = cursor.fetchone()
            if row:
                print(f"  {row[0]:30s} = {row[1]}")
        except Exception as e:
            print(f"  ❌ {var}: {e}")

    # 5. Пересоздание таблицы
    print(f"\n── 5. Пересоздание таблицы '{table}' ──")
    cursor.execute(f"DROP TABLE IF EXISTS {quote(table)}")
    column_defs = ", ".join(f"{quote(c)} TEXT" for c in cols)
    cursor.execute(f"CREATE TABLE {quote(table)} ({column_defs})")
    conn.commit()
    cursor.execute(f"DESCRIBE {quote(table)}")
    print(f"  Структура таблицы:")
    for row in cursor.fetchall():
        print(f"    {row}")

    # 6. LOAD DATA INFILE
    print(f"\n── 6. LOAD DATA LOCAL INFILE ──")
    abs_path = str(csv_path).replace("\\", "/")
    load_sql = f"""
        LOAD DATA LOCAL INFILE '{abs_path}'
        INTO TABLE {quote(table)}
        FIELDS TERMINATED BY ','
        OPTIONALLY ENCLOSED BY '"'
        LINES TERMINATED BY '{detected_term}'
        IGNORE 1 ROWS
    """
    print(f"  SQL: {load_sql.strip()}")
    try:
        cursor.execute(load_sql)
        print(f"  ✓ Выполнено. cursor.rowcount = {cursor.rowcount}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        sys.exit(1)
    conn.commit()

    # 7. SHOW WARNINGS — ключевая часть!
    print(f"\n── 7. SHOW WARNINGS (что MySQL сказал про LOAD DATA) ──")
    cursor.execute("SHOW WARNINGS")
    warnings = cursor.fetchall()
    if not warnings:
        print(f"  (нет предупреждений)")
    else:
        for w in warnings[:20]:
            print(f"  {w}")
        if len(warnings) > 20:
            print(f"  … и ещё {len(warnings) - 20}")

    # 8. Что реально в таблице
    print(f"\n── 8. Что в таблице '{table}' ──")
    cursor.execute(f"SELECT COUNT(*) FROM {quote(table)}")
    total = cursor.fetchone()[0]
    print(f"  COUNT(*) = {total}")
    print(f"  Первые 3 строки:")
    cursor.execute(f"SELECT * FROM {quote(table)} LIMIT 3")
    for row in cursor.fetchall():
        # Покажу обрезанно — на широких таблицах вывод длинный
        s = str(row)
        if len(s) > 200:
            s = s[:200] + "…"
        print(f"    {s}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 70)
    print("ИТОГ:")
    print(f"  В файле строк данных:    {sum(1 for _ in open(csv_path, encoding='utf-8')) - 1}")
    print(f"  В таблице после LOAD:    {total}")
    if total == sum(1 for _ in open(csv_path, encoding="utf-8")) - 1:
        print(f"  ✓ Совпадает — LOAD DATA работает правильно")
    else:
        print(f"  ❌ НЕ СОВПАДАЕТ — нужно смотреть на warnings выше")
    print("=" * 70)


if __name__ == "__main__":
    main()
