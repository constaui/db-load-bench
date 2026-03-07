from src.db.mysql import MySQLDatabase
from src.db.pgsql import PgSQLDatabase


DB_CLASSES = {
    "mysql": MySQLDatabase,
    "postgresql": PgSQLDatabase,
}
