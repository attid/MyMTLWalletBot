from typing import List
import jsonpickle
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from requests import Session
from stellar_sdk import Asset
from sulguk import SULGUK_PARSE_MODE

from other.config_reader import config
from db.requests import db_get_book_data, db_get_address_book_by_id, db_delete_address_book_by_id, \
    db_insert_into_address_book, \
    db_get_default_wallet, db_get_user_account_by_username
from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return, get_kb_del_return
from other.grist_tools import load_asset_from_grist
from other.mytypes import Balance
from routers.add_wallet import cmd_show_add_wallet_choose_pin
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_info_message
from other.aiogram_tools import send_message, my_gettext, clear_state, get_web_request, get_web_decoded_xdr
from loguru import logger

from other.global_data import global_data
from other.lang_tools import check_user_id
from other.stellar_tools import (stellar_get_balances, stellar_add_trust, stellar_get_user_account,
                                 stellar_is_free_wallet, public_issuer, get_good_asset_list,
                                 stellar_pay, eurmtl_asset, float2str, stellar_get_user_keypair,
                                 stellar_change_password, stellar_unfree_wallet, have_free_xlm,
                                 stellar_get_user_seed_phrase, stellar_close_asset,
                                 stellar_has_asset_offers)
from other.asset_visibility_tools import (
    get_asset_visibility, set_asset_visibility,
    ASSET_VISIBLE, ASSET_EXCHANGE_ONLY, ASSET_HIDDEN
)



class DelAssetCallbackData(CallbackData, prefix="DelAssetCallbackData"):
    answer: str


class AddAssetCallbackData(CallbackData, prefix="AddAssetCallbackData"):
    answer: str


class MDCallbackData(CallbackData, prefix="MDCallbackData"):
    uuid_callback: str


class AddressBookCallbackData(CallbackData, prefix="AddressBookCallbackData"):
    action: str
    idx: int


class StateAddAsset(StatesGroup):
    sending_code = State()
    sending_issuer = State()


class StateAddressBook(StatesGroup):
    sending_new = State()


class AssetVisibilityCallbackData(CallbackData, prefix="AVD_"):
    action: str  # 'set', 'page', 'toggle' (toggle is deprecated but kept for compatibility during transition if needed)
    code: str = "*"  # Asset code, empty for page actions
    status: int = -1 # Target status (ASSET_VISIBLE, ASSET_EXCHANGE_ONLY, ASSET_HIDDEN), -1 for page actions
    page: int = 1 # Page number


router = Router()
router.message.filter(F.chat.type == "private")

# ASSET_VISIBILITY_CYCLE = [ASSET_VISIBLE, ASSET_EXCHANGE_ONLY, ASSET_HIDDEN] # Deprecated cycle logic

# def get_next_visibility(status): # Deprecated cycle logic
#     idx = ASSET_VISIBILITY_CYCLE.index(status)
#     return ASSET_VISIBILITY_CYCLE[(idx + 1) % len(ASSET_VISIBILITY_CYCLE)]

ASSETS_PER_PAGE = 30 # Max assets per page

@router.callback_query(F.data == "WalletSetting")
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'wallet_setting_msg')
    free_wallet = await stellar_is_free_wallet(session, callback.from_user.id)
    if free_wallet:
        private_button = types.InlineKeyboardButton(text=my_gettext(callback, 'kb_buy'), callback_data="BuyAddress")
    else:
        private_button = types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_key'),
                                                    callback_data="GetPrivateKey")

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_manage_assets'), callback_data="ManageAssetsMenu")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_address_book'), callback_data="AddressBook")],
        [types.InlineKeyboardButton(text='Manage Data', callback_data="ManageData")],
        [private_button],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_password'), callback_data="SetPassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_remove_password'), callback_data="RemovePassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_donate'), callback_data="Donate")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_default'), callback_data="SetDefault")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_limit'), callback_data="SetLimit")],
        [types.InlineKeyboardButton(text='🔕 ' + my_gettext(callback, 'kb_notification_settings'),
                                    callback_data="NotificationSettings")],
        [types.InlineKeyboardButton(text='🌐 ' + my_gettext(callback, 'change_lang'), callback_data="ChangeLang")],
        # last button
        get_return_button(callback)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)


@router.callback_query(F.data == "ManageAssetsMenu")
async def cmd_manage_assets(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'manage_assets_msg')
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_delete_one'), callback_data="DeleteAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_list'), callback_data="AddAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_expert'), callback_data="AddAssetExpert")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_asset_visibility'), callback_data="AssetVisibilityMenu")],
        get_return_button(callback)
    ]
    await callback.answer()

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)


# Helper function to generate the message text and keyboard markup
async def _generate_asset_visibility_markup(user_id: int, session: Session, page: int = 1) -> tuple[str, types.InlineKeyboardMarkup]:
    """Generates the text and keyboard for the asset visibility menu."""
    from db.requests import db_get_default_wallet
    wallet = db_get_default_wallet(session, user_id)
    balances = await stellar_get_balances(session, user_id) # Consider sorting or filtering if needed

    vis_dict = {}
    if wallet.assets_visibility:
        from other.asset_visibility_tools import deserialize_visibility
        vis_dict = deserialize_visibility(wallet.assets_visibility)

    # Pagination logic
    total_assets = len(balances)
    total_pages = (total_assets + ASSETS_PER_PAGE - 1) // ASSETS_PER_PAGE
    page = max(1, min(page, total_pages)) # Ensure page is within bounds
    start_index = (page - 1) * ASSETS_PER_PAGE
    end_index = start_index + ASSETS_PER_PAGE
    assets_on_page = balances[start_index:end_index]

    kb = []
    # Asset buttons
    for asset in assets_on_page:
        code = asset.asset_code
        issuer = asset.asset_issuer # Keep issuer for potential future use (e.g., URL)
        current_status = vis_dict.get(code, ASSET_VISIBLE)

        # Button texts with status indicators
        exchange_only_text = my_gettext(user_id, 'asset_exchange_only')
        hidden_text = my_gettext(user_id, 'asset_hidden')
        if current_status == ASSET_EXCHANGE_ONLY:
            exchange_only_text = "✅ " + exchange_only_text
        elif current_status == ASSET_HIDDEN:
            hidden_text = "✅ " + hidden_text

        # Create buttons for the row
        name_button = types.InlineKeyboardButton(
            text=code,
            callback_data="do_nothing" # Placeholder or specific action if required
        )
        exchange_only_button = types.InlineKeyboardButton(
            text=exchange_only_text,
            # Pass integer status 1 for exchange_only
            callback_data=AssetVisibilityCallbackData(action="set", code=code, status=1, page=page).pack()
        )
        hidden_button = types.InlineKeyboardButton(
            text=hidden_text,
            # Pass integer status 2 for hidden
            callback_data=AssetVisibilityCallbackData(action="set", code=code, status=2, page=page).pack()
        )
        kb.append([name_button, exchange_only_button, hidden_button])

    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton(
            text="◀️ " + my_gettext(user_id, 'prev_page'),
            callback_data=AssetVisibilityCallbackData(action="page", page=page - 1).pack()
        ))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(
            text=my_gettext(user_id, 'next_page') + " ▶️",
            callback_data=AssetVisibilityCallbackData(action="page", page=page + 1).pack()
        ))

    if nav_buttons:
        kb.append(nav_buttons)
        logger.info(f"Navigation buttons added: {nav_buttons}")
        logger.info(f"Total keyboard: {kb}")

    # Back button
    kb.append(get_return_button(user_id)) # Assuming get_return_button returns a list containing the button

    # Generate message text
    message_text = my_gettext(user_id, 'asset_visibility_msg')
    if total_pages > 1:
         message_text += f"\n{my_gettext(user_id, 'page')} {page}/{total_pages}"

    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    return message_text, reply_markup


@router.callback_query(F.data == "AssetVisibilityMenu")
async def cmd_asset_visibility_menu(callback: types.CallbackQuery, state: FSMContext, session: Session):
    """Displays the initial asset visibility settings menu."""
    user_id = callback.from_user.id
    message_text, reply_markup = await _generate_asset_visibility_markup(user_id, session, page=1)

    await callback.answer()
    await send_message(session, callback, message_text, reply_markup=reply_markup)


########################################################################################################################
########################################################################################################################
########################################################################################################################
@router.callback_query(AssetVisibilityCallbackData.filter())
async def handle_asset_visibility_action(callback: types.CallbackQuery, callback_data: AssetVisibilityCallbackData, state: FSMContext, session: Session):
    """Handles actions from the asset visibility menu (setting status or changing page)."""
    logger.info(f"Entered handle_asset_visibility_action with callback_data: {callback_data!r}") # Log entry point
    action = callback_data.action
    page = callback_data.page # Current page when the button was clicked
    user_id = callback.from_user.id

    if action == "page":
        # Navigate to the requested page
        target_page = callback_data.page # The page number is directly in callback_data for 'page' action
        message_text, reply_markup = await _generate_asset_visibility_markup(user_id, session, page=target_page)
        try:
            await callback.message.edit_text(message_text, reply_markup=reply_markup)
            await callback.answer()
        except Exception as e:
            logger.error(f"Error editing message for asset visibility page change: {e}")
            await callback.answer(my_gettext(callback, 'error_refreshing_menu'), show_alert=True) # Inform user about error

    elif action == "set":
        # Set the visibility status for an asset
        from db.requests import db_get_default_wallet
        from sqlalchemy.orm import Session as OrmSession
        from other.asset_visibility_tools import deserialize_visibility, serialize_visibility

        wallet = db_get_default_wallet(session, user_id)
        asset_code = callback_data.code
        target_status_int = callback_data.status # The integer status associated with the button pressed (1 or 2)

        # Map integer status from callback to string status used internally
        STATUS_INT_TO_STR = {
            1: ASSET_EXCHANGE_ONLY,
            2: ASSET_HIDDEN,
        }
        target_status_str = STATUS_INT_TO_STR.get(target_status_int)

        if target_status_str is None:
             logger.error(f"Invalid target status integer received: {target_status_int} for asset {asset_code}")
             await callback.answer(my_gettext(callback, 'error_processing_request'), show_alert=True)
             return # Stop if status is invalid

        vis_dict = deserialize_visibility(wallet.assets_visibility) if wallet.assets_visibility else {}
        current_status_str = vis_dict.get(asset_code, ASSET_VISIBLE)

        # Determine the new status based on the click (using string statuses now)
        if current_status_str == target_status_str:
            new_status_str = ASSET_VISIBLE # Clicking checked button -> set to VISIBLE
        else:
            new_status_str = target_status_str # Clicking unchecked button -> set to target

        # Update the dictionary and save to DB (using string statuses)
        if new_status_str == ASSET_VISIBLE:
            vis_dict.pop(asset_code, None) # Remove from dict if setting back to default visible
        else:
            vis_dict[asset_code] = new_status_str

        wallet.assets_visibility = serialize_visibility(vis_dict)
        save_error = False
        if isinstance(session, OrmSession):
            try:
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Error committing asset visibility changes: {e}")
                await callback.answer(my_gettext(callback, 'error_saving_settings'), show_alert=True)
                save_error = True
        else:
             logger.warning("Asset visibility change in non-ORM session, commit might not be applicable.")

        if not save_error:
            # Redraw the current page of the menu to reflect the change
            message_text, reply_markup = await _generate_asset_visibility_markup(user_id, session, page=page)
            try:
                await callback.message.edit_text(message_text, reply_markup=reply_markup)
                await callback.answer(my_gettext(callback, 'asset_visibility_changed'))
            except Exception as e:
                logger.error(f"Error editing message after asset visibility change: {e}")
                # If edit fails after save, at least inform user status was likely saved
                await callback.answer(my_gettext(callback, 'asset_visibility_changed') + " (UI update failed)", show_alert=True)

    elif action == "toggle":
        # Handle legacy toggle action if necessary, or log a warning
        logger.warning(f"Received legacy 'toggle' action for asset visibility from user {user_id}")
        await callback.answer("Legacy action received.", show_alert=True) # Or implement fallback logic
    else:
        logger.warning(f"Unknown asset visibility action: {action} from user {user_id}")
        await callback.answer("Unknown action.", show_alert=True)


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "DeleteAsset")
async def cmd_add_asset_del(callback: types.CallbackQuery, state: FSMContext, session: Session):
    asset_list = await stellar_get_balances(session, callback.from_user.id)

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                  callback_data=DelAssetCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    msg = my_gettext(callback, 'delete_asset2')
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))
    await state.update_data(assets=jsonpickle.encode(asset_list))
    await callback.answer()


@router.callback_query(DelAssetCallbackData.filter())
async def cq_swap_choose_token_from(callback: types.CallbackQuery, callback_data: DelAssetCallbackData,
                                    state: FSMContext, session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        asset_obj = Asset(asset[0].asset_code, asset[0].asset_issuer)
        if await stellar_has_asset_offers(session, callback.from_user.id, asset_obj):
            await send_message(session, callback, my_gettext(callback, 'close_asset_has_offers'),
                               reply_markup=get_kb_return(callback))
            await callback.answer()
            return

        xdr = await stellar_close_asset(
            (await stellar_get_user_account(session, callback.from_user.id)).account.account_id,
            asset_obj,
            asset[0].balance)

        msg = my_gettext(callback, 'confirm_close_asset', (asset[0].asset_code, asset[0].asset_issuer))
        await state.update_data(xdr=xdr)

        await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    else:
        await callback.answer(my_gettext(callback, "bad_data"), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "AddAsset")
async def cmd_add_asset_add(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_id = callback.from_user.id
    if await stellar_is_free_wallet(session, user_id) and (len(await stellar_get_balances(session, user_id)) > 5):
        await send_message(session, user_id, my_gettext(user_id, 'only_3'), reply_markup=get_kb_return(user_id))
        return False

    if not await have_free_xlm(session=session, state=state, user_id=callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return

    good_asset = get_good_asset_list()
    for item in await stellar_get_balances(session, user_id):
        found = list(filter(lambda x: x.asset_code == item.asset_code, good_asset))
        if len(found) > 0:
            good_asset.remove(found[0])

    if len(good_asset) == 0:
        await send_message(session, user_id, my_gettext(user_id, 'have_all'), reply_markup=get_kb_return(user_id))
        return False

    kb_tmp = []
    for key in good_asset:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{key.asset_code}",
                                                  callback_data=AddAssetCallbackData(
                                                      answer=key.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, my_gettext(user_id, 'open_asset'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))

    await state.update_data(assets=jsonpickle.encode(good_asset))


@router.callback_query(AddAssetCallbackData.filter())
async def cq_add_asset(callback: types.CallbackQuery, callback_data: AddAssetCallbackData,
                       state: FSMContext, session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        await cmd_add_asset_end(callback.message.chat.id, state, session, )
    else:
        await callback.answer(my_gettext(callback, "bad_data"), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "AddAssetExpert")
async def cmd_add_asset_expert(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_id = callback.from_user.id
    if await stellar_is_free_wallet(session, user_id) and (len(await stellar_get_balances(session, user_id)) > 5):
        await send_message(session, user_id, my_gettext(user_id, 'only_3'), reply_markup=get_kb_return(user_id))
        return False

    if not await have_free_xlm(session=session, state=state, user_id=callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return

    await state.set_state(StateAddAsset.sending_code)
    msg = my_gettext(user_id, 'send_code')
    await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id))
    await callback.answer()


@router.message(StateAddAsset.sending_code)
async def cmd_sending_code(message: types.Message, state: FSMContext, session: Session):
    user_id = message.from_user.id
    asset_code = message.text
    await state.update_data(send_asset_code=asset_code)

    await state.set_state(StateAddAsset.sending_issuer)

    msg = my_gettext(user_id, 'send_issuer', (public_issuer,))
    await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id))


@router.message(StateAddAsset.sending_issuer)
async def cmd_sending_issuer(message: types.Message, state: FSMContext, session: Session):
    await state.update_data(send_asset_issuer=message.text)
    await cmd_add_asset_end(message.chat.id, state, session, )


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.message(Command(commands=["start"]), F.text.contains("asset_"))
async def cmd_start_cheque(message: types.Message, state: FSMContext, session: Session):
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading')

    # if user not exist
    if not check_user_id(session, message.from_user.id):
        await send_message(session, message.from_user.id, 'You dont have wallet. Please run /start')
        return

    asset = message.text.split(' ')[1][6:]
    asset_code = asset.split('-')[0]
    asset_issuer = asset.split('-')[1]

    try:
        if asset_issuer == '0':
            grist_answer = await load_asset_from_grist(asset_code)
            public_key = grist_answer.issuer if grist_answer else None
        else:
            public_key, user_id = db_get_user_account_by_username(session, '@' + asset_issuer)

        if public_key is None:
            raise Exception("public_key is None")
    except Exception as ex:
        await send_message(session, message.chat.id, my_gettext(message.chat.id, 'send_error2'),
                           reply_markup=get_kb_return(message))
        return

    await state.update_data(send_asset_code=asset_code)
    await state.update_data(send_asset_issuer=public_key)
    await cmd_add_asset_end(message.chat.id, state, session, )


########################################################################################################################
########################################################################################################################
########################################################################################################################


async def cmd_add_asset_end(chat_id: int, state: FSMContext, session: Session):
    data = await state.get_data()
    asset_code = data.get('send_asset_code', 'XLM')
    asset_issuer = data.get('send_asset_issuer', '')

    xdr = await stellar_add_trust((await stellar_get_user_account(session, chat_id)).account.account_id,
                                  Asset(asset_code, asset_issuer))

    msg = my_gettext(chat_id, 'confirm_asset', (asset_code, asset_issuer))

    await state.update_data(xdr=xdr, operation='add_asset')
    await send_message(session, chat_id, msg, reply_markup=get_kb_yesno_send_xdr(chat_id))


########################################################################################################################
########################################################################################################################
########################################################################################################################

async def remove_password(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    stellar_change_password(session, user_id, pin, str(user_id), 0)
    await state.set_state(None)
    await cmd_info_message(session, user_id, 'Password was unset', )


@router.callback_query(F.data == "RemovePassword")
async def cmd_remove_password(callback: types.CallbackQuery, state: FSMContext, session: Session):
    pin_type = db_get_default_wallet(session, callback.from_user.id).use_pin
    if pin_type in (1, 2):
        await state.update_data(fsm_func=jsonpickle.dumps(remove_password))
        await state.set_state(PinState.sign)
        await cmd_ask_pin(session, callback.from_user.id, state)
        await callback.answer()
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        await callback.answer('You dont have password or pin', show_alert=True)


@router.callback_query(F.data == "SetPassword")
async def cmd_set_password(callback: types.CallbackQuery, state: FSMContext, session: Session):
    pin_type = db_get_default_wallet(session, callback.from_user.id).use_pin
    if pin_type in (1, 2):
        await callback.answer('You have password. Remove it first', show_alert=True)
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        if await stellar_is_free_wallet(session, callback.from_user.id):
            await callback.answer('You have free account. Please buy it first.', show_alert=True)
        else:
            public_key = (await stellar_get_user_account(session, callback.from_user.id)).account.account_id
            await state.update_data(public_key=public_key)
            await cmd_show_add_wallet_choose_pin(session, callback.from_user.id, state,
                                                 my_gettext(callback, 'for_address', (public_key,)))
            await callback.answer()


async def send_private_key(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    keypair = stellar_get_user_keypair(session, user_id, pin)
    
    # Пытаемся получить сид-фразу
    seed_phrase = stellar_get_user_seed_phrase(session, user_id, pin)
    
    message = f'Your private key is <code>{keypair.secret}</code>'
    
    # Если сид-фраза существует, добавляем её в сообщение
    if seed_phrase:
        message += f'\n\nYour seed phrase is <code>{seed_phrase}</code>'
    
    await state.set_state(None)
    await send_message(session, user_id, message, reply_markup=get_kb_del_return(user_id))


@router.callback_query(F.data == "GetPrivateKey")
async def cmd_get_private_key(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if await stellar_is_free_wallet(session, callback.from_user.id):
        await cmd_buy_private_key(callback, state, session)
        # await callback.answer('You have free account. Please buy it first.')
    else:
        pin_type = db_get_default_wallet(session, callback.from_user.id).use_pin

        if pin_type == 10:
            await callback.answer('You have read only account', show_alert=True)
        else:
            await state.update_data(fsm_func=jsonpickle.dumps(send_private_key))
            await state.set_state(PinState.sign)
            await cmd_ask_pin(session, callback.from_user.id, state)
            await callback.answer()


async def cmd_after_buy(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    buy_address = data.get('buy_address')
    await send_message(session, user_id=global_data.admin_id, msg=f'{user_id} buy {buy_address}', need_new_msg=True,
                       reply_markup=get_kb_return(user_id))
    await stellar_unfree_wallet(session, user_id)


@router.callback_query(F.data == "BuyAddress")
async def cmd_buy_private_key(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if await stellar_is_free_wallet(session, callback.from_user.id):
        public_key = (await stellar_get_user_account(session, callback.from_user.id)).account.account_id
        father_key = (await stellar_get_user_account(session, 0)).account.account_id
        await state.update_data(buy_address=public_key, fsm_after_send=jsonpickle.dumps(cmd_after_buy))
        balances = await stellar_get_balances(session, callback.from_user.id)
        eurmtl_balance = 0
        for balance in balances:
            if balance.asset_code == 'EURMTL':
                eurmtl_balance = float(balance.balance)
                break
        if eurmtl_balance < config.wallet_cost:
            await callback.answer(
                f"You have free account. Please buy it first. You don't have enough money. Need {config.wallet_cost} EURMTL",
                show_alert=True)
        else:
            await callback.answer("You have free account. Please buy it first", show_alert=True)
            memo = f"{callback.from_user.id}*{public_key[len(public_key) - 4:]}"
            xdr = await stellar_pay(public_key, father_key, eurmtl_asset, config.wallet_cost, memo=memo)
            await state.update_data(xdr=xdr)
            msg = my_gettext(callback, 'confirm_send', (config.wallet_cost, eurmtl_asset.code, father_key, memo))
            msg = f"For buy {public_key}\n{msg}"

            await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    else:
        await callback.answer('You can`t buy. You have you oun account. But you can donate /donate', show_alert=True)


async def cmd_edit_address_book(session: Session, user_id: int):
    data = db_get_book_data(session, user_id)

    buttons = []
    for row in data:
        buttons.append(
            [
                types.InlineKeyboardButton(text=row.address,
                                           callback_data=AddressBookCallbackData(
                                               action='Show', idx=row.id).pack()
                                           ),
                types.InlineKeyboardButton(text=row.name,
                                           callback_data=AddressBookCallbackData(
                                               action='Show', idx=row.id).pack()
                                           ),
                types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete'),
                                           callback_data=AddressBookCallbackData(
                                               action='Delete', idx=row.id).pack()
                                           )
            ]
        )
    buttons.append(get_return_button(user_id))

    await send_message(session, user_id, my_gettext(user_id, 'address_book'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "AddressBook")
async def cb_edit_address_book(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await callback.answer()
    await state.set_state(StateAddressBook.sending_new)
    await cmd_edit_address_book(session, callback.from_user.id)


@router.message(StateAddressBook.sending_new, F.text)
async def cmd_send_for(message: types.Message, state: FSMContext, session: Session):
    await message.delete()
    if len(message.text) > 5 and message.text.find(' ') != -1:
        arr = message.text.split(' ')
        db_insert_into_address_book(session, arr[0], ' '.join(arr[1:]), message.from_user.id)
    await cmd_edit_address_book(session, message.from_user.id)


@router.callback_query(AddressBookCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: AddressBookCallbackData,
                     state: FSMContext, session: Session):
    answer = callback_data.action
    idx = callback_data.idx
    user_id = callback.from_user.id

    if answer == 'Show':
        book = db_get_address_book_by_id(session, idx, user_id)
        if book is not None:
            await callback.answer(f"{book.address}\n{book.name}"[:200], show_alert=True)

    if answer == 'Delete':
        db_delete_address_book_by_id(session, idx, user_id)
        await cmd_edit_address_book(session, user_id)

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "ManageData")
async def cmd_data_management(callback: types.CallbackQuery, state: FSMContext, session: Session):
    account_id = (await stellar_get_user_account(session, callback.from_user.id)).account.account_id
    buttons = [
        [types.InlineKeyboardButton(text='Manage Data',
                                    web_app=types.WebAppInfo(url=f'https://eurmtl.me/ManageData'
                                                                 f'?user_id={callback.from_user.id}'
                                                                 f'&message_id={callback.message.message_id}'
                                                                 f'&account_id={account_id}'))],
        [types.InlineKeyboardButton(text='Return', callback_data="Return")]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, "There you can manage your data:", reply_markup=keyboard)


@router.callback_query(MDCallbackData.filter())
async def cq_add_asset(callback: types.CallbackQuery, callback_data: MDCallbackData,
                       state: FSMContext, session: Session):
    uuid_callback = callback_data.uuid_callback
    data = await state.get_data()

    headers = {
        "Authorization": f"Bearer {config.eurmtl_key}",
        "Content-Type": "application/json"
    }
    json = {
        "uuid": uuid_callback,
        "user_id": callback.from_user.id
    }
    status, json_data = await get_web_request('POST', url=f"https://eurmtl.me/remote/get_mmwb_transaction",
                                              headers=headers, json=json, return_type='json')

    if json_data is not None:
        if 'message' in json_data:
            await callback.answer(json_data['message'], show_alert=True)
            return
        xdr = json_data['xdr']
        await state.update_data(xdr=xdr)
        msg = await get_web_decoded_xdr(xdr)
        await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback),
                           parse_mode=SULGUK_PARSE_MODE)
    else:
        await callback.answer("Error getting data", show_alert=True)

########################################################################################################################
########################################################################################################################
########################################################################################################################
