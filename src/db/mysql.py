import mysql.connector
from mysql.connector import Error
from .base import BaseDatabase
from .exceptions import DatabaseConnectionError


class MySQLDatabase(BaseDatabase):

    def connect(self):
        try:
            self.connection = mysql.connector.connect(**self.config)
        except Error as e:
            raise DatabaseConnectionError(f"MySQL connection failed: {e}") from e

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
