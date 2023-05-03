from typing import Union
from aiogram import types


def get_user_id(user_id: Union[types.CallbackQuery, types.Message, int]) -> int:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    return user_id