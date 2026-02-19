from src.db.pgsql import PgSQLDatabase
from src.db.mysql import MySQLDatabase
from src.config.settings import get_pg_config, get_mysql_config
from src.db.exceptions import DatabaseError


def main():

    pgsql = None
    mysql = None

    try:
        pgsql = PgSQLDatabase(get_pg_config())
        mysql = MySQLDatabase(get_mysql_config())

        pgsql.connect()
        mysql.connect()

        print("PostgreSQL connected successfully")
        print("MySQL connected successfully")

    except DatabaseError as err:
        print(f"Error: {err}")

    finally:
        if pgsql:
            pgsql.close()
        if mysql:
            mysql.close()


if __name__ == "__main__":
    main()
