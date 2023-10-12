import uuid
from datetime import datetime, timedelta

import asyncio

import aiohttp
import requests
from config_reader import config


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

    resp = requests.post("https://thothpay.com//api/invoice", headers=headers, json=j2)

    print(resp)
    print(resp.json())


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

    #print(json_data)

    # resp = requests.post("https://thothpay.com//api/invoice", headers=headers, json=j2)
    async with aiohttp.ClientSession() as session:
        url = "https://thothpay.com/api/invoice"
        headers = {
            "accept": "application/json",
            'Content-Type': 'application/json',
            "Authorization": config.thothpay_api.get_secret_value()
        }
        #print(json.dumps(json_data))
        async with session.post(url, headers=headers, json=json_data) as response:
            data = await response.json()
            if response.status == 200:
                return data
            #print(response)



async def thoth_check_order(invoice_id):
    #/ api / invoice?id =
    async with aiohttp.ClientSession() as session:
        url = "https://thothpay.com/api/invoice?id="+invoice_id
        headers = {
            "accept": "application/json",
            'Content-Type': 'application/json',
            "Authorization": config.thothpay_api.get_secret_value()
        }
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            #print(data.get('state'))
            if data.get('state') and isinstance(data.get('state'),dict) and 'Finished' in data.get('state') :
                return True, int(data['items'][0]['amount'])
            #print(response)
        return False, 0


if __name__ == "__main__":
    #asyncio.run(thoth_create_order(1, 1000))
    #https://thothpay.com/invoice?id=ab8b5c3f-a888-4a28-9004-a5f9f668df60
    print(asyncio.run(thoth_check_order('5d13769f-3102-4ca5-a4ea-06101d1c473f')))



