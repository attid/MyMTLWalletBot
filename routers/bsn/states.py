from aiogram.fsm.state import State, StatesGroup


class BSNStates(StatesGroup):
    waiting_for_tags = State()
