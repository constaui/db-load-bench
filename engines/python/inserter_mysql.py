import csv
import mysql.connector


def _connect(conn_params: dict):
    conn = mysql.connector.connect(
        host=conn_params["host"],
        port=conn_params["port"],
        user=conn_params["user"],
        password=conn_params["password"],
        database=conn_params["database"],
        allow_local_infile=True,
    )
    return conn


def _quote(name: str) -> str:
    clean = name.strip().strip("`").replace("`", "``")
    return f"`{clean}`"


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
        cursor.execute(
            f"""
            LOAD DATA LOCAL INFILE '{abs_path}'
            INTO TABLE {_quote(table_name)}
            FIELDS TERMINATED BY ','
            OPTIONALLY ENCLOSED BY '"'
            LINES TERMINATED BY '\\n'
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
