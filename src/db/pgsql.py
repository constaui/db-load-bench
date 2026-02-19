import psycopg2
from psycopg2 import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError


class PgSQLDatabase(BaseDatabase):

    def connect(self):
        try:
            self.connection = psycopg2.connect(**self.config)
        except Error as e:
            raise DatabaseConnectionError(f"PostgreSQL connection failed: {e}") from e

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def default_insert(self):
        pass

    def bulk_insert(self):
        pass
