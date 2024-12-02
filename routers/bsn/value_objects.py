from routers.bsn.exceptions import LengthError


class Str64b(str):
    def __new__(cls, value):
        if len(value) > 64:
            raise LengthError(value)
        if len(value) < 1:
            raise ValueError(f"Не может быть пусто")
        return super().__new__(cls, value)

class Key(Str64b):
    pass

class Value(Str64b):
    pass

class Address(str):
    pass
