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

    @abstractmethod
    def default_insert(self, csv_file: str, table_name: str) -> int:
        pass

    @abstractmethod
    def bulk_insert(self, csv_file: str, table_name: str, batch_size: int) -> int:
        pass

    @abstractmethod
    def file_insert(self, csv_file: str, table_name: str) -> int:
        pass
