from typing import List
import jsonpickle  # type: ignore
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.ext.asyncio import AsyncSession
from sulguk import SULGUK_PARSE_MODE  # type: ignore

from other.config_reader import config

from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return, get_kb_del_return
from other.grist_tools import load_asset_from_grist
from other.mytypes import Balance
from routers.add_wallet import cmd_show_add_wallet_choose_pin
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_info_message
from infrastructure.utils.telegram_utils import send_message, my_gettext, clear_state, clear_last_message_id
from other.faststream_tools import publish_pairing_request
from other.web_tools import get_web_request, get_web_decoded_xdr
from loguru import logger

# from other.global_data import global_data
from other.lang_tools import check_user_id
from infrastructure.utils.stellar_utils import public_issuer, get_good_asset_list
from other.stellar_tools import eurmtl_asset, stellar_check_xdr
# Legacy imports removed: stellar_get_balances, stellar_add_trust, stellar_get_user_account,
# stellar_is_free_wallet, stellar_pay, stellar_get_user_keypair,
# stellar_change_password, stellar_unfree_wallet, have_free_xlm,
# stellar_get_user_seed_phrase, stellar_close_asset, stellar_has_asset_offers

# Legacy imports removed
# Imports removed/updated
from core.domain.value_objects import Asset as DomainAsset
from other.asset_visibility_tools import (
    ASSET_VISIBLE, ASSET_EXCHANGE_ONLY, ASSET_HIDDEN
)
from infrastructure.services.app_context import AppContext
from infrastructure.services.localization_service import LocalizationService



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
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext, l10n: LocalizationService):
    if callback.from_user is None:
        return
    msg = my_gettext(callback, 'wallet_setting_msg', app_context=app_context)
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    free_wallet = wallet.is_free if wallet else False
    if free_wallet:
        private_button = types.InlineKeyboardButton(text=my_gettext(callback, 'kb_buy', app_context=app_context), callback_data="BuyAddress")
    else:
        private_button = types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_key', app_context=app_context),
                                                    callback_data="GetPrivateKey")

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_manage_assets', app_context=app_context), callback_data="ManageAssetsMenu")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_address_book', app_context=app_context), callback_data="AddressBook")],
        [types.InlineKeyboardButton(text='Manage Data', callback_data="ManageData")],
        [private_button],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_password', app_context=app_context), callback_data="SetPassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_remove_password', app_context=app_context), callback_data="RemovePassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_donate', app_context=app_context), callback_data="Donate")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_default', app_context=app_context), callback_data="SetDefault")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_limit', app_context=app_context), callback_data="SetLimit")],
        [types.InlineKeyboardButton(text='🔕 ' + my_gettext(callback, 'kb_notification_settings', app_context=app_context),
                                    callback_data="NotificationSettings")],
        [types.InlineKeyboardButton(text='🌐 ' + my_gettext(callback, 'change_lang', app_context=app_context), callback_data="ChangeLang")],
        # last button
        get_return_button(callback, app_context=app_context)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard, app_context=app_context)


@router.callback_query(F.data == "ManageAssetsMenu")
async def cmd_manage_assets(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    msg = my_gettext(callback, 'manage_assets_msg', app_context=app_context)
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_delete_one', app_context=app_context), callback_data="DeleteAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_list', app_context=app_context), callback_data="AddAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_expert', app_context=app_context), callback_data="AddAssetExpert")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_asset_visibility', app_context=app_context), callback_data="AssetVisibilityMenu")],
        get_return_button(callback, app_context=app_context)
    ]
    await callback.answer()

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard, app_context=app_context)


# Helper function to generate the message text and keyboard markup
async def _generate_asset_visibility_markup(user_id: int, session: AsyncSession, app_context: AppContext, page: int = 1) -> tuple[str, types.InlineKeyboardMarkup]:
    """Generates the text and keyboard for the asset visibility menu."""
    """Generates the text and keyboard for the asset visibility menu."""
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(user_id)
    if not wallet:
        return "Wallet not found", types.InlineKeyboardMarkup(inline_keyboard=[])
    # Using UseCaseFactory
    use_case_factory = app_context.use_case_factory
    if use_case_factory is None:
        return "Internal error", types.InlineKeyboardMarkup(inline_keyboard=[])
    use_case = use_case_factory.create_get_wallet_balance(session)
    balances = await use_case.execute(user_id=user_id)

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
        if code is None:
            continue
        current_status = vis_dict.get(code, ASSET_VISIBLE)

        # Button texts with status indicators
        exchange_only_text = my_gettext(user_id, 'asset_exchange_only', app_context=app_context)
        hidden_text = my_gettext(user_id, 'asset_hidden', app_context=app_context)
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
            text="◀️ " + my_gettext(user_id, 'prev_page', app_context=app_context),
            callback_data=AssetVisibilityCallbackData(action="page", page=page - 1).pack()
        ))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(
            text=my_gettext(user_id, 'next_page', app_context=app_context) + " ▶️",
            callback_data=AssetVisibilityCallbackData(action="page", page=page + 1).pack()
        ))

    if nav_buttons:
        kb.append(nav_buttons)
        logger.info(f"Navigation buttons added: {nav_buttons}")
        logger.info(f"Total keyboard: {kb}")

    # Back button
    kb.append(get_return_button(user_id, app_context=app_context)) # Assuming get_return_button returns a list containing the button

    # Generate message text
    message_text = my_gettext(user_id, 'asset_visibility_msg', app_context=app_context)
    if total_pages > 1:
         message_text += f"\n{my_gettext(user_id, 'page', app_context=app_context)} {page}/{total_pages}"

    reply_markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    return message_text, reply_markup


@router.callback_query(F.data == "AssetVisibilityMenu")
async def cmd_asset_visibility_menu(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    """Displays the initial asset visibility settings menu."""
    user_id = callback.from_user.id
    message_text, reply_markup = await _generate_asset_visibility_markup(user_id, session, app_context, page=1)

    await callback.answer()
    await send_message(session, callback, message_text, reply_markup=reply_markup, app_context=app_context)


########################################################################################################################
########################################################################################################################
########################################################################################################################
@router.callback_query(AssetVisibilityCallbackData.filter())
async def handle_asset_visibility_action(callback: types.CallbackQuery, callback_data: AssetVisibilityCallbackData, state: FSMContext, session: AsyncSession, app_context: AppContext):
    """Handles actions from the asset visibility menu (setting status or changing page)."""
    logger.info(f"Entered handle_asset_visibility_action with callback_data: {callback_data!r}") # Log entry point
    action = callback_data.action
    page = callback_data.page # Current page when the button was clicked
    user_id = callback.from_user.id

    if action == "page":
        # Navigate to the requested page
        target_page = callback_data.page # The page number is directly in callback_data for 'page' action
        message_text, reply_markup = await _generate_asset_visibility_markup(user_id, session, app_context, page=target_page)
        try:
            if callback.message and isinstance(callback.message, types.Message):
                await callback.message.edit_text(message_text, reply_markup=reply_markup)
            await callback.answer()
        except Exception as e:
            logger.error(f"Error editing message for asset visibility page change: {e}")
            await callback.answer(my_gettext(callback, 'error_refreshing_menu', app_context=app_context), show_alert=True) # Inform user about error

    elif action == "set":
        # Set the visibility status for an asset
        # from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
        from other.asset_visibility_tools import deserialize_visibility, serialize_visibility

        repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await repo.get_default_wallet(user_id)
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
             await callback.answer(my_gettext(callback, 'error_processing_request', app_context=app_context), show_alert=True)
             return # Stop if status is invalid

        if wallet is None:
            await callback.answer(my_gettext(callback, 'error_processing_request', app_context=app_context), show_alert=True)
            return
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

        if wallet is None:
            await callback.answer(my_gettext(callback, 'error_processing_request', app_context=app_context), show_alert=True)
            return
        wallet.assets_visibility = serialize_visibility(vis_dict)
        save_error = False
        try:
            await repo.update(wallet)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Error committing asset visibility changes: {e}")
            await callback.answer(my_gettext(callback, 'error_saving_settings', app_context=app_context), show_alert=True)
            save_error = True

        if not save_error:
            # Redraw the current page of the menu to reflect the change
            message_text, reply_markup = await _generate_asset_visibility_markup(user_id, session, app_context, page=page)
            try:
                if callback.message and isinstance(callback.message, types.Message):
                    await callback.message.edit_text(message_text, reply_markup=reply_markup)
                await callback.answer(my_gettext(callback, 'asset_visibility_changed', app_context=app_context))
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    # Ignore if the message is identical (e.g. user double clicked or state didn't change visually)
                    # We still show the success toast, but no alert
                    await callback.answer(my_gettext(callback, 'asset_visibility_changed', app_context=app_context))
                else:
                    logger.error(f"TelegramBadRequest editing message after asset visibility change: {e}")
                    await callback.answer(my_gettext(callback, 'asset_visibility_changed', app_context=app_context) + " (UI update failed)", show_alert=True)
            except Exception as e:
                logger.error(f"Error editing message after asset visibility change: {e}")
                # If edit fails after save, at least inform user status was likely saved
                await callback.answer(my_gettext(callback, 'asset_visibility_changed', app_context=app_context) + " (UI update failed)", show_alert=True)

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
async def cmd_add_asset_del(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    # Refactored to use UseCaseFactory
    use_case_factory = app_context.use_case_factory
    if use_case_factory is None:
        return
    use_case = use_case_factory.create_get_wallet_balance(session)
    asset_list = await use_case.execute(user_id=callback.from_user.id)
    
    # Filter out native asset (XLM) or others if needed
    # Usually we can delete any non-native asset
    
    kb_tmp = []
    assets_to_store = []
    
    for asset in asset_list:
        if asset.asset_type == 'native':
            continue
            
        assets_to_store.append(asset)
        kb_tmp.append([types.InlineKeyboardButton(
            text=f"{asset.asset_code}",
            callback_data=DelAssetCallbackData(answer=asset.asset_code).pack()
        )])
        
    kb_tmp.append(get_return_button(callback, app_context=app_context))
    
    await state.update_data(assets=jsonpickle.encode(assets_to_store))
    
    msg = my_gettext(callback, 'delete_asset2', app_context=app_context)
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp), app_context=app_context)
    await callback.answer()


@router.callback_query(DelAssetCallbackData.filter())
async def cq_swap_choose_token_from(callback: types.CallbackQuery, callback_data: DelAssetCallbackData,
                                    state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    answer = callback_data.answer


    data = await state.get_data()


    asset_list: List[Balance] = jsonpickle.decode(data['assets'])





    asset = list(filter(lambda x: x.asset_code == answer, asset_list))


    if asset:


        asset_obj = asset[0]


        await state.update_data(send_asset_code=asset_obj.asset_code,


                                send_asset_issuer=asset_obj.asset_issuer)


        


        repo = app_context.repository_factory.get_wallet_repository(session)


        service = app_context.stellar_service


        wallet = await repo.get_default_wallet(callback.from_user.id)

        if wallet is None:
            await callback.answer(my_gettext(callback, "bad_data", app_context=app_context), show_alert=True)
            return

        offers = await service.get_selling_offers(wallet.public_key)


        has_offers = any(o['selling']['asset_code'] == asset_obj.asset_code and o['selling']['asset_issuer'] == asset_obj.asset_issuer for o in offers)


        


        if has_offers:


            await send_message(session, callback, my_gettext(callback, 'close_asset_has_offers', app_context=app_context),


                               reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)


            await callback.answer()


            return





        # Close asset = Change Trust (Limit 0)

        if asset_obj.asset_code is None or asset_obj.asset_issuer is None:
            await callback.answer(my_gettext(callback, "bad_data", app_context=app_context), show_alert=True)
            return

        tx = await service.build_change_trust_transaction(


            source_account_id=wallet.public_key,


            asset_code=asset_obj.asset_code,


            asset_issuer=asset_obj.asset_issuer,


            limit="0"


        )


        


        from routers.sign import cmd_ask_pin


        


        xdr = await stellar_check_xdr(tx)


        if xdr:


            await state.update_data(xdr=xdr)


            await cmd_ask_pin(session, callback.from_user.id, state, app_context=app_context)


            


        return


    else:


        await callback.answer(my_gettext(callback, "bad_data", app_context=app_context), show_alert=True)


        logger.info(f'error add asset {callback.from_user.id} {answer}')





    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "AddAsset")
async def cmd_add_asset_add(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    user_id = callback.from_user.id
    # Refactored to use UseCaseFactory
    repo = app_context.repository_factory.get_wallet_repository(session)
    use_case_factory = app_context.use_case_factory
    if use_case_factory is None:
        return
    balance_use_case = use_case_factory.create_get_wallet_balance(session)
    
    wallet = await repo.get_default_wallet(user_id)
    is_free = wallet.is_free if wallet else False
    
    if is_free and (len(await balance_use_case.execute(user_id=user_id)) > 5):
        await send_message(session, user_id, my_gettext(user_id, 'only_3', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        return False

    # Check free XLM
    balances = await balance_use_case.execute(user_id=user_id)
    xlm = next((a for a in balances if a.asset_code == 'XLM'), None)
    if not xlm or float(xlm.balance) <= 0.5:
        await callback.answer(my_gettext(callback, 'low_xlm', app_context=app_context), show_alert=True)
        return

    good_asset = get_good_asset_list()
    for item in await balance_use_case.execute(user_id=user_id):
        found = list(filter(lambda x: x.asset_code == item.asset_code, good_asset))
        if len(found) > 0:
            good_asset.remove(found[0])

    if len(good_asset) == 0:
        await send_message(session, user_id, my_gettext(user_id, 'have_all', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        return False

    kb_tmp = []
    for key in good_asset:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{key.asset_code}",
                                                  callback_data=AddAssetCallbackData(
                                                      answer=key.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback, app_context=app_context))
    await send_message(session, user_id, my_gettext(user_id, 'open_asset', app_context=app_context),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp), app_context=app_context)

    await state.update_data(assets=jsonpickle.encode(good_asset))


@router.callback_query(AddAssetCallbackData.filter())
async def cq_add_asset(callback: types.CallbackQuery, callback_data: AddAssetCallbackData,
                       state: FSMContext, session: AsyncSession, app_context: AppContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        if callback.message is None or not isinstance(callback.message, types.Message):
            return
        await cmd_add_asset_end(callback.message.chat.id, state, session, app_context=app_context)
    else:
        await callback.answer(my_gettext(callback, "bad_data", app_context=app_context), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "AddAssetExpert")
async def cmd_add_asset_expert(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    user_id = callback.from_user.id
    user_id = callback.from_user.id
    repo = app_context.repository_factory.get_wallet_repository(session)
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    wallet = await repo.get_default_wallet(user_id)
    is_free = wallet.is_free if wallet else False
    
    if is_free and (len(await balance_use_case.execute(user_id=user_id)) > 5):
        await send_message(session, user_id, my_gettext(user_id, 'only_3', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        return False

    # Check free XLM
    balances = await balance_use_case.execute(user_id=user_id)
    xlm = next((a for a in balances if a.asset_code == 'XLM'), None)
    if not xlm or float(xlm.balance) <= 0.5:
        await callback.answer(my_gettext(callback, 'low_xlm', app_context=app_context), show_alert=True)
        return

    await state.set_state(StateAddAsset.sending_code)
    msg = my_gettext(user_id, 'send_code', app_context=app_context)
    await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
    await callback.answer()


@router.message(StateAddAsset.sending_code)
async def cmd_sending_code(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    user_id = message.from_user.id
    asset_code = message.text
    await state.update_data(send_asset_code=asset_code)

    await state.set_state(StateAddAsset.sending_issuer)

    msg = my_gettext(user_id, 'send_issuer', (public_issuer,), app_context=app_context)
    await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)


@router.message(StateAddAsset.sending_issuer)
async def cmd_sending_issuer(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None or message.chat is None:
        return
    await state.update_data(send_asset_issuer=message.text)
    await cmd_add_asset_end(message.chat.id, state, session, app_context=app_context)


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.message(Command(commands=["start"]), F.text.contains("asset_"))
async def cmd_start_cheque(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None or message.chat is None:
        return
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading', app_context=app_context)

    # if user not exist
    if not await check_user_id(session, message.from_user.id):
        await send_message(session, message.from_user.id, 'You dont have wallet. Please run /start', app_context=app_context)
        return

    asset = message.text.split(' ')[1][6:]
    asset_code = asset.split('-')[0]
    asset_issuer = asset.split('-')[1]

    try:
        if asset_issuer == '0':
            grist_answer = await load_asset_from_grist(asset_code)
            public_key = grist_answer.issuer if grist_answer else None
        else:
            # from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
            user_repo = app_context.repository_factory.get_user_repository(session)
            public_key, user_id = await user_repo.get_account_by_username('@' + asset_issuer)

        if public_key is None:
            raise Exception("public_key is None")
    except Exception:
        await send_message(session, message.chat.id, my_gettext(message.chat.id, 'send_error2', app_context=app_context),
                           reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        return

    await state.update_data(send_asset_code=asset_code)
    await state.update_data(send_asset_issuer=public_key)
    await cmd_add_asset_end(message.chat.id, state, session, app_context=app_context)


########################################################################################################################
########################################################################################################################
########################################################################################################################


async def cmd_add_asset_end(chat_id: int, state: FSMContext, session: AsyncSession, *, app_context: AppContext):
    data = await state.get_data()
    asset_code = data.get('send_asset_code', 'EURMTL')
    asset_issuer = data.get('send_asset_issuer', '')

    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(chat_id)
    if wallet is None:
        return
    service = app_context.stellar_service

    tx = await service.build_change_trust_transaction(
             source_account_id=wallet.public_key,
             asset_code=asset_code,
             asset_issuer=asset_issuer
         )
         
    
    from routers.sign import cmd_ask_pin
    
    xdr = await stellar_check_xdr(tx)
    if xdr:
        await state.update_data(xdr=xdr)
        await cmd_ask_pin(session, chat_id, state, app_context=app_context)

    msg = my_gettext(chat_id, 'confirm_asset', (asset_code, asset_issuer), app_context=app_context)

    await state.update_data(xdr=xdr, operation='add_asset')
    await send_message(session, chat_id, msg, reply_markup=get_kb_yesno_send_xdr(chat_id, app_context=app_context), app_context=app_context)


########################################################################################################################
########################################################################################################################
########################################################################################################################

async def remove_password(session: AsyncSession, user_id: int, state: FSMContext, app_context: AppContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    data = await state.get_data()
    pin = data.get('pin', '')
    change_pw_use_case = app_context.use_case_factory.create_change_wallet_password(session)
    # user_id is passed as pin here? No, check signature
    # remove_password(session, user_id, state)
    # pin is in data['pin']. new password should be ... empty? or different logic?
    # Logic in stellar_change_password was: encrypt(key, new_password).
    # Here we are "removing" password. Meaning setting pin_type=0?
    # If pin_type=0, what is the password? Usually we decrypt with old pin then encrypt with... what?
    # If pin_type=0, maybe we don't encrypt? Just clear text?
    # Wait, SqlAlchemyWalletRepository assumes secret is encrypted?
    # If use_pin=0 (no pin), maybe secret is NOT encrypted?
    # Let's check logic.
    # If pin_type=0, maybe we store secret as is? Or default key?
    # 'stellar_change_password(session, user_id, pin, str(user_id), 0)'
    # It used `str(user_id)` as new_password.
    
    await change_pw_use_case.execute(
        user_id=user_id, 
        old_pin=pin, 
        new_pin=str(user_id), 
        pin_type=0
    )
    await state.set_state(None)
    await cmd_info_message(session, user_id, 'Password was unset', app_context=app_context)


@router.callback_query(F.data == "RemovePassword")
async def cmd_remove_password(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    # from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    pin_type = wallet.use_pin if wallet else 0
    if pin_type in (1, 2):
        await state.update_data(fsm_func=jsonpickle.dumps(remove_password))
        await state.set_state(PinState.sign)
        await cmd_ask_pin(session, callback.from_user.id, state, app_context=app_context)
        await callback.answer()
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        await callback.answer('You dont have password or pin', show_alert=True)


@router.callback_query(F.data == "SetPassword")
async def cmd_set_password(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    # from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    pin_type = wallet.use_pin if wallet else 0
    if pin_type in (1, 2):
        await callback.answer('You have password. Remove it first', show_alert=True)
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        is_free = wallet.is_free if wallet else False
        if is_free:
            await callback.answer('You have free account. Please buy it first.', show_alert=True)
        else:
            if wallet is None:
                return
            public_key = wallet.public_key
            await state.update_data(public_key=public_key)
            await cmd_show_add_wallet_choose_pin(session, callback.from_user.id, state,
                                                 my_gettext(callback, 'for_address', (public_key,), app_context=app_context),
                                                 app_context=app_context)
            await callback.answer()


async def send_private_key(session: AsyncSession, user_id: int, state: FSMContext, app_context: AppContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    secrets_use_case = app_context.use_case_factory.create_get_wallet_secrets(session)
    
    secrets = await secrets_use_case.execute(user_id, pin)
    if not secrets:
        await send_message(session, user_id, "Error: Incorrect PIN", reply_markup=get_kb_del_return(user_id, app_context=app_context), app_context=app_context)
        return

    message = f'Your private key is <code>{secrets.secret_key}</code>'
    
    # Если сид-фраза существует, добавляем её в сообщение
    if secrets.seed_phrase:
        message += f'\n\nYour seed phrase is <code>{secrets.seed_phrase}</code>'
    
    await state.set_state(None)
    await send_message(session, user_id, message, reply_markup=get_kb_del_return(user_id, app_context=app_context), app_context=app_context)


@router.callback_query(F.data == "GetPrivateKey")
async def cmd_get_private_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    is_free = wallet.is_free if wallet else False
    if is_free:
        await cmd_buy_private_key(callback, state, session, app_context=app_context)
        # await callback.answer('You have free account. Please buy it first.')
    else:
        # pin_type logic using existing wallet
        pin_type = wallet.use_pin if wallet else 0

        if pin_type == 10:
            await callback.answer('You have read only account', show_alert=True)
        else:
            await state.update_data(fsm_func=jsonpickle.dumps(send_private_key))
            await state.set_state(PinState.sign)
            await cmd_ask_pin(session, callback.from_user.id, state, app_context=app_context)
            await callback.answer()


async def cmd_after_buy(session: AsyncSession, user_id: int, state: FSMContext, *, app_context: AppContext, **kwargs):
    data = await state.get_data()
    buy_address = data.get('buy_address')
    admin_id = app_context.admin_id
    await send_message(session, user_id=admin_id, msg=f'{user_id} buy {buy_address}', need_new_msg=True,
                       reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
    
    # from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(user_id)
    if wallet:
        wallet.is_free = False
        wallet.use_pin = 0 # Also reset pin type? original 'stellar_unfree_wallet' did: db_set_free_wallet(0), db_set_pin_type(0)
        await repo.update(wallet)


@router.callback_query(F.data == "BuyAddress")
async def cmd_buy_private_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    # Check free wallet using Repo (already done?)
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    is_free = wallet.is_free if wallet else False

    if is_free:
        if wallet is None:
            return
        public_key = wallet.public_key
        father_wallet = await repo.get_default_wallet(0)
        if father_wallet is None:
            return
        father_key = father_wallet.public_key
        await state.update_data(buy_address=public_key, fsm_after_send=jsonpickle.dumps(cmd_after_buy))
        # Refactored to use UseCaseFactory
        balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
        balances = await balance_use_case.execute(user_id=callback.from_user.id)
        eurmtl_balance: float = 0.0
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
            
            
            # Send Payment
            pay_use_case = app_context.use_case_factory.create_send_payment(session)
            result = await pay_use_case.execute(
                user_id=callback.from_user.id,
                destination_address=father_key,
                amount=config.wallet_cost,
                asset=DomainAsset(code=eurmtl_asset.code, issuer=eurmtl_asset.issuer),
                memo=memo
            )
            xdr = result.xdr
            await state.update_data(xdr=xdr)
            msg = my_gettext(callback, 'confirm_send', (config.wallet_cost, eurmtl_asset.code, father_key, memo), app_context=app_context)
            msg = f"For buy {public_key}\n{msg}"

            await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback, app_context=app_context), app_context=app_context)
    else:
        await callback.answer('You can`t buy. You have you oun account. But you can donate /donate', show_alert=True)


async def cmd_edit_address_book(session: AsyncSession, user_id: int, app_context: AppContext):
    # from infrastructure.persistence.sqlalchemy_addressbook_repository import SqlAlchemyAddressBookRepository
    addressbook_repo = app_context.repository_factory.get_addressbook_repository(session)
    entries = await addressbook_repo.get_all(user_id)

    buttons = []
    for entry in entries:
        buttons.append(
            [
                types.InlineKeyboardButton(text=entry.address,
                                           callback_data=AddressBookCallbackData(
                                               action='Show', idx=entry.id).pack()
                                           ),
                types.InlineKeyboardButton(text=entry.name,
                                           callback_data=AddressBookCallbackData(
                                               action='Show', idx=entry.id).pack()
                                           ),
                types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete', app_context=app_context),
                                           callback_data=AddressBookCallbackData(
                                               action='Delete', idx=entry.id).pack()
                                           )
            ]
        )
    buttons.append(get_return_button(user_id, app_context=app_context))

    await send_message(session, user_id, my_gettext(user_id, 'address_book', app_context=app_context),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons), app_context=app_context)


@router.callback_query(F.data == "AddressBook")
async def cb_edit_address_book(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    await callback.answer()
    await state.set_state(StateAddressBook.sending_new)
    await cmd_edit_address_book(session, callback.from_user.id, app_context=app_context)


@router.message(StateAddressBook.sending_new, F.text)
async def cmd_send_for(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    await message.delete()
    if message.text is None or message.from_user is None:
        return
    if len(message.text) > 5 and message.text.find(' ') != -1:
        arr = message.text.split(' ')
        # from infrastructure.persistence.sqlalchemy_addressbook_repository import SqlAlchemyAddressBookRepository
        addressbook_repo = app_context.repository_factory.get_addressbook_repository(session)
        await addressbook_repo.create(message.from_user.id, arr[0], ' '.join(arr[1:]))
    await cmd_edit_address_book(session, message.from_user.id, app_context=app_context)


@router.callback_query(AddressBookCallbackData.filter())
async def cq_setting_address_book(callback: types.CallbackQuery, callback_data: AddressBookCallbackData,
                     state: FSMContext, session: AsyncSession, app_context: AppContext):
    # from infrastructure.persistence.sqlalchemy_addressbook_repository import SqlAlchemyAddressBookRepository
    addressbook_repo = app_context.repository_factory.get_addressbook_repository(session)
    answer = callback_data.action
    idx = callback_data.idx
    user_id = callback.from_user.id

    if answer == 'Show':
        book = await addressbook_repo.get_by_id(idx, user_id)
        if book is not None:
            await callback.answer(f"{book.address}\n{book.name}"[:200], show_alert=True)

    if answer == 'Delete':
        await addressbook_repo.delete(idx, user_id)
        await cmd_edit_address_book(session, user_id, app_context=app_context)

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "ManageData")
async def cmd_data_management(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None or callback.message is None:
        return
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    if not wallet:
        return
    account_id = wallet.public_key
    buttons = [
        [types.InlineKeyboardButton(text='Manage Data',
                                    web_app=types.WebAppInfo(url=f'https://eurmtl.me/ManageData'
                                                                 f'?user_id={callback.from_user.id}'
                                                                 f'&message_id={callback.message.message_id}'
                                                                 f'&account_id={account_id}'))],
        [types.InlineKeyboardButton(text='Return', callback_data="Return")]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, "There you can manage your data:", reply_markup=keyboard, app_context=app_context)


@router.callback_query(MDCallbackData.filter())
async def cq_manage_data_callback(callback: types.CallbackQuery, callback_data: MDCallbackData,
                       state: FSMContext, session: AsyncSession, app_context: AppContext):
    uuid_callback = callback_data.uuid_callback

    headers = {
        "Authorization": f"Bearer {config.eurmtl_key}",
        "Content-Type": "application/json"
    }
    json_payload = {
        "uuid": uuid_callback,
        "user_id": callback.from_user.id
    }
    status, json_data = await get_web_request('POST', url="https://eurmtl.me/remote/get_mmwb_transaction",
                                              headers=headers, json=json_payload, return_type='json')

    if json_data is not None:
        if 'message' in json_data:
            await callback.answer(json_data['message'], show_alert=True)
            return
        xdr = json_data['xdr']
        await state.update_data(xdr=xdr)
        msg = await get_web_decoded_xdr(xdr)
        await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback, app_context=app_context),
                           parse_mode=SULGUK_PARSE_MODE, app_context=app_context)
    else:
        await callback.answer("Error getting data", show_alert=True)


async def handle_wc_uri(wc_uri: str, user_id: int, session: AsyncSession, state: FSMContext, app_context: AppContext):
    """Helper function to process WalletConnect URI"""
    await clear_state(state)
    await clear_last_message_id(user_id, app_context=app_context)
    # Get user's default address
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(user_id)

    if wallet:
        address = wallet.public_key
        try:
            user_info = {
                "user_id": user_id,
                "address": address
            }
            await publish_pairing_request(wc_uri, address, user_info)
            await send_message(
                session,
                user_id,
                my_gettext(user_id, 'wc_pairing_initiated', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context
            )
        except Exception as e:
            logger.error(f"Failed to publish WC pairing request for user {user_id}: {e}")
            await send_message(
                session,
                user_id,
                my_gettext(user_id, 'wc_pairing_error', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context
            )
    else:
        await send_message(
            session,
            user_id,
            my_gettext(user_id, 'default_wallet_not_found', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context
        )
