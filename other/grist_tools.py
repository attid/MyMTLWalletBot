import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional
from loguru import logger
from other.config_reader import config
from other.web_tools import HTTPSessionManager


@dataclass
class GristTableConfig:
    access_id: str
    table_name: str
    base_url: str = 'https://montelibero.getgrist.com/api/docs'


# Enum для таблиц
@dataclass
class MTLGrist:
    NOTIFY_ACCOUNTS = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Accounts")
    NOTIFY_ASSETS = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Assets")
    NOTIFY_TREASURY = GristTableConfig("oNYTdHkEstf9X7dkh7yH11", "Treasury")

    MTLA_CHATS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "MTLA_CHATS")
    MTLA_COUNCILS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "MTLA_COUNCILS")
    MTLA_USERS = GristTableConfig("aYk6cpKAp9CDPJe51sP3AT", "Users")

    SP_USERS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "SP_USERS")
    SP_CHATS = GristTableConfig("3sFtdPU7Dcfw2XwTioLcJD", "SP_CHATS")

    MAIN_CHAT_INCOME = GristTableConfig("gnXfashifjtdExQoeQeij6", "Main_chat_income")
    MAIN_CHAT_OUTCOME = GristTableConfig("gnXfashifjtdExQoeQeij6", "Main_chat_outcome")

    GRIST_access = GristTableConfig("rGD426DVBySAFMTLEqKp1d", "Access")
    GRIST_use_log = GristTableConfig("rGD426DVBySAFMTLEqKp1d", "Use_log")

    EURMTL_users = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Users")
    EURMTL_accounts = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Accounts")
    EURMTL_assets = GristTableConfig("gxZer88w3TotbWzkQCzvyw", "Assets")


class GristAPI:
    def __init__(self, session_manager: HTTPSessionManager = None):
        self.session_manager = session_manager
        self.token = config.grist_token
        if not self.session_manager:
            self.session_manager = HTTPSessionManager()

    async def fetch_data(self, table: GristTableConfig, sort: Optional[str] = None,
                         filter_dict: Optional[Dict[str, List[Any]]] = None) -> List[Dict[str, Any]]:
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
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
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
        response = await self.session_manager.get_web_request(method='GET', url=url, headers=headers)

        match response.status:
            case 200 if response.data and "records" in response.data:
                return [{'id': record['id'], **record['fields']} for record in response.data["records"]]
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def put_data(self, table: GristTableConfig, json_data: Dict[str, Any]) -> bool:
        """
        Обновляет данные в указанной таблице Grist.
        """
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        response = await self.session_manager.get_web_request(method='PUT', url=url, headers=headers,
                                                              json=json_data)

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def patch_data(self, table: GristTableConfig, json_data: Dict[str, Any]) -> bool:
        """
        Частично обновляет данные в указанной таблице Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для обновления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        response = await self.session_manager.get_web_request(method='PATCH', url=url, headers=headers,
                                                              json=json_data)

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def post_data(self, table: GristTableConfig, json_data: Dict[str, Any]) -> bool:
        """
        Добавляет новые записи в указанную таблицу Grist.

        Args:
            table: Конфигурация таблицы Grist
            json_data: Данные для добавления в формате {"records": [{"fields": {...}}]}
        """
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        url = f"{table.base_url}/{table.access_id}/tables/{table.table_name}/records"
        response = await self.session_manager.get_web_request(method='POST', url=url, headers=headers,
                                                              json=json_data)

        match response.status:
            case 200:
                return True
            case _:
                raise Exception(f'Ошибка запроса: Статус {response.status}')

    async def load_table_data(self, table: GristTableConfig, sort: Optional[str] = None,
                              filter_dict: Optional[Dict[str, List[Any]]] = None) -> Optional[List[Dict[str, Any]]]:
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
            logger.warning(f"Ошибка при загрузке данных из таблицы {table.table_name}: {e}")
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
        MTLGrist.EURMTL_assets,
        filter_dict=filter_dict
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
        "account_id": [account_id]   # Filter values should be in a list
    }

    records = await grist_manager.load_table_data(
        MTLGrist.EURMTL_accounts,
        filter_dict=filter_dict
    )

    # Handle the case when records is None (error occurred during loading)
    if records is None:
        return False
    return len(records) > 0


async def main():
    a = await check_account_id_from_grist('GB2JZIVHQNBENPORJDJDHJNJRKC4WDDQ6R3Z3NU24OKFRJ5DLJKFKORB')
    print(a)
    await grist_session_manager.close()


if __name__ == '__main__':
    asyncio.run(main())


async def load_fest_info():
    headers = {
        'accept': 'application/json',
        'Authorization': f'Bearer {config.grist_token}'
    }
    url = 'https://montelibero.getgrist.com/api/docs/tSAWaCAoh8CsDXGb8pbCx9/tables/Fest/records'
    response = await grist_session_manager.get_web_request('GET', url, headers=headers)
    
    if response.status == 200 and response.data and "records" in response.data:
        # {'id': 7, 'fields': {'address_id': 'GAZEFASTL4P7A6ERCSHKWDCKBQVGA4R3V5336ILQF4MSALSAH3VMGHIW', 'username': '@MortenDie', 'name': 'Opossum art'}}
        result = {}
        for record in response.data["records"]:
            if len(record["fields"]["address_id"]) == 56:
                result[record["fields"]["name"]] = record["fields"]["address_id"]
        return result
    else:
        raise Exception(f'Ошибка запроса: Статус {response.status}')

