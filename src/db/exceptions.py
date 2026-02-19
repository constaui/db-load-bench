class DatabaseError(Exception):
    pass


class DatabaseConnectionError(DatabaseError):
    pass


class DatabaseInsertError(DatabaseError):
    pass
