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
