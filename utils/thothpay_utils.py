import uuid
from datetime import datetime, timedelta
import asyncio
from data.config_reader import config
from utils.aiogram_utils import get_web_request


def test():
    print(config.thothpay_api.get_secret_value())
    headers = {
        "accept": "application/json",
        "Authorization": config.thothpay_api.get_secret_value()
    }

    j = {
        "order_id": "string",
        "number": 0,
        "title": "string",
        "currency": {
            "Crypto": "Btc"
        },
        "items": [
            {
                "amount": "0x54470",
                "name": "VPN subscription 1 month"
            },
            {
                "amount": "0x28622f0",
                "name": "10GB RAM stick"
            }
        ],
        "due_date": "2023-12-28T12:39:14",
        "callback_url": "string"
    }

    j2 = {"order_id": str(uuid.uuid4()),
          # "number": 0,
          "title": "Exchange with MMWB",
          "currency": {
              "Crypto": "Lightning"
          },
          "items": [
              {
                  "amount": int(
                      5.2 * 10 ** 11),
                  "name": "Exchange with MMWB"
              }
          ],
          "due_date": (
                  datetime.now() + timedelta(
              hours=3)).strftime(
              "%Y-%m-%dT%H:%M:%S")
          # "callback_url": "string"
          }

    print(j2)

    # resp = requests.post("https://thothpay.com//api/invoice", headers=headers, json=j2)

    # print(resp)
    # print(resp.json())


async def thoth_create_order(user_id, amount):
    json_data = {"order_id": str(user_id),
                 # "number": 0,
                 "title": "Exchange with MMWB",
                 "currency": {
                     "Crypto": "Btc"
                 },
                 "items": [
                     {
                         "amount": int(amount),
                         "name": "Exchange with MMWB"
                     }
                 ],
                 "due_date": (
                         datetime.now() + timedelta(
                     minutes=30)).strftime(
                     "%Y-%m-%dT%H:%M:%S")
                 # "callback_url": "string"
                 }

    url = "https://thothpay.com/api/invoice"
    headers = {
        "accept": "application/json",
        'Content-Type': 'application/json',
        "Authorization": config.thothpay_api.get_secret_value()
    }
    status, response_json = await get_web_request('POST', url=url, headers=headers, json=json_data)
    if status == 200:
        return response_json


async def thoth_check_order(invoice_id):
    # / api / invoice?id =
    url = "https://thothpay.com/api/invoice?id=" + invoice_id
    headers = {
        "accept": "application/json",
        'Content-Type': 'application/json',
        "Authorization": config.thothpay_api.get_secret_value()
    }
    status, data = await get_web_request('GET', url=url, headers=headers)
    print(status, data)
    if status == 200:
        if data.get('state') and isinstance(data.get('state'), dict) and 'Finished' in data.get('state'):
            return True, int(data['items'][0]['amount'])
    return False, 0


if __name__ == "__main__":
    print(asyncio.run(thoth_create_order(1, 1000)))

    # https://thothpay.com/invoice?id=ab8b5c3f-a888-4a28-9004-a5f9f668df60
    print(asyncio.run(thoth_check_order('bdafb9fb-c7c0-4091-83d7-e01886039993')))
