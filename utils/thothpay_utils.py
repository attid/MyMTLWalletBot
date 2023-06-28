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
    print(asyncio.run(thoth_check_order('a37704be-bc79-4cd5-b15a-e9fe60d5d70c')))
    print(asyncio.run(thoth_check_order('ab8b5c3f-a888-4a28-9004-a5f9f668df60')))
    print(asyncio.run(thoth_check_order('d7d811d4-cef0-4425-8299-dd5b74775e51')))
    print(asyncio.run(thoth_check_order('34b8ad1d-dbf2-4d4e-85ef-b5f746bf3480')))

    new = {'id': 'ab8b5c3f-a888-4a28-9004-a5f9f668df60', 'merchant_id': '9a83ab58-55a2-4c63-9236-9d7f1d6615f9', 'internal_number': 276, 'external_order_id': '1', 'external_number': None, 'tittle': 'Exchange with MMWB', 'currency': {'Crypto': 'Btc'}, 'items': [{'name': 'Exchange with MMWB', 'amount': '0x3e8'}], 'choosen': {}, 'created_date': '2023-05-05T17:00:42.559722075', 'due_date': '2023-05-05T19:30:32', 'callback_url': None, 'state': 'Awaiting'}
    good = {'id': 'ab8b5c3f-a888-4a28-9004-a5f9f668df60', 'merchant_id': '9a83ab58-55a2-4c63-9236-9d7f1d6615f9', 'internal_number': 276, 'external_order_id': '1', 'external_number': None, 'tittle': 'Exchange with MMWB', 'currency': {'Crypto': 'Btc'}, 'items': [{'name': 'Exchange with MMWB', 'amount': '0x3e8'}], 'choosen': {'Lightning': {'address': {'Btc': {'Ln': 'lnbc9999n1pj92wrfsp5vu2v2whnuxla6pjul255c9pasfv68all9jnzj4trk2wvm0w6j2nspp5mmmqsm3uynp940cd8r704esgu3ke5scj3zgec8mllr5qnzp8m4vsdz4235x7argwpshjgrfdemx76trv5sxzc3cvg6kxvmx94snswpc956xzv3c95unqvp594sn2e3evcmrvwryvcmrqxqrgc7cqpjrzjqtx3k77yrrav9hye7zar2rtqlfkytl094dsp0ms5majzth6gt7ca6zl405qqtlcqqqqqqqqqqqqqraqq2q9qx3qysgqcyjyvwd9dzd8hhmj6cja3zs2y3xexqmasay8x64wf8audldaagznapqpr3uljdx84gva4v5g8hp7756n6l75e2c3cmzjum37pdd98mqpjlpkce'}}, 'exchange_rate': {'rate': ['0x1', '0x1'], 'from': {'Crypto': 'Btc'}, 'to': {'Crypto': 'Lightning'}}}}, 'created_date': '2023-05-05T17:00:42.559722075', 'due_date': '2023-05-05T19:30:32', 'callback_url': None,
            'state': {'Finished': {'payment_proof': [{'txid': 'b0f0fa83bf88b10f090279518b353a6c6083a09ecedf5c264084306d4debc9b7', 'amount': {'Lightning': 1000000}, 'confirmations': 1, 'time': '2023-05-05T17:11:58.338617843'}], 'refund_proof': None}}}


