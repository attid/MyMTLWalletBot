import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List, Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel
from config_reader import config

client = AsyncIOMotorClient(config.mongodb_url)
db = client['mtl_tables']

assets_collection = db['assets']
accounts_collection = db['accounts']


async def mongo_get_asset_issuer(asset_code):
    asset_data = await assets_collection.find({
        "issuer": {"$exists": True},
        "code": asset_code
    }).to_list(length=None)
    if asset_data:
        return asset_data[0].get("issuer")


async def mongo_check_multi(public_key: str) -> bool:
    """
    Check if a given public key has a 'reserv' signer type in the accounts collection.

    Args:
        public_key (str): The public key to check.

    Returns:
        bool: True if the public key has a 'reserv' signer type, False otherwise.
    """
    result = await accounts_collection.find_one({
        "signers_type": "reserv",
        "account_id": public_key
    })
    return bool(result)


if __name__ == '__main__':
    _ = asyncio.run(mongo_check_multi('GD44EAUQXNUVBJACZMW6GPT2GZ7I26EDQCU5HGKUTVEQTXIDEVGUFIRE'))
    print(_)
