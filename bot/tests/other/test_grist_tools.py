from unittest.mock import AsyncMock

import pytest

from other.config_reader import config
from other.grist_tools import GristAPI, GristTableConfig, MTLGrist
from other.web_tools import WebResponse


@pytest.mark.parametrize(
    "table_name",
    [
        "NOTIFY_ACCOUNTS",
        "NOTIFY_ASSETS",
        "NOTIFY_TREASURY",
        "SP_USERS",
        "SP_CHATS",
        "MAIN_CHAT_INCOME",
        "MAIN_CHAT_OUTCOME",
        "GRIST_access",
        "GRIST_use_log",
        "EURMTL_users",
        "EURMTL_accounts",
        "EURMTL_assets",
        "SHARE_HOLDERS",
        "CONFIG",
        "MTL_AIRDROP_REGISTER",
        "MTL_ADMINS",
        "MTLA_CHATS",
        "MTLA_COUNCILS",
        "MTLA_USERS",
    ],
)
def test_audited_document_binding(table_name: str) -> None:
    table = getattr(MTLGrist, table_name)

    assert table.access_id
    assert table.base_url is None


@pytest.mark.asyncio
async def test_grist_api_uses_centralized_root(monkeypatch: pytest.MonkeyPatch) -> None:
    session_manager = AsyncMock()
    session_manager.get_web_request.return_value = WebResponse(
        status=200, data={"records": []}
    )
    monkeypatch.setattr(config, "grist_base_url", "https://grist.eurmtl.me/api/docs")
    api = GristAPI(session_manager=session_manager)

    await api.fetch_data(MTLGrist.EURMTL_assets)

    request = session_manager.get_web_request.call_args.kwargs
    assert request["url"] == (
        f"https://grist.eurmtl.me/api/docs/{MTLGrist.EURMTL_assets.access_id}/"
        "tables/Assets/records"
    )


@pytest.mark.asyncio
async def test_grist_table_can_keep_explicit_separate_host() -> None:
    session_manager = AsyncMock()
    session_manager.get_web_request.return_value = WebResponse(
        status=200, data={"records": []}
    )
    api = GristAPI(session_manager=session_manager)
    table = GristTableConfig(
        access_id="rely-document",
        table_name="Records",
        base_url="https://mtl-rely.getgrist.com/api/docs",
    )

    await api.fetch_data(table)

    request = session_manager.get_web_request.call_args.kwargs
    assert request["url"] == (
        "https://mtl-rely.getgrist.com/api/docs/rely-document/tables/Records/records"
    )
