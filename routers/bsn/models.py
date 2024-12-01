from collections import defaultdict
from dataclasses import dataclass

from routers.bsn.constants import KNOWN_TAGS
from routers.bsn.enums import ActionType
from routers.bsn.exceptions import EmptyTag
from routers.bsn.value_objects import Address, Key, Value

@dataclass
class Tag:
    key: Key
    num: int|None = None

    def __str__(self):
        return f"{self.key}{self.num or ''}"

    def __hash__(self):
        return hash(self.__str__())

    @property
    def is_known_key(self):
        return self.key.lower() in {tag.lower() for tag in KNOWN_TAGS}

    @classmethod
    def parse(cls, raw_tag: str) -> "Tag":
        letters = ''
        digits = ''
        stop_index = 0
        for index, char in enumerate(raw_tag[::-1]):
            if char.isdigit():
                digits = f'{char}{digits}'
            else:
                stop_index = len(raw_tag) - index
                break
        letters = raw_tag[:stop_index]
        if not letters:
            raise EmptyTag(raw_tag)
        keys_map = {key.lower(): key for key in KNOWN_TAGS}

        key = Key(letters)
        if key.lower() in keys_map:
            key = keys_map[key.lower()]
        num = int(digits) if digits else None
        return cls(key, num)



@dataclass
class BSNRow:
    tag: Tag
    value: Value
    action_type: ActionType = ActionType.KEEP
    old_value: Value | None = None

    def __str__(self):
        return f"{'⚠️ ' if self.tag.is_known_key else ''}{self.tag}: {self.value}"

    @classmethod
    def from_str(cls, tag: str, value: str) -> "BSNRow":
        return BSNRow(Tag.parse(tag), Value(value))

    def change_value(self, new_value: "Value") -> "BSNRow":
        self.old_value = self.value
        self.value = new_value
        self.action_type = ActionType.CHANGE
        return self

    def delete(self) -> "BSNRow":
        self.action_type = ActionType.REMOVE
        return self

    @property
    def is_modify(self):
        return self.action_type in (ActionType.REMOVE, ActionType.CHANGE, ActionType.ADD)

    def is_remove(self):
        return self.action_type == ActionType.REMOVE

    def is_change(self):
        return self.action_type == ActionType.CHANGE

class BSNData:
    address: Address

    _map: dict[Tag, BSNRow]
    _multiple_tag_numbers: dict[Key, set[int]]

    def __init__(self, address: Address, data: list[BSNRow]):
        self.address = address
        self._map = dict()
        self._multiple_tag_numbers = defaultdict(set)

        for row in data:
            self._map[row.tag] = row
            if row.tag.num:
                self._multiple_tag_numbers[row.tag.key].add(row.tag.num)

    def _get_next_num(self, key: Key) -> int:
        num = 1
        while num in self._multiple_tag_numbers[key]:
            num += 1
        return num

    def _make_tag(self, key: Key) -> Tag:
        tag = Tag.parse(key)
        if tag.num is None:
            tag.num = self._get_next_num(tag.key)
        return tag

    def add_new_data_row(self, key: Key, value: Value):
        tag = self._make_tag(key)
        if tag in self._map:
            self._map[tag].change_value(value)
        else:
            row = BSNRow(tag, value, ActionType.ADD)
            self._map[tag] = row
        if tag.num:
            self._multiple_tag_numbers[tag.key].add(tag.num)

    def del_data_row(self, key: Key):
        tag = Tag.parse(key)
        if tag in self._map:
            self._map[tag].delete()
        if tag.num:
            self._multiple_tag_numbers[tag.key].remove(tag.num)

    def is_empty(self):
        return len(self.changed_items()) == 0

    def changed_items(self) -> tuple[BSNRow, ...]:
        return tuple(filter(lambda _row: _row.is_modify, self._map.values()))
