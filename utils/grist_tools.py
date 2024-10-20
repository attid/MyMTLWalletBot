import asyncio
from utils.aiogram_utils import get_web_request
from utils.config_reader import config


async def load_fest_info():
    headers = {
        'accept': 'application/json',
        'Authorization': f'Bearer {config.grist_token}'
    }
    url = 'https://montelibero.getgrist.com/api/docs/tSAWaCAoh8CsDXGb8pbCx9/tables/Fest/records'
    status, response = await get_web_request('GET', url, headers=headers)
    if status == 200 and response and "records" in response:
        # {'id': 7, 'fields': {'address_id': 'GAZEFASTL4P7A6ERCSHKWDCKBQVGA4R3V5336ILQF4MSALSAH3VMGHIW', 'username': '@MortenDie', 'name': 'Opossum art'}}
        result = {}
        for record in response["records"]:
            if len(record["fields"]["address_id"]) == 56:
                result[record["fields"]["name"]] = record["fields"]["address_id"]
        return result
    else:
        raise Exception(f'Ошибка запроса: Статус {status}')





if __name__ == '__main__':
    _ = asyncio.run(load_fest_info())
    print(_)