from abc import ABC, abstractmethod


class BaseDatabase(ABC):

    def __init__(self, config: dict):
        self.config = config
        self.connection = None

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def prepare(self, cursor, csv_file, table_name):
        pass

    def get_version(self) -> str:
        """Версия сервера БД (например "8.0.32" / "16.1"). Пусто при ошибке."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
            cursor.close()
            return str(row[0]) if row else ""
        except Exception:
            return ""
