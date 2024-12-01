class EmptyTag(ValueError):
    """
    Тег должен иметь хотя бы одну букву
    """
    raw_tag: str

    def __init__(self, raw_tag: str) -> None:
        self.raw_tag = raw_tag


class LengthError(ValueError):
    """
    Длина строки {len(value)} превышает 64 символов.
    """
    value: str

    def __init__(self, value: str) -> None:
        self.value = value