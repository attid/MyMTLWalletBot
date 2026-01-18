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
    """Convert string to float, handling 'unlimited' case."""
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
    from stellar_sdk import StrKey, MuxedAccount
    try:
        if StrKey.is_valid_ed25519_public_key(address):
            return True
        if StrKey.is_valid_med25519_public_key(address):
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
    destination = query_parameters.get("destination")[0]
    amount = query_parameters.get("amount")[0]
    asset_code = query_parameters.get("asset_code")[0]
    asset_issuer = query_parameters.get("asset_issuer")[0]

    # Extract optional memo
    memo = query_parameters.get("memo")
    if memo:
        memo = memo[0]

    return {
        'destination': destination,
        'amount': amount,
        'asset_code': asset_code,
        'asset_issuer': asset_issuer,
        'memo': memo
    }
