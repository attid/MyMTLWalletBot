import aiohttp
import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union

from loguru import logger

from other.config_reader import config

_SCVAL_TAG_RE = re.compile(r"</?sc[a-z][\w]*\b[^>]*>", re.IGNORECASE)
_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<a\s[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r'href="([^"]*)"', re.IGNORECASE)
_SPAN_OPEN_RE = re.compile(r"<span[^>]*>", re.IGNORECASE)
_SPAN_CLOSE_RE = re.compile(r"</span>", re.IGNORECASE)
_DIV_OPEN_RE = re.compile(r"<div[^>]*>", re.IGNORECASE)
_DIV_CLOSE_RE = re.compile(r"</div>", re.IGNORECASE)
# Any tag Telegram's HTML subset does not allow; its content stays in the text.
_STRAY_TAG_RE = re.compile(
    r"</?(?!a\b|b\b|i\b|u\b|s\b|code\b|pre\b|blockquote\b)[a-zA-Z][^>]*>",
    re.IGNORECASE,
)


def _escape_scval_tags(text: str) -> str:
    return _SCVAL_TAG_RE.sub(
        lambda m: m.group(0).replace("<", "&lt;").replace(">", "&gt;"), text
    )


def _anchor_repl(match: re.Match) -> str:
    href = _HREF_RE.search(match.group(0))
    if not href:
        return match.group(1)
    return f'<a href="{href.group(1)}">{match.group(1)}</a>'


def _sanitize_decode_html(text: str) -> str:
    """Normalize eurmtl.me/remote/decode web HTML into Telegram-safe HTML.

    Telegram's parse mode HTML rejects bare <span>/<div> and attributes other
    than href on <a>. Line breaks become newlines, links keep only href,
    warning containers (<span>/<div>) become <b> with content preserved, and
    any other unknown tag is dropped while its content stays in the message.
    """
    text = _BR_TAG_RE.sub("\n", text)
    text = _ANCHOR_RE.sub(_anchor_repl, text)
    text = _SPAN_OPEN_RE.sub("<b>", text)
    text = _SPAN_CLOSE_RE.sub("</b>", text)
    text = _DIV_OPEN_RE.sub("<b>", text)
    text = _DIV_CLOSE_RE.sub("</b>", text)
    text = _STRAY_TAG_RE.sub("", text)
    text = text.replace("&nbsp;", "\u00a0")
    return text


# Датакласс для ответа
@dataclass
class WebResponse:
    status: int  # Статус код ответа
    data: Union[Dict[str, Any], str]  # Данные ответа (JSON или текст)
    headers: Optional[Dict[str, str]] = None  # Заголовки ответа
    elapsed_time: Optional[float] = None  # Время выполнения запроса (в секундах)


class HTTPSessionManager:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.session_start_time: float = 0.0
        self.max_session_duration = 3600  # 1 час в секундах
        self._lock = asyncio.Lock()  # Асинхронный lock для синхронизации

    async def get_session(self) -> aiohttp.ClientSession:
        async with self._lock:  # Блокируем доступ к сессии
            current_time = time.monotonic()
            if (
                self.session is None
                or self.session.closed
                or current_time - self.session_start_time > self.max_session_duration
            ):
                if self.session and not self.session.closed:
                    await self.session.close()
                self.session = aiohttp.ClientSession()
                self.session_start_time = current_time
                logger.info("Сессия создана или пересоздана.")
            return self.session

    async def close(self):
        async with self._lock:  # Блокируем доступ к сессии
            if self.session and not self.session.closed:
                await self.session.close()
                logger.info("Сессия закрыта.")

    async def get_web_request(
        self,
        method: str,
        url: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Union[Dict[str, Any], str]] = None,
        return_type: Optional[str] = None,
    ) -> WebResponse:
        """
        Выполняет HTTP-запрос с использованием текущей сессии.

        :param method: HTTP-метод (GET, POST, PUT и т.д.).
        :param url: URL для запроса.
        :param json: JSON-данные для отправки (для POST/PUT).
        :param headers: Заголовки запроса.
        :param data: Данные для отправки (для GET/POST).
        :param return_type: Ожидаемый тип ответа ('json' или None).
        :return: Экземпляр WebResponse.
        """
        session = await self.get_session()
        start_time = time.monotonic()

        try:
            async with session.request(
                method.upper(), url, json=json, headers=headers, data=data
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                elapsed_time = time.monotonic() - start_time

                # Определяем, как обрабатывать ответ
                if "application/json" in content_type or return_type == "json":
                    data = await response.json()
                else:
                    data = await response.text()

                return WebResponse(
                    status=response.status,
                    data=data,
                    headers=dict(response.headers),
                    elapsed_time=elapsed_time,
                )
        except aiohttp.ClientError as e:
            raise Exception(f"Ошибка при выполнении запроса: {e}")


async def get_debank_balance(
    account_id: str,
    chain: str = "bsc",
    session_manager: Optional[HTTPSessionManager] = None,
) -> float:
    """
    Получает баланс аккаунта в USD через DeBank API.
    Использует HTTPSessionManager для управления сессией.

    :param account_id: ID аккаунта.
    :param chain: Идентификатор блокчейна (по умолчанию 'bsc').
    :param session_manager: Опциональный экземпляр HTTPSessionManager.
    :return: Баланс в USD.
    """
    # Создаём session_manager, если он не передан
    if session_manager is None:
        session_manager = http_session_manager

    url = (
        "https://pro-openapi.debank.com/v1/user/chain_balance"
        f"?id={account_id}"
        f"&chain_id={chain}"
    )

    if not config.debank:
        raise ValueError("DeBankAPI key not configured")

    headers = {
        "accept": "application/json",
        "AccessKey": config.debank.get_secret_value(),
    }

    try:
        response = await session_manager.get_web_request(
            "GET", url, headers=headers, return_type="json"
        )
        if response.status == 200:
            if isinstance(response.data, dict):
                return float(response.data.get("usd_value", 0.0))
            else:
                raise Exception("Unexpected response format from DeBankAPI")
        else:
            raise Exception(f"Ошибка запроса: Статус {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при получении баланса: {e}")
        raise


http_session_manager = HTTPSessionManager()


# Пример использования
async def main():
    session_manager = HTTPSessionManager()
    try:
        # GET-запрос
        response = await session_manager.get_web_request(
            "GET", "https://example.com", return_type="json"
        )
        print(f"GET Response: {response}")

        # POST-запрос
        post_data = {"key": "value"}
        response = await session_manager.get_web_request(
            "POST", "https://example.com", json=post_data
        )
        print(f"POST Response: {response}")

    finally:
        await session_manager.close()


# async def get_eurmtl_xdr(url):
#     try:
#         url = 'https://eurmtl.me/remote/get_xdr/' + url.split('/')[-1]
#         response = await http_session_manager.get_web_request('GET', url=url)
#
#         if 'xdr' in response.data:
#             return response.data['xdr']
#         else:
#             return 'Invalid response format: missing "xdr" field.'
#     except Exception as ex:
#         logger.info(['get_eurmtl_xdr', ex])
#         return 'An error occurred during the request.'


async def get_web_request(
    method, url, json=None, headers=None, data=None, return_type=None
):
    async with aiohttp.ClientSession() as web_session:
        if method.upper() == "POST":
            request_coroutine = web_session.post(
                url, json=json, headers=headers, data=data
            )
        elif method.upper() == "GET":
            request_coroutine = web_session.get(url, headers=headers, params=data)
        else:
            raise ValueError("Неизвестный метод запроса")

        async with request_coroutine as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type or return_type == "json":
                return response.status, await response.json()
            else:
                return response.status, await response.text()


async def get_web_decoded_xdr(xdr):
    status, response_json = await get_web_request(
        "POST", url="https://eurmtl.me/remote/decode", json={"xdr": xdr}
    )
    if status == 200:
        msg = _sanitize_decode_html(_escape_scval_tags(response_json["text"]))
    else:
        msg = "Ошибка запроса"
    return msg


if __name__ == "__main__":
    asyncio.run(main())
