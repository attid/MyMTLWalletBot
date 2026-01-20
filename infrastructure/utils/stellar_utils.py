"""
Stellar utilities and SDK-compatible asset definitions.

This module provides:
- stellar_sdk.Asset instances for use with Stellar SDK
- Utility functions for Stellar-specific operations
- Helper functions for validation, parsing, and formatting
"""

from stellar_sdk import Asset
from core.constants import (
    PUBLIC_ISSUER, PUBLIC_MMWB, 
    USDC_ISSUER, USDM_ISSUER,
    BASE_FEE
)

# Stellar SDK Asset instances (for use with stellar_sdk operations)
xlm_asset = Asset("XLM")
mtl_asset = Asset("MTL", PUBLIC_ISSUER)
eurmtl_asset = Asset("EURMTL", PUBLIC_ISSUER)
btcmtl_asset = Asset("BTCMTL", PUBLIC_ISSUER)
satsmtl_asset = Asset("SATSMTL", PUBLIC_ISSUER)
usdc_asset = Asset("USDC", USDC_ISSUER)
usdm_asset = Asset("USDM", USDM_ISSUER)

# Re-export constants for convenience
public_issuer = PUBLIC_ISSUER
public_mmwb = PUBLIC_MMWB
base_fee = BASE_FEE


def my_float(s):
    """Convert string to float, handling 'unlimited' case and None."""
    if s is None:
        return 0.0
    if s == 'unlimited':
        return float('inf')
    return float(s)


def my_round(x: float, base=2):
    return round(x, base)


def is_base64(s):
    """Check if string is valid base64."""
    import base64
    try:
        return base64.b64encode(base64.b64decode(s)).decode() == s
    except Exception:
        return False


def cut_text_to_28_bytes(text: str) -> str:
    """
    Cut text to fit within Stellar's 28-byte memo limit.
    Handles UTF-8 encoding properly.
    """
    encoded = text.encode('utf-8')
    if len(encoded) <= 28:
        return text
    # Truncate to 28 bytes, handling UTF-8 properly
    truncated = encoded[:28]
    # Try to decode, removing incomplete UTF-8 sequences
    for i in range(4):
        try:
            return truncated.decode('utf-8')
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


def is_valid_stellar_address(address: str) -> bool:
    """Validate Stellar address format."""
    from stellar_sdk import StrKey
    try:
        if StrKey.is_valid_ed25519_public_key(address):
            return True
        return False
    except Exception:
        return False


def find_stellar_addresses(text: str):
    """Find all Stellar addresses in text using regex."""
    import re
    # Stellar addresses are 56 characters starting with G
    pattern = r'G[A-Z2-7]{55}'
    return re.findall(pattern, text)


def find_stellar_federation_address(text: str):
    """Find Stellar federation addresses (email-like format)."""
    import re
    pattern = r'[a-zA-Z0-9_.+-]+\*[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    matches = re.findall(pattern, text)
    return matches[0] if matches else None


def extract_url(msg: str, surl: str = 'eurmtl.me'):
    """Extract URL from message text."""
    import re
    pattern = rf'https?://(?:www\.)?{re.escape(surl)}[^\s]*'
    match = re.search(pattern, msg)
    if match:
        return match.group(0)
    return None


def xdr_to_uri(xdr: str) -> str:
    """Convert XDR to web+stellar:tx URI format."""
    from urllib.parse import urlencode, quote
    params = {'xdr': xdr}
    return 'web+stellar:tx?' + urlencode(params, quote_via=quote)


def decode_data_value(data_value: str):
    """Decode Stellar data entry value."""
    import base64
    try:
        decoded = base64.b64decode(data_value)
        try:
            # Try to decode as UTF-8 text
            return decoded.decode('utf-8')
        except UnicodeDecodeError:
            # Return as hex if not valid UTF-8
            return decoded.hex()
    except Exception:
        return data_value


async def parse_pay_stellar_uri(uri_data: str):
    """
    Parse a Stellar payment URI (web+stellar:pay) and extract parameters.

    Args:
        uri_data (str): The Stellar payment URI string

    Returns:
        dict: Dictionary containing parsed payment parameters
    """
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(uri_data)
    query_parameters = parse_qs(parsed.query)

    # Extract required parameters
    destination_list = query_parameters.get("destination")
    amount_list = query_parameters.get("amount")
    asset_code_list = query_parameters.get("asset_code")
    asset_issuer_list = query_parameters.get("asset_issuer")

    if not (destination_list and amount_list and asset_code_list and asset_issuer_list):
        raise ValueError("Missing required URI parameters")

    destination = destination_list[0]
    amount = amount_list[0]
    asset_code = asset_code_list[0]
    asset_issuer = asset_issuer_list[0]

    # Extract optional memo
    memo = None
    memo_list = query_parameters.get("memo")
    if memo_list:
        memo = memo_list[0]

    return {
        'destination': destination,
        'amount': amount,
        'asset_code': asset_code,
        'asset_issuer': asset_issuer,
        'memo': memo
    }


def stellar_get_market_link(sale_asset: Asset, buy_asset: Asset) -> str:
    """Generate Stellar.Expert market link for an asset pair."""
    from aiogram.utils.text_decorations import html_decoration
    
    sale_asset_str = sale_asset.code if sale_asset.is_native() else f'{sale_asset.code}-{sale_asset.issuer}'
    buy_asset_str = buy_asset.code if buy_asset.is_native() else f'{buy_asset.code}-{buy_asset.issuer}'
    market_link = f'https://eurmtl.me/cup/orderbook/{sale_asset_str}/{buy_asset_str}'
    market_link = html_decoration.link(value='expert', link=market_link)
    return market_link


def get_good_asset_list():
    """Return list of recommended assets for the bot."""
    from typing import List
    from other.mytypes import Balance
    
    return [
        Balance.from_dict(
            {"asset_code": 'AUMTL', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'EURMTL', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'BTCMTL', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'SATSMTL', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'LABR', "asset_issuer": 'GA7I6SGUHQ26ARNCD376WXV5WSE7VJRX6OEFNFCEGRLFGZWQIV73LABR'}),
        Balance.from_dict(
            {"asset_code": 'MTL', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'MTLRECT', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'MTLand', "asset_issuer": PUBLIC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'MTLCITY', "asset_issuer": 'GDUI7JVKWZV4KJVY4EJYBXMGXC2J3ZC67Z6O5QFP4ZMVQM2U5JXK2OK3'}),
        Balance.from_dict(
            {"asset_code": 'MTLDVL', "asset_issuer": 'GAMU3C7Q7CUUC77BAN5JLZWE7VUEI4VZF3KMCMM3YCXLZPBYK5Q2IXTA'}),
        Balance.from_dict(
            {"asset_code": 'FCM', "asset_issuer": 'GDIE253MSIYMFUS3VHRGEQPIBG7VAIPSMATWLTBF73UPOLBUH5RV2FCM'}),
        Balance.from_dict(
            {"asset_code": 'USDC', "asset_issuer": USDC_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'MMWB', "asset_issuer": PUBLIC_MMWB}),
        Balance.from_dict(
            {"asset_code": 'USDM', "asset_issuer": USDM_ISSUER}),
        Balance.from_dict(
            {"asset_code": 'MTLFEST', "asset_issuer": 'GCGWAPG6PKBMHEEAHRLTWHFCAGZTQZDOXDMWBUBCXHLQBSBNWFRYFEST'}),
        Balance.from_dict(
            {"asset_code": 'MTLAP', "asset_issuer": 'GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA'}),
    ]
