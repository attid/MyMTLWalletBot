import base64
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import fakeredis.aioredis
from aiogram import types
from aiogram.fsm.storage.base import StorageKey
from stellar_sdk import Keypair

from infrastructure.services.stellar_sealedbox_service import StellarSealedBoxService
from core.domain.entities import Wallet
from core.interfaces.repositories import IWalletRepository
from routers.sealedbox import (
    SealedBoxState,
    _requested_output_filename,
    _resolve_output_filename,
    _short_address,
    _LimitedBytesIO,
    router as sealedbox_router,
)
from routers.sign import PinState, router as sign_router
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)
from other import faststream_tools
from shared.constants import REDIS_SEALEDBOX_PREFIX


def _latest_screen(mock_telegram: list[dict]) -> dict:
    screens = [
        request
        for request in mock_telegram
        if request["method"] in ("sendMessage", "editMessageText")
    ]
    return screens[-1]


def _deleted_message_ids(mock_telegram: list[dict]) -> set[int]:
    return {
        int(request["data"]["message_id"])
        for request in mock_telegram
        if request["method"] == "deleteMessage"
    }


@pytest.fixture(autouse=True)
def detach_router():
    yield
    if sealedbox_router.parent_router:
        sealedbox_router._parent_router = None
    if sign_router.parent_router:
        sign_router._parent_router = None


@pytest.fixture
def sealedbox_context(router_app_context):
    router_app_context.stellar_sealedbox_service = StellarSealedBoxService()
    router_app_context.signing_facade = None
    addressbook_repo = AsyncMock()
    addressbook_repo.get_all.return_value = []
    router_app_context.repository_factory.get_addressbook_repository.return_value = (
        addressbook_repo
    )
    return router_app_context


@pytest.mark.asyncio
async def test_menu_offers_encrypt_decrypt_settings_back_and_home(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)

    await dp.feed_update(
        sealedbox_context.bot, create_callback_update(123, "SealedBoxMenu")
    )

    markup = _latest_screen(mock_telegram)["data"]["reply_markup"]
    assert "SealedBoxEncrypt" in markup
    assert "SealedBoxDecrypt" in markup
    assert "SealedBoxBack:settings" in markup
    assert '"callback_data": "Return"' in markup


@pytest.mark.asyncio
async def test_menu_back_returns_to_wallet_settings(
    mock_telegram, sealedbox_context
) -> None:
    wallet = MagicMock(spec=Wallet)
    wallet.is_free = True
    wallet_repo = MagicMock(spec=IWalletRepository)
    wallet_repo.get_default_wallet = AsyncMock(return_value=wallet)
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    dp = sealedbox_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(123, "SealedBoxBack:settings"),
    )

    screen = _latest_screen(mock_telegram)
    assert screen["data"]["text"] == "wallet_setting_msg"
    assert "SealedBoxMenu" in screen["data"]["reply_markup"]


@pytest.mark.asyncio
async def test_opening_menu_from_callback_edits_current_screen(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    user_id = 123
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(key, {"last_message_id": 1})

    await dp.feed_update(
        sealedbox_context.bot, create_callback_update(user_id, "SealedBoxMenu")
    )

    assert get_telegram_request(mock_telegram, "editMessageText") is not None
    assert get_telegram_request(mock_telegram, "sendMessage") is None


@pytest.mark.asyncio
async def test_crypto_command_opens_menu_and_deletes_command(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)

    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(123, "/crypto", message_id=8),
    )

    assert 8 in _deleted_message_ids(mock_telegram)
    assert _latest_screen(mock_telegram)["data"]["text"] == "sealedbox_menu"


@pytest.mark.asyncio
async def test_encrypts_text_for_manually_entered_recipient(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    user_id = 123
    recipient = Keypair.from_raw_ed25519_seed(bytes([4]) * 32)
    sealedbox_context.localization_service.get_text.side_effect = (
        lambda _user_id, key_name, params=(): (
            f"{key_name} {params[0]}" if params else key_name
        )
    )
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxEncrypt"),
    )
    assert await dp.storage.get_state(key) == SealedBoxState.recipient

    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, recipient.public_key, update_id=2, message_id=2),
    )
    assert await dp.storage.get_state(key) == SealedBoxState.encrypt_content
    assert (
        _short_address(recipient.public_key)
        in _latest_screen(mock_telegram)["data"]["text"]
    )

    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, "secret text", update_id=3, message_id=3),
    )

    request = get_telegram_request(mock_telegram, "sendDocument")
    assert request is not None
    assert "message.txt.ssb" in str(request["data"])
    assert "sealedbox_encrypted_for" in request["data"]["caption"]
    assert _short_address(recipient.public_key) in request["data"]["caption"]
    assert "<code>" in request["data"]["caption"]
    assert '"callback_data": "Return"' in request["data"]["reply_markup"]
    assert 1 in _deleted_message_ids(mock_telegram)
    assert {2, 3}.issubset(_deleted_message_ids(mock_telegram))
    assert await dp.storage.get_state(key) is None


@pytest.mark.asyncio
async def test_large_encrypted_text_uses_document_caption_without_base64(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    recipient = Keypair.random().public_key
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key, SealedBoxState.encrypt_content)
    await dp.storage.update_data(key, {"sealedbox_recipient": recipient})

    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, "x" * 1000, message_id=10),
    )

    request = get_telegram_request(mock_telegram, "sendDocument")
    assert request is not None
    assert "<code>" not in request["data"]["caption"]


@pytest.mark.asyncio
async def test_encrypt_document_is_downloaded_before_source_message_is_deleted(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    recipient = Keypair.random().public_key
    plaintext = b"document bytes"

    async def download(_document, destination):
        assert 4 not in _deleted_message_ids(mock_telegram)
        destination.write(plaintext)
        return destination

    sealedbox_context.bot.download = AsyncMock(side_effect=download)
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key, SealedBoxState.encrypt_content)
    await dp.storage.update_data(
        key, {"sealedbox_recipient": recipient, "last_message_id": 77}
    )

    await dp.feed_update(
        sealedbox_context.bot,
        _document_update(user_id, file_name="report.pdf", file_size=14, update_id=4),
    )

    assert 4 in _deleted_message_ids(mock_telegram)
    assert 77 in _deleted_message_ids(mock_telegram)
    result = get_telegram_request(mock_telegram, "sendDocument")
    assert result is not None
    assert '"callback_data": "Return"' in result["data"]["reply_markup"]
    assert await dp.storage.get_state(key) is None
    tracked_message_id = (await dp.storage.get_data(key))["last_message_id"]
    assert tracked_message_id > 0
    assert tracked_message_id != 77


@pytest.mark.asyncio
async def test_encrypt_content_back_returns_to_recipient_selection(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    user_id = 123
    recipient = Keypair.random().public_key
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxEncrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, recipient, update_id=2, message_id=2),
    )

    markup = _latest_screen(mock_telegram)["data"]["reply_markup"]
    assert "SealedBoxBack:recipient" in markup

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxBack:recipient", update_id=3),
    )

    assert await dp.storage.get_state(key) == SealedBoxState.recipient
    assert _latest_screen(mock_telegram)["data"]["text"] == "sealedbox_choose_recipient"


@pytest.mark.asyncio
async def test_recipient_prompt_uses_send_inline_chooser_without_address_buttons(
    mock_telegram, sealedbox_context
) -> None:
    repo = sealedbox_context.repository_factory.get_addressbook_repository.return_value
    repo.get_all.return_value = [
        MagicMock(id=7, name="Alice", address=Keypair.random().public_key)
    ]
    dp = sealedbox_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(123, "SealedBoxEncrypt"),
    )

    markup = _latest_screen(mock_telegram)["data"]["reply_markup"]
    assert '"switch_inline_query_current_chat": ""' in markup
    assert "SealedBoxRecipient:" not in markup
    repo.get_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_recipient_message_is_deleted(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    user_id = 123
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key, SealedBoxState.recipient)

    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, "not-an-address", message_id=9),
    )

    assert 9 in _deleted_message_ids(mock_telegram)


@pytest.mark.asyncio
async def test_encrypt_content_error_goes_back_to_recipient_selection(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    user_id = 123

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxEncrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(
            user_id, Keypair.random().public_key, update_id=2, message_id=2
        ),
    )
    unsupported = types.Update(
        update_id=3,
        message=types.Message(
            message_id=3,
            date=datetime.datetime.now(),
            chat=types.Chat(id=user_id, type="private"),
            from_user=types.User(id=user_id, is_bot=False, first_name="Test"),
        ),
    )

    await dp.feed_update(sealedbox_context.bot, unsupported)

    assert 3 in _deleted_message_ids(mock_telegram)
    assert (
        "SealedBoxBack:recipient"
        in _latest_screen(mock_telegram)["data"]["reply_markup"]
    )


def _document_update(
    user_id: int, *, file_name: str, file_size: int, update_id: int = 3
) -> types.Update:
    return types.Update(
        update_id=update_id,
        message=types.Message(
            message_id=update_id,
            date=datetime.datetime.now(),
            chat=types.Chat(id=user_id, type="private"),
            from_user=types.User(id=user_id, is_bot=False, first_name="Test"),
            document=types.Document(
                file_id="cipher-file",
                file_unique_id="cipher-unique",
                file_name=file_name,
                file_size=file_size,
            ),
        ),
    )


def test_generic_output_name_is_selected_after_decryption() -> None:
    requested = _requested_output_filename("sealedbox.ssb")

    assert requested == ""
    assert (
        _resolve_output_filename(requested, "hello".encode()) == "sealedbox-output.txt"
    )
    assert _resolve_output_filename(requested, b"\xff\x00") == "sealedbox-output.bin"
    assert _requested_output_filename("report.pdf.ssb") == "report.pdf"


def test_document_buffer_rejects_bytes_past_the_limit() -> None:
    destination = _LimitedBytesIO(3)
    destination.write(b"abc")

    with pytest.raises(ValueError):
        destination.write(b"d")


@pytest.mark.asyncio
async def test_decrypts_with_current_no_pin_wallet(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    keypair = Keypair.from_raw_ed25519_seed(bytes([6]) * 32)
    ciphertext = await sealedbox_context.stellar_sealedbox_service.encrypt(
        999, keypair.public_key, b"pdf bytes"
    )
    wallet = MagicMock(public_key=keypair.public_key, use_pin=0)
    wallet_repo = AsyncMock()
    wallet_repo.get_default_wallet.return_value = wallet
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    secrets = MagicMock(secret_key=keypair.secret)
    get_secrets = AsyncMock()
    get_secrets.execute.return_value = secrets
    sealedbox_context.use_case_factory.create_get_wallet_secrets.return_value = (
        get_secrets
    )

    async def download(_document, destination):
        assert 3 not in _deleted_message_ids(mock_telegram)
        destination.write(ciphertext)
        destination.seek(0)
        return destination

    sealedbox_context.bot.download = AsyncMock(side_effect=download)
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxDecrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        _document_update(
            user_id,
            file_name="report.pdf.ssb",
            file_size=len(ciphertext),
        ),
    )

    get_secrets.execute.assert_awaited_once_with(user_id, str(user_id))
    request = get_telegram_request(mock_telegram, "sendDocument")
    assert request is not None
    assert "report.pdf" in str(request["data"])
    assert '"callback_data": "Return"' in request["data"]["reply_markup"]
    assert 3 in _deleted_message_ids(mock_telegram)
    assert (
        await dp.storage.get_state(
            StorageKey(
                bot_id=sealedbox_context.bot.id,
                chat_id=user_id,
                user_id=user_id,
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_decrypts_base64_ciphertext_sent_as_text(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    keypair = Keypair.from_raw_ed25519_seed(bytes([7]) * 32)
    ciphertext = await sealedbox_context.stellar_sealedbox_service.encrypt(
        999, keypair.public_key, b"decrypted text"
    )
    wallet_repo = AsyncMock()
    wallet_repo.get_default_wallet.return_value = MagicMock(
        public_key=keypair.public_key, use_pin=0
    )
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    get_secrets = AsyncMock()
    get_secrets.execute.return_value = MagicMock(secret_key=keypair.secret)
    sealedbox_context.use_case_factory.create_get_wallet_secrets.return_value = (
        get_secrets
    )
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxDecrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(
            user_id,
            base64.b64encode(ciphertext).decode("ascii"),
            update_id=2,
            message_id=2,
        ),
    )

    result = get_telegram_request(mock_telegram, "sendDocument")
    assert result is not None
    assert "sealedbox-output.txt" in str(result["data"])
    assert 2 in _deleted_message_ids(mock_telegram)


@pytest.mark.asyncio
async def test_read_only_wallet_hands_ciphertext_to_owner_bound_webapp(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    wallet = MagicMock(public_key=Keypair.random().public_key, use_pin=10)
    wallet_repo = AsyncMock()
    wallet_repo.get_default_wallet.return_value = wallet
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    ciphertext = b"x" * 64

    async def download(_document, destination):
        destination.write(ciphertext)
        destination.seek(0)
        return destination

    sealedbox_context.bot.download = AsyncMock(side_effect=download)
    redis = fakeredis.aioredis.FakeRedis()
    old_redis = faststream_tools.REDIS_CLIENT
    faststream_tools.REDIS_CLIENT = redis
    try:
        dp = sealedbox_context.dispatcher
        dp.message.middleware(RouterTestMiddleware(sealedbox_context))
        dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
        dp.include_router(sealedbox_router)

        await dp.feed_update(
            sealedbox_context.bot,
            create_callback_update(user_id, "SealedBoxDecrypt"),
        )
        await dp.feed_update(
            sealedbox_context.bot,
            _document_update(
                user_id, file_name="report.pdf.ssb", file_size=len(ciphertext)
            ),
        )

        screen = _latest_screen(mock_telegram)
        assert "/sealedbox?token=" in screen["data"]["reply_markup"]
        keys = await redis.keys(f"{REDIS_SEALEDBOX_PREFIX}*")
        assert len(keys) == 1

        await dp.feed_update(
            sealedbox_context.bot,
            create_callback_update(user_id, "SealedBoxBack:decrypt_file", update_id=4),
        )

        assert not await redis.keys(f"{REDIS_SEALEDBOX_PREFIX}*")
    finally:
        faststream_tools.REDIS_CLIENT = old_redis
        await redis.aclose()


@pytest.mark.asyncio
async def test_password_wallet_waits_for_password_before_decrypting(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    keypair = Keypair.from_raw_ed25519_seed(bytes([8]) * 32)
    ciphertext = await sealedbox_context.stellar_sealedbox_service.encrypt(
        999, keypair.public_key, b"protected"
    )
    wallet = MagicMock(public_key=keypair.public_key, use_pin=2)
    wallet_repo = AsyncMock()
    wallet_repo.get_default_wallet.return_value = wallet
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    get_secrets = AsyncMock()
    get_secrets.execute.return_value = MagicMock(secret_key=keypair.secret)
    sealedbox_context.use_case_factory.create_get_wallet_secrets.return_value = (
        get_secrets
    )

    async def download(_document, destination):
        destination.write(ciphertext)
        return destination

    sealedbox_context.bot.download = AsyncMock(side_effect=download)
    sealedbox_context.stellar_service.get_user_account = AsyncMock(
        return_value=MagicMock(account=MagicMock(account_id=keypair.public_key))
    )
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_routers(sealedbox_router, sign_router)
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(key, {"user_lang": "en"})

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxDecrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        _document_update(user_id, file_name="file.bin.ssb", file_size=len(ciphertext)),
    )
    assert await dp.storage.get_state(key) == PinState.ask_password
    assert get_telegram_request(mock_telegram, "sendDocument") is None

    markup = _latest_screen(mock_telegram)["data"]["reply_markup"]
    assert '"callback_data": "Return"' in markup
    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, "hunter2", update_id=4, message_id=4),
    )

    get_secrets.execute.assert_awaited_once_with(user_id, "hunter2")
    assert get_telegram_request(mock_telegram, "sendDocument") is not None
    assert {3, 4}.issubset(_deleted_message_ids(mock_telegram))
    assert await dp.storage.get_state(key) is None


@pytest.mark.asyncio
async def test_pin_wallet_uses_shared_signing_keyboard(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    keypair = Keypair.from_raw_ed25519_seed(bytes([9]) * 32)
    ciphertext = await sealedbox_context.stellar_sealedbox_service.encrypt(
        999, keypair.public_key, b"protected"
    )
    wallet_repo = AsyncMock()
    wallet_repo.get_default_wallet.return_value = MagicMock(
        public_key=keypair.public_key, use_pin=1
    )
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    sealedbox_context.stellar_service.get_user_account = AsyncMock(
        return_value=MagicMock(account=MagicMock(account_id=keypair.public_key))
    )

    async def download(_document, destination):
        destination.write(ciphertext)
        return destination

    sealedbox_context.bot.download = AsyncMock(side_effect=download)
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_routers(sealedbox_router, sign_router)
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(key, {"user_lang": "en"})

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxDecrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        _document_update(user_id, file_name="file.bin.ssb", file_size=len(ciphertext)),
    )

    assert await dp.storage.get_state(key) == PinState.sign
    markup = _latest_screen(mock_telegram)["data"]["reply_markup"]
    assert '"callback_data": "pin_:1"' in markup
    assert '"callback_data": "pin_:Enter"' in markup


@pytest.mark.asyncio
async def test_invalid_text_decrypt_input_is_deleted(
    mock_telegram, sealedbox_context
) -> None:
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_router(sealedbox_router)
    user_id = 123
    key = StorageKey(bot_id=sealedbox_context.bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.set_state(key, SealedBoxState.decrypt_file)

    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, "not-base64", message_id=11),
    )

    assert 11 in _deleted_message_ids(mock_telegram)
    assert _latest_screen(mock_telegram)["data"]["text"] == "sealedbox_decrypt_failed"


@pytest.mark.asyncio
async def test_bad_wallet_password_goes_back_to_file_selection(
    mock_telegram, sealedbox_context
) -> None:
    user_id = 123
    wallet = MagicMock(public_key=Keypair.random().public_key, use_pin=2)
    wallet_repo = AsyncMock()
    wallet_repo.get_default_wallet.return_value = wallet
    sealedbox_context.repository_factory.get_wallet_repository.return_value = (
        wallet_repo
    )
    get_secrets = AsyncMock()
    get_secrets.execute.return_value = None
    sealedbox_context.use_case_factory.create_get_wallet_secrets.return_value = (
        get_secrets
    )

    async def download(_document, destination):
        destination.write(b"x" * 64)
        return destination

    sealedbox_context.bot.download = AsyncMock(side_effect=download)
    sealedbox_context.stellar_service.get_user_account = AsyncMock(
        return_value=MagicMock(account=MagicMock(account_id=wallet.public_key))
    )
    dp = sealedbox_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(sealedbox_context))
    dp.callback_query.middleware(RouterTestMiddleware(sealedbox_context))
    dp.include_routers(sealedbox_router, sign_router)

    await dp.feed_update(
        sealedbox_context.bot,
        create_callback_update(user_id, "SealedBoxDecrypt"),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        _document_update(user_id, file_name="file.ssb", file_size=64),
    )
    await dp.feed_update(
        sealedbox_context.bot,
        create_message_update(user_id, "wrong", update_id=4, message_id=4),
    )

    assert (
        "SealedBoxBack:decrypt_file"
        in _latest_screen(mock_telegram)["data"]["reply_markup"]
    )
