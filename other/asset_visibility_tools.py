import json
from typing import Dict, Optional

# Asset visibility statuses
ASSET_VISIBLE = "visible"
ASSET_EXCHANGE_ONLY = "exchange_only"
ASSET_HIDDEN = "hidden"

def serialize_visibility(visibility_dict: Dict[str, str]) -> str:
    """
    Serialize the asset visibility dictionary to a JSON string.
    """
    return json.dumps(visibility_dict, ensure_ascii=False)

def deserialize_visibility(visibility_str: Optional[str]) -> Dict[str, str]:
    """
    Deserialize the asset visibility JSON string to a dictionary.
    If the string is empty or invalid, return an empty dict.
    """
    if not visibility_str:
        return {}
    try:
        return json.loads(visibility_str)
    except Exception:
        return {}

def get_asset_visibility(visibility_str: Optional[str], asset_code: str) -> str:
    """
    Get the visibility status for a specific asset.
    If not set, return ASSET_VISIBLE by default.
    """
    vis = deserialize_visibility(visibility_str)
    return vis.get(asset_code, ASSET_VISIBLE)

def set_asset_visibility(visibility_str: Optional[str], asset_code: str, status: str) -> str:
    """
    Set the visibility status for a specific asset and return the new serialized string.
    """
    vis = deserialize_visibility(visibility_str)
    vis[asset_code] = status
    return serialize_visibility(vis)