import csv
import mysql.connector


def _connect(conn_params: dict):
    # use_pure=True + charset=utf8mb4: на Windows с русской локалью
    # mysql.connector без этих опций может ронять процесс на декоде ошибок.
    conn = mysql.connector.connect(
        host=conn_params["host"],
        port=conn_params["port"],
        user=conn_params["user"],
        password=conn_params["password"],
        database=conn_params["database"],
        allow_local_infile=True,
        charset="utf8mb4",
        use_pure=True,
    )
    return conn


def _quote(name: str) -> str:
    clean = name.strip().strip("`").replace("`", "``")
    return f"`{clean}`"


def _detect_lines_terminator(path: str) -> str:
    """Возвращает строку-аргумент для LOAD DATA LINES TERMINATED BY.
    Без декодирования файла: читаем первые 8 КБ, ищем CRLF — типичен для
    CSV, созданных на Windows (Excel, Python csv с дефолтным newline и т.п.).
    MySQL LOAD DATA INFILE строгий: при несовпадении терминатора всё
    содержимое воспринимается как одна «строка», и IGNORE 1 ROWS оставляет
    1 «битую» запись."""
    with open(path, "rb") as f:
        chunk = f.read(8192)
    if b"\r\n" in chunk:
        return r"\r\n"  # 4 символа: \, r, \, n — MySQL раскроет как CRLF
    return r"\n"


def count_rows(conn_params: dict, table_name: str) -> int:
    """Возвращает фактическое число строк в таблице из самой БД.
    Используется в main.py для независимой проверки результата вставки."""
    conn = _connect(conn_params)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {_quote(table_name)}")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        cursor.close()
        conn.close()


def default_insert(conn_params: dict, csv_file: str, table_name: str) -> int:
    conn = _connect(conn_params)
    cursor = conn.cursor()
    count = 0
    try:
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                col_names = ", ".join(_quote(c) for c in row.keys())
                placeholders = ", ".join(["%s"] * len(row))
                cursor.execute(
                    f"INSERT INTO {_quote(table_name)} ({col_names}) VALUES ({placeholders})",
                    list(row.values()),
                )
                count += 1
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def bulk_insert(
    conn_params: dict, csv_file: str, table_name: str, batch_size: int = 1000
) -> int:
    conn = _connect(conn_params)
    cursor = conn.cursor()
    count = 0
    try:
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            col_names = ", ".join(_quote(c) for c in reader.fieldnames)
            placeholders = ", ".join(["%s"] * len(reader.fieldnames))
            sql = f"INSERT INTO {_quote(table_name)} ({col_names}) VALUES ({placeholders})"

            batch = []
            for row in reader:
                batch.append(list(row.values()))
                if len(batch) >= batch_size:
                    cursor.executemany(sql, batch)
                    count += len(batch)
                    batch.clear()
            if batch:
                cursor.executemany(sql, batch)
                count += len(batch)

        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def file_insert(conn_params: dict, csv_file: str, table_name: str) -> int:
    conn = _connect(conn_params)
    cursor = conn.cursor()
    try:
        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            row_count = sum(1 for _ in csv.DictReader(f))

        abs_path = csv_file.replace("\\", "/")
        line_term = _detect_lines_terminator(csv_file)
        cursor.execute(
            f"""
            LOAD DATA LOCAL INFILE '{abs_path}'
            INTO TABLE {_quote(table_name)}
            FIELDS TERMINATED BY ','
            OPTIONALLY ENCLOSED BY '"'
            LINES TERMINATED BY '{line_term}'
            IGNORE 1 ROWS
        """
        )
        conn.commit()
        return row_count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
