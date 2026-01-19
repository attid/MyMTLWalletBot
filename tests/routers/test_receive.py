
import pytest
import os
import tempfile
import shutil
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from unittest.mock import patch, AsyncMock, MagicMock
import datetime

from routers.receive import router as receive_router
from routers.receive import create_beautiful_code
from tests.conftest import MOCK_SERVER_URL, TEST_BOT_TOKEN
from aiogram.dispatcher.middlewares.base import BaseMiddleware


class MockDbMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["session"] = MagicMock()
        return await handler(event, data)


@pytest.fixture(autouse=True)
def cleanup_router():
    yield
    if receive_router.parent_router:
         receive_router._parent_router = None


@pytest.mark.asyncio
async def test_cmd_receive(mock_telegram, dp):
    """
    Test Receive callback: should get user account and create/send QR code.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(MOCK_SERVER_URL)
    )
    bot = Bot(token=TEST_BOT_TOKEN, session=session)

    dp.callback_query.middleware(MockDbMiddleware())
    dp.include_router(receive_router)

    # Mock account data
    mock_acc = MagicMock()
    mock_acc.account.account_id = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Mock stellar_get_user_account (external Stellar Network API)
    with patch("routers.receive.stellar_get_user_account", new_callable=AsyncMock) as mock_get_acc, \
         patch("routers.receive.my_gettext", return_value="Your address"), \
         patch("routers.start_msg.my_gettext", return_value="Your address"), \
         patch("keyboards.common_keyboards.my_gettext", return_value="Back"):

        mock_get_acc.return_value = mock_acc

        # Create callback update
        update = types.Update(
            update_id=1,
            callback_query=types.CallbackQuery(
                id="cb1",
                from_user=types.User(id=123, is_bot=False, first_name="Test", username="test"),
                chat_instance="ci1",
                message=types.Message(
                    message_id=1,
                    date=datetime.datetime.now(),
                    chat=types.Chat(id=123, type='private'),
                    text="msg"
                ),
                data="Receive"
            )
        )

        # Configure app_context with properly mocked bot and dispatcher
        app_context = MagicMock()
        app_context.bot = bot  # Use real bot instance from mock_server
        app_context.dispatcher = dp  # Dispatcher has storage
        app_context.localization_service = MagicMock()
        app_context.localization_service.get_text.return_value = "Your address"

        await dp.feed_update(bot=bot, update=update, app_context=app_context)

        # Verify QR code was created
        qr_path = f"qr/{mock_acc.account.account_id}.png"
        assert os.path.exists(qr_path), f"QR code file {qr_path} should be created"

        # Verify sendPhoto was called (via mock_server)
        req = next((r for r in mock_telegram if r["method"] == "sendPhoto"), None)
        assert req is not None, "sendPhoto should be called"

        # Verify callback was answered
        req_answer = next((r for r in mock_telegram if r["method"] == "answerCallbackQuery"), None)
        assert req_answer is not None, "answerCallbackQuery should be called"

        # Cleanup QR file
        if os.path.exists(qr_path):
            os.remove(qr_path)

    await bot.session.close()


@pytest.mark.asyncio
async def test_create_beautiful_code():
    """
    Test QR code generation: creates valid QR with address overlay.
    """
    from PIL import Image

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Create temp directory for test
    temp_dir = tempfile.mkdtemp()
    qr_path = os.path.join(temp_dir, "test_qr.png")

    try:
        # Generate QR code
        create_beautiful_code(qr_path, test_address)

        # Verify file exists
        assert os.path.exists(qr_path), "QR code file should be created"

        # Verify it's a valid image
        img = Image.open(qr_path)
        assert img.size[0] > 0 and img.size[1] > 0, "Image should have valid dimensions"

        # Verify image mode (should be RGB)
        assert img.mode == "RGB", "Image should be in RGB mode"

    finally:
        # Cleanup temp files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_create_qr_with_logo():
    """
    Test QR code with logo overlay: creates valid QR with text overlay.
    """
    from routers.receive import create_qr_with_logo, create_image_with_text
    from PIL import Image

    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"

    # Create logo
    logo_img = create_image_with_text(f'{test_address[:4]}..{test_address[-4:]}')

    # Create QR with logo
    qr_with_logo = create_qr_with_logo(test_address, logo_img)

    # Verify result is a valid image
    assert isinstance(qr_with_logo, Image.Image), "Should return PIL Image"
    assert qr_with_logo.size[0] > 0 and qr_with_logo.size[1] > 0, "Image should have valid dimensions"
    assert qr_with_logo.mode == "RGB", "Image should be in RGB mode"


@pytest.mark.asyncio
async def test_create_image_with_text():
    """
    Test text image creation: creates valid image with address text.
    """
    from routers.receive import create_image_with_text
    from PIL import Image

    test_text = "GD45..XI"

    # Create image with text
    img = create_image_with_text(test_text)

    # Verify result is a valid image
    assert isinstance(img, Image.Image), "Should return PIL Image"
    assert img.size == (200, 50), "Default image size should be 200x50"
    assert img.mode == "RGB", "Image should be in RGB mode"
