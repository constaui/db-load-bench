import csv
import psycopg2
from psycopg2.extras import execute_values


def _connect(conn_params: dict):
    return psycopg2.connect(
        host=conn_params["host"],
        port=conn_params["port"],
        user=conn_params["user"],
        password=conn_params["password"],
        dbname=conn_params["database"],
    )


def _quote(name: str) -> str:
    clean = name.strip().strip('"').replace('"', '""')
    return f'"{clean}"'


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
            sql = f"INSERT INTO {_quote(table_name)} ({col_names}) VALUES %s"

            batch = []
            for row in reader:
                batch.append(list(row.values()))
                if len(batch) >= batch_size:
                    execute_values(cursor, sql, batch, page_size=batch_size)
                    count += len(batch)
                    batch.clear()
            if batch:
                execute_values(cursor, sql, batch, page_size=batch_size)
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

        with open(csv_file, "r", newline="", encoding="utf-8") as f:
            cursor.copy_expert(
                f"COPY {_quote(table_name)} FROM STDIN WITH (FORMAT csv, HEADER true)",
                f,
            )
        conn.commit()
        return row_count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
