from asyncio import sleep
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from keyboards.common_keyboards import get_return_button, get_kb_return, get_kb_yesno_send_xdr
from routers.send import cmd_send_04
from routers.start_msg import cmd_info_message
from utils.aiogram_utils import send_message, admin_id, long_line
from utils.common_utils import get_user_id
from utils.lang_utils import my_gettext
from utils.stellar_utils import *
from utils.thothpay_utils import thoth_create_order, thoth_check_order
from utils.tron_utils import *

router = Router()

fest_menu = {
    "Донаты": {
        "en": "Donations",
        "level2": {
            "Фестиваль": {
                "en": "Fest",
                "address_id": "GBJ4BPR6WESHII6TO4ZUQBB6NJD3NBTK5LISVNKXMPOMMYSLR5DOXMFD",
                "memo": "DONATE_FEST",
                "num": 2
            },
            "Спорт": {
                "en": "Sport",
                "address_id": "GBJ4BPR6WESHII6TO4ZUQBB6NJD3NBTK5LISVNKXMPOMMYSLR5DOXMFD",
                "memo": "DONATE_SPORT",
                "num": 3
            },
            "Дети": {
                "en": "Children",
                "address_id": "GBJ4BPR6WESHII6TO4ZUQBB6NJD3NBTK5LISVNKXMPOMMYSLR5DOXMFD",
                "memo": "DONATE_CHILD",
                "num": 4
            },
            "MTL-Кошелек": {
                "en": "MTL-Wallet",
                "address_id": "GBSNN2SPYZB2A5RPDTO3BLX4TP5KNYI7UMUABUS3TYWWEWAAM2D7CMMW",
                "memo": "DONATE",
                "msg": "Донаты на развитие этого кошелька MTL-Wallet",
                "num": 5
            },
        }
    },
    "Сервис": {
        "en": "Service",
        "level2": {
            "Парковка": {
                "en": "Parking",
                "address_id": "GAXZNLEPYG2M77TWGFYZL6IHJKGX6P5BCCJ7WAMVOOP3UPC5U4LCVCJV",
                "memo": "PARKING",
                "num": 8
            },
        }
    }

}


class SendLevel1(CallbackData, prefix="send_level_1"):
    level_1: str


class SendLevel2(CallbackData, prefix="send_level_2"):
    level_1: str
    level_2: str


class StateFest(StatesGroup):
    sending_sum = State()


@router.callback_query(F.data == "Fest")
async def cmd_fest(callback: types.CallbackQuery, session: Session, state: FSMContext):
    data = await state.get_data()
    if data.get('user_lang') and data.get('user_lang') == 'ru':
        lang_num = 0
        msg = 'Выберите категорию '
    else:
        lang_num = 1
        msg = 'Choose category '

    kb_tmp = []
    for level_1 in fest_menu:
        menu_name = level_1 if lang_num == 0 else fest_menu[level_1].get('en', level_1)
        kb_tmp.append([types.InlineKeyboardButton(text=f"{menu_name}",
                                                  callback_data=SendLevel1(
                                                      level_1=level_1).pack()
                                                  )])

    kb_tmp.append([types.InlineKeyboardButton(text="Купить билет 🥳",
                                              url="https://extravaganza-events.com/radio-world-ru"
                                              )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, msg + long_line(),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp),
                       need_new_msg=True)


@router.callback_query(SendLevel1.filter())
async def cmd_fest_level_1(callback: types.CallbackQuery, callback_data: SendLevel1, state: FSMContext,
                           session: Session):
    data = await state.get_data()
    if data.get('user_lang') and data.get('user_lang') == 'ru':
        lang_num = 0
        msg = 'Выберите участника '
    else:
        lang_num = 1
        msg = 'Choose participant '
    level_1 = callback_data.level_1
    kb_tmp = []
    for level_2 in fest_menu[level_1]['level2']:
        menu_name = fest_menu[level_1]['level2'][level_2].get('ru', level_2) if lang_num == 0 \
            else fest_menu[level_1]['level2'][level_2].get('en', level_2)
        kb_tmp.append([types.InlineKeyboardButton(text=f"{menu_name}",
                                                  callback_data=SendLevel2(
                                                      level_1=level_1, level_2=level_2).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, msg + long_line(),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp),
                       need_new_msg=True)


@router.callback_query(SendLevel2.filter())
async def cmd_fest_level_2(callback: types.CallbackQuery, callback_data: SendLevel2, state: FSMContext,
                           session: Session):
    data = await state.get_data()

    level_1 = callback_data.level_1
    level_2 = callback_data.level_2
    seller = fest_menu[level_1]['level2'][level_2]

    await state.set_state(StateFest.sending_sum)
    if data.get('user_lang') and data.get('user_lang') == 'ru':
        lang_num = 0
        menu_name = fest_menu[level_1]['level2'][level_2].get('ru', level_2) if lang_num == 0 \
            else fest_menu[level_1]['level2'][level_2].get('en', level_2)
        msg = 'Пришлите сумму в EURMTL для отправки на кошелек ' + menu_name
    else:
        lang_num = 1
        menu_name = fest_menu[level_1]['level2'][level_2].get('ru', level_2) if lang_num == 0 \
            else fest_menu[level_1]['level2'][level_2].get('en', level_2)
        msg = 'Send sum in EURMTL to wallet ' + menu_name

    if seller.get('msg') is not None:
        msg = seller['msg'] + '\n\n' + msg

    await send_message(session, callback, msg, reply_markup=get_kb_return(callback.from_user.id))
    await state.update_data(msg=msg, level_1=level_1, level_2=level_2)


@router.message(StateFest.sending_sum)
async def cmd_fest_get_sum(message: Message, state: FSMContext, session: Session):
    await message.delete()
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()
    level_1 = data['level_1']
    level_2 = data['level_2']
    seller = fest_menu[level_1]['level2'][level_2]

    if send_sum > 0.0:
        await state.set_state(None)

        await state.update_data(send_sum=send_sum,
                                send_address=seller['address_id'],
                                memo=seller.get('memo', None),
                                send_asset_code='EURMTL',
                                send_asset_issuer='GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V',
                                )

        await cmd_send_04(session, message, state)
    else:
        keyboard = get_kb_return(message.from_user.id)
        await send_message(session, message, f"{my_gettext(message, 'bad_sum')}\n{data['msg']}",
                           reply_markup=keyboard)
