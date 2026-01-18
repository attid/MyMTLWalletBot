import uuid
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy.orm import Session
from stellar_sdk.sep import stellar_uri
from stellar_sdk import Network, TransactionBuilder

from infrastructure.utils.telegram_utils import my_gettext, send_message, clear_state, clear_last_message_id
from other.stellar_tools import stellar_user_sign, stellar_get_user_account
from core.use_cases.stellar.process_uri import ProcessStellarUri
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.services.stellar_service import StellarService
from routers.sign import cmd_check_xdr
from keyboards.common_keyboards import get_kb_yesno_send_xdr, get_kb_send, get_kb_return
from other.web_tools import http_session_manager

from other.faststream_tools import publish_pairing_request
from infrastructure.services.app_context import AppContext

router = Router()
router.message.filter(F.chat.type == "private")


async def process_remote_uri(session: Session, chat_id: int, uri_id: str, state: FSMContext, app_context: AppContext):
    """Get URI from server and prepare for signing"""
    # Get URI from server
    try:
        response = await http_session_manager.get_web_request(
            'GET',
            url=f"https://eurmtl.me/remote/sep07/get/{uri_id}"
        )

        if response.status != 200:
            await send_message(session, chat_id, my_gettext(chat_id, 'remote_uri_error', app_context=app_context))
            return

        # Process the URI
        uri_data = response.data['uri']
        
        # Initialize repositories and services
        wallet_repo = SqlAlchemyWalletRepository(session)
        stellar_service = StellarService()
        process_uri_uc = ProcessStellarUri(wallet_repo, stellar_service)
        
        # Process the URI
        result = await process_uri_uc.execute(uri_data, chat_id)

        # Save data for state
        await state.update_data(
            xdr=result.xdr,
            uri_id=uri_id,
            last_message_id=0,
            callback_url=result.callback_url,
            return_url=result.return_url
        )

        # Process XDR
        await cmd_check_xdr(
            session=session,
            check_xdr=result.xdr,
            user_id=chat_id,
            state=state,
            app_context=app_context
        )
    except Exception as e:
        await send_message(
            session,
            chat_id,
            my_gettext(chat_id, 'remote_uri_error', (str(e),), app_context=app_context)
        )


@router.message(Command(commands=["start"]), F.text.contains("uri_"))
async def cmd_start_remote(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    """Handle Telegram bot start with remote URI"""
    await clear_state(state)
    uri_id = message.text.split()[1][4:]  # Extract ID from "uri_..."
    await process_remote_uri(session, message.from_user.id, uri_id, state, app_context=app_context)


@router.message(F.text.startswith("web+stellar:tx"))
async def process_stellar_uri(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    """Handle direct Stellar URI with optional encoded params"""
    uri = message.text
    if '?' in uri:
        from urllib.parse import unquote
        base, params = uri.split('?', 1)
        uri = f"{base}?{unquote(params)}"
    await clear_state(state)
    qr_data = message.text

    try:
        # Initialize repositories and services
        wallet_repo = SqlAlchemyWalletRepository(session)
        stellar_service = StellarService()
        process_uri_uc = ProcessStellarUri(wallet_repo, stellar_service)
        
        # Process the transaction URI
        result = await process_uri_uc.execute(qr_data, message.from_user.id)

        # Save data for state
        await state.update_data(
            xdr=result.xdr,
            last_message_id=0,
            callback_url=result.callback_url,
            return_url=result.return_url
        )

        # Process XDR
        await cmd_check_xdr(
            session=session,
            check_xdr=result.xdr,
            user_id=message.from_user.id,
            state=state,
            app_context=app_context
        )
    except Exception as e:
        await send_message(
            session,
            message.from_user.id,
            my_gettext(message.from_user.id, 'remote_uri_error', (str(e),), app_context=app_context)
        )


async def handle_wc_uri(wc_uri: str, user_id: int, session: Session, state: FSMContext, app_context: AppContext):
    """Helper function to process WalletConnect URI"""
    await clear_state(state)
    await clear_last_message_id(user_id)
    # Get user's default address
    user_account = await stellar_get_user_account(session, user_id)

    if user_account:
        address = user_account.account.account_id
        try:
            user_info = {
                "user_id": user_id,
                "address": address
            }
            await publish_pairing_request(wc_uri, address, user_info)
            await send_message(
                session,
                user_id,
                my_gettext(user_id, 'wc_pairing_initiated', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context)
            )
        except Exception as e:
            logger.error(f"Failed to publish WC pairing request for user {user_id}: {e}")
            await send_message(
                session,
                user_id,
                my_gettext(user_id, 'wc_pairing_error', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context)
            )
    else:
        await send_message(
            session,
            user_id,
            my_gettext(user_id, 'default_wallet_not_found', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context)
        )


@router.message(F.text.startswith("wc:"))
async def process_wc_uri(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    """Handle WalletConnect URI from text message"""
    await handle_wc_uri(message.text, message.from_user.id, session, state, app_context=app_context)
    await message.delete()
