import uuid
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy.orm import Session
from stellar_sdk.sep import stellar_uri
from stellar_sdk import Network, TransactionBuilder

from other.aiogram_tools import my_gettext, send_message, clear_state
from other.stellar_tools import (
    stellar_user_sign, stellar_get_user_account, process_uri_with_replace,
    parse_transaction_stellar_uri, process_transaction_stellar_uri
)
from routers.sign import cmd_check_xdr
from keyboards.common_keyboards import get_kb_yesno_send_xdr, get_kb_send
from other.web_tools import http_session_manager

router = Router()
router.message.filter(F.chat.type == "private")

async def process_remote_uri(session: Session, chat_id: int, uri_id: str, state: FSMContext):
    """Get URI from server and prepare for signing"""
    # Get URI from server
    try:
        response = await http_session_manager.get_web_request(
            'GET',
            url=f"https://eurmtl.me/remote/sep07/get/{uri_id}"
        )

        if response.status != 200:
            await send_message(session, chat_id, my_gettext(chat_id, 'remote_uri_error'))
            return

        # Process the URI
        uri_data = response.data['uri']
        result = await process_transaction_stellar_uri(uri_data, session, chat_id)

        # Save data for state
        await state.update_data(
            xdr=result['xdr'],
            uri_id=uri_id,
            last_message_id=0,
            callback_url=result['callback_url'],
            return_url=result.get('return_url')
        )

        # Process XDR
        await cmd_check_xdr(
            session=session,
            check_xdr=result['xdr'],
            user_id=chat_id,
            state=state
        )
    except Exception as e:
        await send_message(
            session,
            chat_id,
            my_gettext(chat_id, 'remote_uri_error', (str(e),))
        )

@router.message(Command(commands=["start"]), F.text.contains("uri_"))
async def cmd_start_remote(message: types.Message, state: FSMContext, session: Session):
    """Handle Telegram bot start with remote URI"""
    await clear_state(state)
    uri_id = message.text.split()[1][4:]  # Extract ID from "uri_..."
    await process_remote_uri(session, message.from_user.id, uri_id, state)

@router.message(F.text.startswith("web+stellar:tx"))
async def process_stellar_uri(message: types.Message, state: FSMContext, session: Session):
    """Handle direct Stellar URI with optional encoded params"""
    uri = message.text
    if '?' in uri:
        from urllib.parse import unquote
        base, params = uri.split('?', 1)
        uri = f"{base}?{unquote(params)}"
    await clear_state(state)
    qr_data = message.text
    
    try:
        # Process the transaction URI
        result = await process_transaction_stellar_uri(
            qr_data,
            session,
            message.from_user.id,
            Network.PUBLIC_NETWORK_PASSPHRASE
        )
        
        # Save data for state
        await state.update_data(
            xdr=result['xdr'],
            last_message_id=0,
            callback_url=result['callback_url'],
            return_url=result.get('return_url')
        )
        
        # Process XDR
        await cmd_check_xdr(
            session=session,
            check_xdr=result['xdr'],
            user_id=message.from_user.id,
            state=state
        )
    except Exception as e:
        await send_message(
            session,
            message.from_user.id,
            my_gettext(message.from_user.id, 'remote_uri_error', (str(e),))
        )
