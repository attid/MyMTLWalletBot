import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import sessionmaker


class GlobalData:
    tasks = []
    user_lang_dic = {}
    lang_dict = {}
    task_list = []
    bot: Bot
    dispatcher: Dispatcher
    db_pool: sessionmaker
    admin_id = 84131737
    cheque_queue: asyncio.Queue
    log_queue: asyncio.Queue
    localization_service = None


global_data = GlobalData()
global_data.cheque_queue = asyncio.Queue()
global_data.log_queue = asyncio.Queue()


class StateSign(StatesGroup):
    sending_xdr = State()


class LogQuery:
    def __init__(self, user_id: int, log_operation: str, log_operation_info: str):
        self.user_id = user_id
        self.log_operation = log_operation
        self.log_operation_info = log_operation_info
        self.log_dt = datetime.now()
