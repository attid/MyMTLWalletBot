import json
import pytest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import fakeredis.aioredis

from aiogram.fsm.storage.base import StorageKey
from core.constants import PUBLIC_ISSUER
from core.domain.value_objects import Balance
from infrastructure.services.receive_history_store import (
    HistoryAmount,
    ReceiveHistoryStore,
)
from other import faststream_tools
from routers.receive import (
    router as receive_router,
    create_beautiful_code,
    create_invoice_qr,
    _build_pay_uri,
    ReceiveInvoiceStates,
    RECEIVE_INVOICE_CALLBACK,
    RECEIVE_HIST_CALLBACK,
    RECEIVE_ASSET_CALLBACK,
    RECEIVE_CHANGE_AMOUNT_CALLBACK,
    RECEIVE_CHANGE_ASSET_CALLBACK,
)
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    create_message_update,
    get_telegram_request,
)


@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if receive_router.parent_router:
        receive_router._parent_router = None


@pytest.fixture
def setup_receive_mocks(router_app_context):
    """
    Common mock setup for receive router tests.
    """

    class ReceiveMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            # Default wallet mock
            self.wallet = MagicMock()
            self.wallet.public_key = (
                "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            )

            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

    return ReceiveMockHelper(router_app_context)


@pytest.mark.asyncio
async def test_cmd_receive_callback(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    monkeypatch,
    tmp_path,
):
    """
    Test Receive callback: should show QR code and address info.
    NO PATCH for cmd_info_message - integration test according to README.md
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    test_address = setup_receive_mocks.wallet.public_key
    monkeypatch.chdir(tmp_path)
    qr_path = Path("qr") / f"{test_address}.png"

    update = create_callback_update(user_id=user_id, callback_data="Receive")

    # Run handler through dispatcher (Live interaction simulation)
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    # 1. Verify delivery does not depend on a runtime QR directory.
    assert not qr_path.exists()

    # 2. Verify answerCallbackQuery was called
    req_answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert req_answer is not None

    # 3. Verify sendPhoto was called (cmd_info_message -> bot.send_photo)
    req_photo = get_telegram_request(mock_telegram, "sendPhoto")
    assert req_photo is not None
    assert str(user_id) == str(req_photo["data"]["chat_id"])
    # caption can be multipart or urlencoded depending on bot version, mock_server captures it
    assert "my_address" in str(req_photo["data"].get("caption", ""))
    # 4. Invoice button is offered next to ManageAssets
    reply_markup = str(req_photo["data"].get("reply_markup", ""))
    assert RECEIVE_INVOICE_CALLBACK in reply_markup
    assert "ManageAssetsMenu" in reply_markup


def test_create_beautiful_code():
    """Unit test for QR code generation."""
    from PIL import Image

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    qr_buffer = BytesIO()

    create_beautiful_code(qr_buffer, test_address)

    with Image.open(qr_buffer) as img:
        assert img.format == "PNG"
        assert img.mode == "RGB"
        assert img.size[0] > 100


def test_create_qr_logic_components():
    """Test internal image helpers in receive.py."""
    from routers.receive import create_qr_with_logo, create_image_with_text
    from PIL import Image

    test_address = "GD45..XI"
    logo = create_image_with_text(test_address)
    assert isinstance(logo, Image.Image)

    qr = create_qr_with_logo(test_address, logo)
    assert isinstance(qr, Image.Image)
    assert qr.mode == "RGB"


# --- Invoice ("Выставить счёт") flow ---

ISSUER = PUBLIC_ISSUER


@pytest.fixture
async def receive_history_redis():
    """fakeredis под глобальным REDIS_CLIENT (паттерн test_sign.py)."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    old_redis = faststream_tools.REDIS_CLIENT
    faststream_tools.REDIS_CLIENT = redis
    yield redis
    faststream_tools.REDIS_CLIENT = old_redis
    await redis.aclose()


def _capture_invoice_photos(router_app_context, monkeypatch) -> list[bytes]:
    """Перехватываем payload фото до HTTP: mock-сервер хранит только attach://."""
    captures: list[bytes] = []
    original = router_app_context.bot.send_photo

    async def spy_send_photo(chat_id, photo=None, **kwargs):
        raw = getattr(photo, "data", None) or getattr(photo, "file", None)
        if isinstance(raw, bytes):
            captures.append(raw)
        elif hasattr(raw, "read"):
            captures.append(raw.read())
        return await original(chat_id, photo=photo, **kwargs)

    monkeypatch.setattr(router_app_context.bot, "send_photo", spy_send_photo)
    return captures


def _decode_invoice_qr(payload: bytes) -> str:
    from PIL import Image, ImageOps
    from pyzbar.pyzbar import decode as pyzbar_decode

    img = Image.open(BytesIO(payload)).convert("L")
    result = pyzbar_decode(ImageOps.autocontrast(img))
    assert result, "QR на фото не декодировался"
    return result[0].data.decode()


def test_build_pay_uri():
    address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    assert _build_pay_uri(address, "10", "EURMTL", ISSUER) == (
        "web+stellar:pay?destination=GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
        f"&amount=10&asset_code=EURMTL&asset_issuer={ISSUER}"
    )
    # XLM без эмитента: asset_issuer не добавляется
    assert "asset_issuer" not in _build_pay_uri(address, "2.5", "XLM", None)


def test_create_invoice_qr_decodes_to_uri():
    from PIL import Image

    address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    uri = _build_pay_uri(address, "10", "EURMTL", ISSUER)
    buffer = BytesIO()
    create_invoice_qr(buffer, uri, "10 EURMTL")
    with Image.open(buffer) as img:
        assert img.format == "PNG"

    buffer.seek(0)
    from PIL import ImageOps
    from pyzbar.pyzbar import decode as pyzbar_decode

    decoded = pyzbar_decode(ImageOps.autocontrast(Image.open(buffer).convert("L")))
    assert decoded[0].data.decode() == uri


def test_create_invoice_qr_long_badge_autofont():
    """Длинный бейдж: автоуменьшение шрифта не ломает декодирование."""
    from PIL import Image, ImageOps
    from pyzbar.pyzbar import decode as pyzbar_decode

    address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    uri = _build_pay_uri(address, "12345678.9", "XLM", None)
    buffer = BytesIO()
    create_invoice_qr(buffer, uri, "12345678.9 LONGASSETCODE")
    decoded = pyzbar_decode(ImageOps.autocontrast(Image.open(buffer).convert("L")))
    assert decoded[0].data.decode() == uri


@pytest.mark.asyncio
async def test_receive_invoice_shows_amount_screen(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    receive_history_redis,
):
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    update = create_callback_update(
        user_id=user_id, callback_data=RECEIVE_INVOICE_CALLBACK
    )
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "receive_invoice_amount_msg" in str(req["data"]["text"])
    # С пустой историей — только кнопка возврата
    assert RECEIVE_HIST_CALLBACK not in str(req["data"]["reply_markup"])

    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    data = await dp.storage.get_data(state_key)
    # Ассет по умолчанию — EURMTL, кошелёк запомнен
    assert data["receive_asset_code"] == "EURMTL"
    assert data["receive_asset_issuer"] == PUBLIC_ISSUER
    assert data["receive_account_id"] == setup_receive_mocks.wallet.public_key
    state = await dp.storage.get_state(state_key)
    assert state == ReceiveInvoiceStates.entering_amount


@pytest.mark.asyncio
async def test_receive_amount_input_bad_sum(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    receive_history_redis,
):
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(state_key, ReceiveInvoiceStates.entering_amount)
    await dp.storage.set_data(
        state_key,
        {
            "receive_account_id": setup_receive_mocks.wallet.public_key,
            "receive_asset_code": "EURMTL",
            "receive_asset_issuer": PUBLIC_ISSUER,
        },
    )

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, "не сумма"),
        app_context=router_app_context,
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert req is not None
    assert "bad_sum" in str(req["data"]["text"])
    # Остались в состоянии ввода суммы
    assert await dp.storage.get_state(state_key) == ReceiveInvoiceStates.entering_amount
    assert not any(r["method"] == "sendPhoto" for r in mock_telegram)


@pytest.mark.asyncio
async def test_receive_amount_input_shows_invoice(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    receive_history_redis,
    monkeypatch,
):
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    address = setup_receive_mocks.wallet.public_key
    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_state(state_key, ReceiveInvoiceStates.entering_amount)
    await dp.storage.set_data(
        state_key,
        {
            "receive_account_id": address,
            "receive_asset_code": "EURMTL",
            "receive_asset_issuer": PUBLIC_ISSUER,
        },
    )
    photos = _capture_invoice_photos(router_app_context, monkeypatch)

    await dp.feed_update(
        bot=router_app_context.bot,
        update=create_message_update(user_id, "10"),
        app_context=router_app_context,
    )

    req_photo = get_telegram_request(mock_telegram, "sendPhoto")
    assert req_photo is not None
    caption = str(req_photo["data"].get("caption", ""))
    assert "receive_invoice_msg" in caption
    # Кнопки смены суммы и ассета
    markup = str(req_photo["data"].get("reply_markup", ""))
    assert RECEIVE_CHANGE_AMOUNT_CALLBACK in markup
    assert RECEIVE_CHANGE_ASSET_CALLBACK in markup

    # SEP-7 URI из QR
    uri = _decode_invoice_qr(photos.pop(0))
    assert uri == (
        f"web+stellar:pay?destination={address}&amount=10"
        f"&asset_code=EURMTL&asset_issuer={PUBLIC_ISSUER}"
    )

    # Пара записана в историю
    count = await receive_history_redis.zcard(f"receive_hist:{user_id}")
    assert count == 1
    member = (await receive_history_redis.zrange(f"receive_hist:{user_id}", 0, -1))[0]
    entry = json.loads(member)
    assert entry["amount"] == "10"
    assert entry["asset_code"] == "EURMTL"
    assert entry["issuer"] == PUBLIC_ISSUER

    # Состояние очищено
    assert await dp.storage.get_state(state_key) is None


@pytest.mark.asyncio
async def test_receive_history_roundtrip(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    receive_history_redis,
    monkeypatch,
):
    """Тап по паре из истории ведёт сразу к готовому экрану."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    address = setup_receive_mocks.wallet.public_key
    store = ReceiveHistoryStore(receive_history_redis)
    await store.add(user_id, HistoryAmount("10", "EURMTL", PUBLIC_ISSUER), now=1_000)
    await store.add(user_id, HistoryAmount("50", "USDT", "GUSDTISS"), now=2_000)
    photos = _capture_invoice_photos(router_app_context, monkeypatch)

    update = create_callback_update(
        user_id=user_id, callback_data=RECEIVE_INVOICE_CALLBACK
    )
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    markup = str(req["data"]["reply_markup"])
    assert "10 EURMTL" in markup and "50 USDT" in markup
    assert (
        f"{RECEIVE_HIST_CALLBACK}0" in markup and f"{RECEIVE_HIST_CALLBACK}1" in markup
    )

    # Новейшая пара (50 USDT, индекс 0) -> готовый экран
    update = create_callback_update(
        user_id=user_id, callback_data=f"{RECEIVE_HIST_CALLBACK}0"
    )
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    req_photo = get_telegram_request(mock_telegram, "sendPhoto")
    assert req_photo is not None
    uri = _decode_invoice_qr(photos.pop(0))
    assert uri == (
        f"web+stellar:pay?destination={address}&amount=50"
        "&asset_code=USDT&asset_issuer=GUSDTISS"
    )


@pytest.mark.asyncio
async def test_receive_history_pick_invalid_index(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    receive_history_redis,
):
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    update = create_callback_update(
        user_id=user_id, callback_data=f"{RECEIVE_HIST_CALLBACK}5"
    )
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    req = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert "bad_data" in str(req["data"].get("text", ""))
    assert not any(r["method"] == "sendPhoto" for r in mock_telegram)


@pytest.mark.asyncio
async def test_receive_change_asset_picker_and_pick(
    mock_telegram,
    router_app_context,
    setup_receive_mocks,
    receive_history_redis,
    monkeypatch,
):
    """Пикер: трастлайны юзера + XLM; XLM-баланс не дублируется."""
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    address = setup_receive_mocks.wallet.public_key

    get_balance = MagicMock()
    get_balance.execute = AsyncMock(
        return_value=[
            Balance("XLM", None, "native", "7"),
            Balance("BTCLN", ISSUER, "credit_alphanum12", "12000"),
            Balance("EURMTL", PUBLIC_ISSUER, "credit_alphanum4", "1"),
        ]
    )
    router_app_context.use_case_factory.create_get_wallet_balance.return_value = (
        get_balance
    )

    state_key = StorageKey(
        bot_id=router_app_context.bot.id, chat_id=user_id, user_id=user_id
    )
    await dp.storage.set_data(
        state_key,
        {
            "receive_account_id": address,
            "receive_amount": "10",
            "receive_asset_code": "EURMTL",
            "receive_asset_issuer": PUBLIC_ISSUER,
        },
    )
    photos = _capture_invoice_photos(router_app_context, monkeypatch)

    update = create_callback_update(
        user_id=user_id, callback_data=RECEIVE_CHANGE_ASSET_CALLBACK
    )
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    req = get_telegram_request(mock_telegram, "sendMessage")
    assert "receive_invoice_asset_msg" in str(req["data"]["text"])
    markup = str(req["data"]["reply_markup"])
    assert "BTCLN" in markup and "XLM" in markup and "EURMTL" in markup

    update = create_callback_update(
        user_id=user_id, callback_data=f"{RECEIVE_ASSET_CALLBACK}0"
    )
    await dp.feed_update(
        bot=router_app_context.bot, update=update, app_context=router_app_context
    )

    req_photo = get_telegram_request(mock_telegram, "sendPhoto")
    assert req_photo is not None
    uri = _decode_invoice_qr(photos.pop(0))
    assert uri == (
        f"web+stellar:pay?destination={address}&amount=10"
        f"&asset_code=BTCLN&asset_issuer={ISSUER}"
    )
    # Смена ассета тоже пишется в историю
    member = (await receive_history_redis.zrange(f"receive_hist:{user_id}", 0, -1))[0]
    entry = json.loads(member)
    assert entry["asset_code"] == "BTCLN" and entry["issuer"] == ISSUER
