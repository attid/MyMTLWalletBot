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
    "Еда": {
        "en": "Food",
        "level2": {
            "Шум": {
                "en": "Shoom",
                "address_id": "GBSO2XTJ6VBGJQTRDFQHQRA4JFAUU2DTSJRJJLWFDSKGRBAHLH24C67A",
            },
            "Нур": {
                "en": "Nur",
                "address_id": "GBR2OOELH3RULCGYK24TX2QX6XFSEALHUZXGLN3CL3DHG7MLVWWG4SBA",
            },
            "Montespirits": {
                "en": "Montespirits",
                "address_id": "GBPJJYVFIYSSRWYZBNHL7EIRBOXEX5JQHJALD2EVOQFZO2ESQGJPFPZW",
            },
            "Сидр": {
                "en": "Sidr",
                "address_id": "GA7C5RVQXIGU3IOARQZARUTCC3B5PD7YOCC4B6KO2QTIUQDICWEK6H2E",
            },
            "ИдК": {
                "en": "IdK",
                "address_id": "GCHMLPSNB4G7XUPDW44P4I64P3GLLUJZPF63UYN4RK3AUQTGF2XPOD27",
            },
            "Chicago Street Food": {
                "en": "Chicago Street Food",
                "address_id": "GA5N3MESHDUGW4CMRQ6BWIH3WL6LSFCD5HKRXGSRHRAW7DPSTTR3SPTR",
            },

        }
    },
    "Ярмарка": {
        "en": "City Fair",
        "level2": {
            "Ольга Футболки": {
                "en": "Olga T-Shirts",
                "address_id": "GD2QQH5T72SJO3AEZBVGR4HMYK7N6OPBA2OJ6QHOGUA7K3QDSJ4OLQ4U"
            },
            "Инна Аквагрим": {
                "en": "Inna Aquagrim",
                "address_id": "GDTVPQQLT6RJNHWFGTYG6G3L6PG6QIT5IPXUSN3H4RNKDTGHLHKPN5MS"
            },
            "Лика Корзинки": {
                "en": "Lika Baskets",
                "address_id": "GDUKYQHTGHIHTXL4QK2OQF2GKKAO2THGOP7LLP3NQJNTHE7BLDNJZJEY"
            },
            "Настя Рисунки": {
                "en": "Nastya Drawings",
                "address_id": "GAZEFASTL4P7A6ERCSHKWDCKBQVGA4R3V5336ILQF4MSALSAH3VMGHIW"
            },
            "Софи Сувениры": {
                "en": "Sofi Souvenirs",
                "address_id": "GBR2OOELH3RULCGYK24TX2QX6XFSEALHUZXGLN3CL3DHG7MLVWWG4SBA",
                "memo": "СУВЕНИРЫ",

            },
            "Головоломки": {
                "en": "Puzzles",
                "address_id": "GBZLRUMH2OFB5OOGA6BHWSKG4IXWIJRJZCUP3JT3NGK53SLARDLRLY7K",
            },
            "Анкап книжка": {
                "en": "Ankap Book",
                "address_id": "GA6BT2ZF577HWKLKVKMXIEM7TVA7LQIRNAGCUHZWBLSGZYJ4CPNA33RR",
            },
        }
    },
    "Донаты": {
        "en": "Donations",
        "level2": {
            "Фестиваль": {
                "en": "Fest",
                "address_id": "GBJ4BPR6WESHII6TO4ZUQBB6NJD3NBTK5LISVNKXMPOMMYSLR5DOXMFD",
                "memo": "DONATE_FEST",
            },
            "Спорт": {
                "en": "Sport",
                "address_id": "GBJ4BPR6WESHII6TO4ZUQBB6NJD3NBTK5LISVNKXMPOMMYSLR5DOXMFD",
                "memo": "DONATE_SPORT",
            },
            "Дети": {
                "en": "Children",
                "address_id": "GBJ4BPR6WESHII6TO4ZUQBB6NJD3NBTK5LISVNKXMPOMMYSLR5DOXMFD",
                "memo": "DONATE_CHILD",
            },
            "MTL-Кошелек": {
                "en": "MTL-Wallet",
                "address_id": "GBSNN2SPYZB2A5RPDTO3BLX4TP5KNYI7UMUABUS3TYWWEWAAM2D7CMMW",
                "memo": "DONATE",
                "msg": "Донаты на развитие этого кошелька MTL-Wallet"
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
        menu_name = level_1 if lang_num == 0 else fest_menu[level_1]['en']
        kb_tmp.append([types.InlineKeyboardButton(text=f"{menu_name}",
                                                  callback_data=SendLevel1(
                                                      level_1=level_1).pack()
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
        menu_name = level_2 if lang_num == 0 else fest_menu[level_1]['level2'][level_2]['en']
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
        menu_name = level_2 if lang_num == 0 else fest_menu[level_1]['level2'][level_2]['en']
        msg = 'Пришлите сумму в EURMTL для отправки на кошелек ' + menu_name
    else:
        lang_num = 1
        menu_name = level_2 if lang_num == 0 else fest_menu[level_1]['level2'][level_2]['en']
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
