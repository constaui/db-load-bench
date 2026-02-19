import os
from dotenv import load_dotenv

load_dotenv()


def get_pg_config():
    return {
        "user": os.getenv("PGSQL_USER"),
        "password": os.getenv("PGSQL_PASSWORD"),
        "host": os.getenv("PGSQL_HOST"),
        "port": int(os.getenv("PGSQL_PORT")),
        "database": os.getenv("PGSQL_DATABASE"),
    }


def get_mysql_config():
    return {
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "host": os.getenv("MYSQL_HOST"),
        "port": int(os.getenv("MYSQL_PORT")),
        "database": os.getenv("MYSQL_DATABASE"),
    }
