import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from loguru import logger
from other.config_reader import config
from other.web_tools import HTTPSessionManager


@dataclass
class GristTableConfig:
    access_id: str
    table_name: str
    # Set this only for a deliberately separate Grist host (for example RELY).
    # Normal tables use the centralized Montelibero root from Settings.
    base_url: Optional[str] = None


# Enum для таблиц
@dataclass
class MTLGrist:
    NOTIFY_ACCOUNTS = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Accounts")
    NOTIFY_ASSETS = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Assets")
    NOTIFY_TREASURY = GristTableConfig("f3ETcoWEkzvkcUnQJtv5tm", "Treasury")

    MTLA_CHATS = GristTableConfig("x4r7WiFKsJREzXS4vowwqj", "MTLA_CHATS")
    MTLA_COUNCILS = GristTableConfig("x4r7WiFKsJREzXS4vowwqj", "MTLA_COUNCILS")
    MTLA_USERS = GristTableConfig("x4r7WiFKsJREzXS4vowwqj", "Users")

    SP_USERS = GristTableConfig("hpZWKq729vw2D5AkG7oYYz", "SP_USERS")
    SP_CHATS = GristTableConfig("hpZWKq729vw2D5AkG7oYYz", "SP_CHATS")

    MAIN_CHAT_INCOME = GristTableConfig("khWn5KMRbfUQQoaPydjhGt", "Main_chat_income")
    MAIN_CHAT_OUTCOME = GristTableConfig("khWn5KMRbfUQQoaPydjhGt", "Main_chat_outcome")

    GRIST_access = GristTableConfig("1sd6z3cHUPVQSgvyy7iARy", "Access")
    GRIST_use_log = GristTableConfig("1sd6z3cHUPVQSgvyy7iARy", "Use_log")

    EURMTL_users = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Users")
    EURMTL_accounts = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Accounts")
    EURMTL_assets = GristTableConfig("3Fk4hjCv847GBx8ZTCPN2Y", "Assets")

    # Dormant audited Montelibero documents are kept explicit so a future
    # caller cannot silently fall back to an old GetGrist document.
    SHARE_HOLDERS = GristTableConfig("eNajcBuG4bFPzDvZfGC3JQ", "ShareHolders")
    CONFIG = GristTableConfig("vpjoUZvH6WRcS7Es8n1UZv", "config")
    MTL_AIRDROP_REGISTER = GristTableConfig(
        "r4r5Lhy2QJ7bvNs4ut1ATV", "MTL_Airdrop_register"
    )
    MTL_ADMINS = GristTableConfig("ePz5LKsFPmhe5XCC4z7akA", "MTL admins")


class GristAPI:
    def __init__(
        self,
        session_manager: Optional[HTTPSessionManager] = None,
        token: Optional[str] = None,
    ):
        if not session_manager:
            self.session_manager = HTTPSessionManager()
        else:
            self.session_manager = session_manager
        # A separate token can be injected for an intentionally separate host
        # (such as RELY); regular callers use the centralized runtime token.
        self.token = token if token is not None else config.grist_token

    @staticmethod
    def _table_url(table: GristTableConfig) -> str:
        base_url = (table.base_url or config.grist_base_url).rstrip("/")
        return f"{base_url}/{table.access_id}/tables/{table.table_name}/records"

    async def fetch_data(
        self,
        table: GristTableConfig,
        sort: Optional[str] = None,
        filter_dict: Optional[Dict[str, List[Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Загружает данные из указанной таблицы Grist.

        Args:
            table: Конфигурация таблицы
            sort: Параметр сортировки
            filter_dict: Словарь фильтрации в формате {"column": [value1, value2]}
                        Пример: {"TGID": [123456789]}
        """
        from urllib.parse import quote

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = self._table_url(table)
        params = []

        if sort:
            params.append(f"sort={sort}")
        if filter_dict:
            # Преобразуем словарь в JSON и кодируем для URL
            filter_json = json.dumps(filter_dict)
            encoded_filter = quote(filter_json)
            params.append(f"filter={encoded_filter}")

        if params:
            url = f"{url}?{'&'.join(params)}"
        response = await self.session_manager.get_web_request(
            method="GET", url=url, headers=headers
        )

        match response.status:
            case 200:
                if isinstance(response.data, dict) and "records" in response.data:
                    return [
                        {"id": record["id"], **record["fields"]}
                        for record in response.data["records"]
                    ]
                else:
                    raise Exception("Unexpected response format")
            case _:
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def put_data(
        self, table: GristTableConfig, json_data: Dict[str, Any]
    ) -> bool:
        """
        Обновляет данные в указанной таблице Grist.
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = self._table_url(table)
        response = await self.session_manager.get_web_request(
            method="PUT", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def patch_data(
        self, table: GristTableConfig, json_data: Dict[str, Any]
    ) -> bool:
        """
        Частично обновляет данные в указанной таблице Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для обновления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = self._table_url(table)
        response = await self.session_manager.get_web_request(
            method="PATCH", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def post_data(
        self, table: GristTableConfig, json_data: Dict[str, Any]
    ) -> bool:
        """
        Добавляет новые записи в указанную таблицу Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для добавления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        url = self._table_url(table)
        response = await self.session_manager.get_web_request(
            method="POST", url=url, headers=headers, json=json_data
        )

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f"Ошибка запроса: Статус {response.status}")

    async def load_table_data(
        self,
        table: GristTableConfig,
        sort: Optional[str] = None,
        filter_dict: Optional[Dict[str, List[Any]]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Загружает данные из таблицы с обработкой ошибок.

        Args:
            table: Конфигурация таблицы
            sort: Параметр сортировки
            filter_dict: Словарь фильтрации в формате {"column": [value1, value2]}
                        Пример: {"TGID": [123456789]}
        """
        try:
            records = await self.fetch_data(table, sort, filter_dict)
            logger.info(f"Данные из таблицы {table.table_name} успешно загружены")
            return records
        except Exception as e:
            logger.warning(
                f"Ошибка при загрузке данных из таблицы {table.table_name}: {e}"
            )
            return None


# Конфигурация
grist_session_manager = HTTPSessionManager()
grist_manager = GristAPI(grist_session_manager)


@dataclass
class GristAsset:
    code: str
    issuer: str


async def load_asset_from_grist(code: str) -> Optional[GristAsset]:
    filter_dict = {"code": [code]}

    asset_records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_assets, filter_dict=filter_dict
    )
    if asset_records:
        user_record = asset_records[0]
        result = GristAsset(code=user_record["code"], issuer=user_record["issuer"])
        # if user.account_id:
        #     grist_cash[user.account_id] = user
        return result

    return None


async def check_account_id_from_grist(account_id: str) -> bool:
    """
    Check if a given account ID has a 'reserv' signer type in the EURMTL_accounts collection.

    Args:
        account_id (str): The account ID to check.

    Returns:
        bool: True if the account ID has a 'reserv' signer type, False otherwise.
    """
    filter_dict = {
        "signers_type": ["reserv"],  # Filter values should be in a list
        "account_id": [account_id],  # Filter values should be in a list
    }

    records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_accounts, filter_dict=filter_dict
    )

    # Handle the case when records is None (error occurred during loading)
    if records is None:
        return False
    return len(records) > 0


async def main():
    a = await check_account_id_from_grist(
        "GB2JZIVHQNBENPORJDJDHJNJRKC4WDDQ6R3Z3NU24OKFRJ5DLJKFKORB"
    )
    print(a)
    await grist_session_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
