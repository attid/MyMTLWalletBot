from tronpy import Tron, Contract
from tronpy.keys import PrivateKey
import json
from loguru import logger
from tronpy.providers import HTTPProvider

api_key = '74c4d751-c9f1-4024-9382-5c73fa28c57f'
my_tt = 'TPtRHKXMJqHJ35cqdBBkA18ei9kcjVJsmZ'
usdt_key = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
#Private Key is  3c6d2743d9c9a9e6884456eafe1b8457d94014c92899156e97b6082e3de0204a
#Accuont Address is  TXxK7UpcdG1jFHSTgnnJXeoWsYWtn99Hjd



def create_address():
    priv_key = PrivateKey.random()
    print("Private Key is ", priv_key)

    account = priv_key.public_key.to_base58check_address()
    print("Accuont Address is ", account)

def show_balance(public_key):
    from tronpy import Tron
    from tronpy.providers import HTTPProvider

    client = Tron(HTTPProvider(api_key=api_key))  # Use mainnet(trongrid) with a single api_key

    s = client.get_account_balance(public_key)
    print('TRX=',s)

    cntr = client.get_contract(usdt_key)
    print('USDT=',cntr.functions.balanceOf(public_key)/1000000)


def send_usdt(public_key_to, amount):
    client = Tron(HTTPProvider(api_key=api_key))

    contract = client.get_contract(usdt_key)
    priv_key = PrivateKey(bytes.fromhex("3c6d2743d9c9a9e6884456eafe1b8457d94014c92899156e97b6082e3de0204a"))

    txn = (
        contract.functions.transfer('TPtRHKXMJqHJ35cqdBBkA18ei9kcjVJsmZ', 1000000)
        .with_owner('TXxK7UpcdG1jFHSTgnnJXeoWsYWtn99Hjd')
        .fee_limit(20_000_000)
        .memo("test memo")
        .build()
        .sign(priv_key)
    )

    print(txn.txid)
    print(txn.broadcast().wait())


def send_trx():
    client = Tron(HTTPProvider(api_key=api_key))
    priv_key = PrivateKey(bytes.fromhex("3c6d2743d9c9a9e6884456eafe1b8457d94014c92899156e97b6082e3de0204a"))

    txn = (
        client.trx.transfer("TXxK7UpcdG1jFHSTgnnJXeoWsYWtn99Hjd", "TPtRHKXMJqHJ35cqdBBkA18ei9kcjVJsmZ", 1_000)
        .memo("test memo")
        .build()
        .sign(priv_key)
    )
    print(txn.txid)
    print(txn.broadcast().wait())

if __name__ == "__main__":
    send_usdt(1,1)
    #show_balance(my_tt)
    #show_balance('TXxK7UpcdG1jFHSTgnnJXeoWsYWtn99Hjd')
    #asyncio.run(main())