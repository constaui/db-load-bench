import argparse
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))


from orchestrator.protocol import MethodRun
from src.config.db import DB_CLASSES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--db-type", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    conn_params = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "password": args.password,
        "database": args.database,
    }

    db_class = DB_CLASSES.get(args.db_type)
    if db_class is None:
        print(f"Unknown db type: {args.db_type}", file=sys.stderr)
        sys.exit(1)

    db = db_class(conn_params)
    db.connect()

    insert_fn = getattr(db, args.method)
    start = time.perf_counter()
    if args.method == "bulk_insert":
        rows = insert_fn(args.csv, args.table, args.batch_size)
    else:
        rows = insert_fn(args.csv, args.table)
    elapsed = time.perf_counter() - start

    db.close()

    run = MethodRun(
        engine="Python",
        db_type=args.db_type,
        method=args.method,
        experiment_config={"rows": rows},
        method_config={
            "batch_size": args.batch_size if args.method == "bulk_insert" else None
        },
        metrics={"elapsed": elapsed, "rps": round(rows / elapsed, 1)},
    )

    print(json.dumps(run.to_dict()))


if __name__ == "__main__":
    main()
