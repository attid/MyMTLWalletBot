"""sign_tools descriptions: FSM operation + Redis memo for webapp."""

from pathlib import Path

import fakeredis.aioredis
import pytest
from aiogram.fsm.storage.base import StorageKey
from unittest.mock import AsyncMock, MagicMock, patch

from other import faststream_tools
from routers.sign import router as sign_router
from tests.conftest import RouterTestMiddleware, create_message_update


@pytest.fixture(autouse=True)
def cleanup_router():
    """Ensure router is detached after each test."""
    yield
    if sign_router.parent_router:
        sign_router._parent_router = None


@pytest.fixture
def setup_sign_mocks(router_app_context, mock_horizon, horizon_server_config):
    """Sign-mock fixture for this module. Mirrors
    tests.routers.test_sign.setup_sign_mocks (pytest forbids importing a
    fixture module and reusing it by name without shadowing; a thin shared
    helper would be over-engineering for two modules)."""
    from infrastructure.services.stellar_service import StellarService

    class SignMockHelper:
        def __init__(self, ctx):
            self.ctx = ctx
            self._setup_defaults()

        def _setup_defaults(self):
            self.ctx.stellar_service = StellarService(
                horizon_url=horizon_server_config["url"]
            )
            self.public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
            mock_horizon.set_account(self.public_key)

            self.p_is_free = patch(
                "other.stellar_tools.stellar_is_free_wallet", return_value=False
            )
            self.p_check_xdr = patch(
                "other.stellar_tools.stellar_check_xdr", side_effect=lambda x, f: x
            )
            self.p_get_acc = patch("other.stellar_tools.stellar_get_user_account")
            self.p_get_kp = patch("other.stellar_tools.stellar_get_user_keypair")
            self.p_user_sign = patch(
                "other.stellar_tools.stellar_user_sign", return_value="SIGNED_XDR"
            )
            self.p_send = patch(
                "other.stellar_tools.async_stellar_send",
                return_value={"hash": "tx_hash"},
            )

            self.m_is_free = self.p_is_free.start()
            self.m_check_xdr = self.p_check_xdr.start()
            self.m_get_acc = self.p_get_acc.start()
            self.m_get_kp = self.p_get_kp.start()
            self.m_user_sign = self.p_user_sign.start()
            self.m_send = self.p_send.start()

            mock_acc = MagicMock()
            mock_acc.account.account_id = self.public_key
            self.m_get_acc.return_value = mock_acc

            self.wallet = MagicMock()
            self.wallet.public_key = self.public_key
            self.wallet.use_pin = 1
            self.wallet.is_free = False

            wallet_repo = MagicMock()
            wallet_repo.get_default_wallet = AsyncMock(return_value=self.wallet)
            self.ctx.repository_factory.get_wallet_repository.return_value = wallet_repo

        def stop(self):
            self.p_is_free.stop()
            self.p_check_xdr.stop()
            self.p_get_acc.stop()
            self.p_get_kp.stop()
            self.p_user_sign.stop()
            self.p_send.stop()

    helper = SignMockHelper(router_app_context)
    yield helper
    helper.stop()


SET_OPTIONS_XDR = (
    (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "classic"
        / "set_options_add_signer.xdr"
    )
    .read_text()
    .strip()
)
SIGNER = "GDZXMBXSDFOVQ5PKXCJRC5CEUDWBLSSPVQMOLE4EAKLDHUBYKIIMECHO"


def _fake_update_data(mock_state, **kwargs):
    async def _update(data=None, **kw):
        mock_state.data.update(kw)
        if data:
            mock_state.data.update(data)

    return _update


async def _run_check_xdr(
    mock_telegram,
    router_app_context,
    setup_sign_mocks,
    user_id,
    check_xdr,
    resolved_xdr=SET_OPTIONS_XDR,
):
    """Feed an XDR text through StateSign.sending_xdr handler."""
    dp = router_app_context.dispatcher
    dp.message.middleware(RouterTestMiddleware(router_app_context))
    dp.include_router(sign_router)
    bot = router_app_context.bot
    state_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    await dp.storage.update_data(state_key, {"user_lang": "en"})
    # stellar_check_xdr is stubbed in setup_sign_mocks as identity; make it
    # return the resolved XDR when given a sign_tools URL.
    setup_sign_mocks.m_check_xdr.side_effect = lambda x, f=False: (
        resolved_xdr if "eurmtl.me/sign_tools" in x else x
    )
    # sending_xdr state so cmd_send_xdr → cmd_check_xdr fires
    from infrastructure.states import StateSign

    await dp.storage.set_state(state_key, StateSign.sending_xdr)
    await dp.feed_update(bot, create_message_update(user_id, check_xdr))
    return state_key


@pytest.mark.asyncio
async def test_sign_tools_description_becomes_operation(
    mock_telegram, router_app_context, setup_sign_mocks
):
    """eurmtl.me description → FSM operation; render lines → soroban_preview."""
    state_key = None
    with patch(
        "routers.sign.get_eurmtl_xdr",
        return_value=(SET_OPTIONS_XDR, "Croud"),
    ):
        state_key = await _run_check_xdr(
            mock_telegram,
            router_app_context,
            setup_sign_mocks,
            321,
            "https://eurmtl.me/sign_tools/" + "a" * 64,
        )
    data = await router_app_context.dispatcher.storage.get_data(state_key)
    assert data["operation"] == "Croud"
    assert data["tools"].startswith("https://eurmtl.me/sign_tools/")
    assert data["soroban_preview"] == (f"SetOptions: подписант {SIGNER} (weight 3)")


@pytest.mark.asyncio
async def test_sign_tools_no_description_falls_back_to_render(
    mock_telegram, router_app_context, setup_sign_mocks
):
    """Missing description → local classic-ops render becomes operation."""
    state_key = None
    with patch(
        "routers.sign.get_eurmtl_xdr",
        return_value=(SET_OPTIONS_XDR, None),
    ):
        state_key = await _run_check_xdr(
            mock_telegram,
            router_app_context,
            setup_sign_mocks,
            322,
            "https://eurmtl.me/sign_tools/" + "b" * 64,
        )
    data = await router_app_context.dispatcher.storage.get_data(state_key)
    assert data["operation"] == (f"SetOptions: подписант {SIGNER} (weight 3)")


@pytest.mark.asyncio
async def test_sign_tools_unparseable_xdr_keeps_slug(
    mock_telegram, router_app_context, setup_sign_mocks
):
    """No description and no renderable ops → legacy 'sign_tools' slug."""
    bad_xdr = "AAAAAgAAAAA="
    state_key = None
    with patch(
        "routers.sign.get_eurmtl_xdr",
        return_value=(bad_xdr, None),
    ):
        state_key = await _run_check_xdr(
            mock_telegram,
            router_app_context,
            setup_sign_mocks,
            323,
            "https://eurmtl.me/sign_tools/" + "c" * 64,
            resolved_xdr=bad_xdr,
        )
    data = await router_app_context.dispatcher.storage.get_data(state_key)
    assert data["operation"] == "sign_tools"


@pytest.mark.asyncio
async def test_webapp_memo_carries_description(
    mock_telegram, router_app_context, setup_sign_mocks
):
    """Redis FIELD_MEMO for webapp contains description, not raw slug."""
    setup_sign_mocks.wallet.use_pin = 10
    fake_redis = fakeredis.aioredis.FakeRedis()
    old_redis_client = faststream_tools.REDIS_CLIENT
    faststream_tools.REDIS_CLIENT = fake_redis
    try:
        with patch(
            "routers.sign.get_eurmtl_xdr",
            return_value=(SET_OPTIONS_XDR, "Croud"),
        ):
            await _run_check_xdr(
                mock_telegram,
                router_app_context,
                setup_sign_mocks,
                324,
                "https://eurmtl.me/sign_tools/" + "d" * 64,
            )
        keys = await fake_redis.keys("tx:*")
        assert len(keys) == 1
        tx_data = await fake_redis.hgetall(keys[0])
        decoded = {k.decode(): v.decode() for k, v in tx_data.items()}
        assert decoded["memo"] == "Croud"
        # chat prompt: conftest l10n returns bare key, so assert on the param
        # passed to get_text for the prompt template — must be the classic
        # render preview (non-empty sign_header path), not the bare memo.
        l10n = router_app_context.localization_service.get_text
        prompt_calls = [
            c for c in l10n.call_args_list if c.args[1] == "biometric_sign_prompt"
        ]
        assert prompt_calls, "biometric_sign_prompt must be requested"
        assert SIGNER in prompt_calls[-1].args[2][0]
    finally:
        faststream_tools.REDIS_CLIENT = old_redis_client
        await fake_redis.aclose()
