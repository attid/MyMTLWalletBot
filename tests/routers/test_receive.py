import pytest
import os
from unittest.mock import MagicMock, AsyncMock

from routers.receive import router as receive_router, create_beautiful_code
from tests.conftest import (
    RouterTestMiddleware,
    create_callback_update,
    get_telegram_request
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
            self.wallet.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            
            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

    return ReceiveMockHelper(router_app_context)


@pytest.mark.asyncio
async def test_cmd_receive_callback(mock_telegram, router_app_context, setup_receive_mocks):
    """
    Test Receive callback: should show QR code and address info.
    NO PATCH for cmd_info_message - integration test according to README.md
    """
    dp = router_app_context.dispatcher
    dp.callback_query.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(receive_router)

    user_id = 123
    test_address = setup_receive_mocks.wallet.public_key
    qr_path = f"qr/{test_address}.png"

    # Ensure qr directory exists
    os.makedirs("qr", exist_ok=True)

    update = create_callback_update(user_id=user_id, callback_data="Receive")
    
    # Run handler through dispatcher (Live interaction simulation)
    await dp.feed_update(bot=router_app_context.bot, update=update, app_context=router_app_context)

    # 1. Verify QR was created
    assert os.path.exists(qr_path)
    
    # 2. Verify answerCallbackQuery was called
    req_answer = get_telegram_request(mock_telegram, "answerCallbackQuery")
    assert req_answer is not None

    # 3. Verify sendPhoto was called (cmd_info_message -> bot.send_photo)
    req_photo = get_telegram_request(mock_telegram, "sendPhoto")
    assert req_photo is not None
    assert str(user_id) == str(req_photo['data']['chat_id'])
    # caption can be multipart or urlencoded depending on bot version, mock_server captures it
    assert "my_address" in str(req_photo['data'].get('caption', ''))

    # Cleanup
    if os.path.exists(qr_path):
        os.remove(qr_path)


def test_create_beautiful_code():
    """Unit test for QR code generation."""
    from PIL import Image
    test_address = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    qr_path = "tests/test_qr_gen.png"
    
    os.makedirs("tests", exist_ok=True)
    
    try:
        create_beautiful_code(qr_path, test_address)
        assert os.path.exists(qr_path)
        
        with Image.open(qr_path) as img:
            assert img.mode == "RGB"
            assert img.size[0] > 100
    finally:
        if os.path.exists(qr_path):
            os.remove(qr_path)

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