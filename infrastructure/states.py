from aiogram.fsm.state import StatesGroup, State

class StateSign(StatesGroup):
    sending_xdr = State()
