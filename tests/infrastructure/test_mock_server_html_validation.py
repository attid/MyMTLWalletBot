
import pytest
from tests.conftest import get_telegram_request
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram import Bot

@pytest.mark.asyncio
async def test_mock_server_html_validation(telegram_server_config, mock_telegram):
    """
    Test that the mock server rejects invalid HTML tags.
    """
    session = AiohttpSession(api=TelegramAPIServer.from_base(telegram_server_config["url"]))
    bot = Bot(token="123:abc", session=session)
    chat_id = 123
    
    # 1. Valid Tags
    try:
        await bot.send_message(chat_id=chat_id, text="<b>Bold</b>", parse_mode="HTML")
    except Exception as e:
        pytest.fail(f"Valid HTML failed: {e}")

    # 2. Invalid Tag <sum>
    with pytest.raises(Exception) as excinfo:
        await bot.send_message(chat_id=chat_id, text="<sum>Invalid</sum>", parse_mode="HTML")
    assert "Bad Request" in str(excinfo.value)
    assert "Unsupported start tag" in str(excinfo.value)

    # 3. Unclosed Tag
    with pytest.raises(Exception) as excinfo:
        await bot.send_message(chat_id=chat_id, text="<b>Unclosed", parse_mode="HTML")
    assert "Bad Request" in str(excinfo.value)
    assert "not closed" in str(excinfo.value)

    # 4. Mismatched closing tag
    with pytest.raises(Exception) as excinfo:
        await bot.send_message(chat_id=chat_id, text="<b><i>Wrong</b></i>", parse_mode="HTML")
    assert "Bad Request" in str(excinfo.value)
    
    await bot.session.close()
