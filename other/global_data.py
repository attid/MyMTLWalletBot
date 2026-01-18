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



