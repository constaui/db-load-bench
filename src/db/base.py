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
    def default_insert(self):
        pass

    @abstractmethod
    def bulk_insert(self):
        pass
