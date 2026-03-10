"""Tests for telegram_utils.clear_state."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.utils.telegram_utils import clear_state


class TestClearState:
    """Tests for clear_state function."""

    @pytest.fixture
    def mock_state(self):
        state = MagicMock()
        state.get_data = AsyncMock(
            return_value={
                "user_id": 42,
                "user_name": "Alice",
                "user_lang": "ru",
                "show_more": True,
                "last_message_id": 7,
                "mtlap": "somekey",
                "use_ton": True,
                "some_transient_key": "should_be_removed",
            }
        )
        state.set_data = AsyncMock()
        state.set_state = AsyncMock()
        return state

    @pytest.mark.asyncio
    async def test_clear_state_resets_fsm_state(self, mock_state, monkeypatch):
        """clear_state must call set_state(None) to reset FSM state."""
        # Patch out faststream_tools to avoid real Redis calls
        monkeypatch.setattr(
            "infrastructure.utils.telegram_utils.faststream_tools",
            MagicMock(clear_pending_tx=AsyncMock()),
            raising=False,
        )
        # Patch the import inside the function
        import sys
        fake_other = MagicMock()
        fake_other.faststream_tools = MagicMock(clear_pending_tx=AsyncMock())
        monkeypatch.setitem(sys.modules, "other", fake_other)
        monkeypatch.setitem(sys.modules, "other.faststream_tools", fake_other.faststream_tools)

        await clear_state(mock_state)

        mock_state.set_state.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_clear_state_preserves_session_fields(self, mock_state, monkeypatch):
        """clear_state keeps user_id, user_name, user_lang, show_more, etc."""
        import sys
        fake_other = MagicMock()
        fake_other.faststream_tools = MagicMock(clear_pending_tx=AsyncMock())
        monkeypatch.setitem(sys.modules, "other", fake_other)
        monkeypatch.setitem(sys.modules, "other.faststream_tools", fake_other.faststream_tools)

        await clear_state(mock_state)

        call_kwargs = mock_state.set_data.call_args[0][0]
        assert call_kwargs["user_id"] == 42
        assert call_kwargs["user_name"] == "Alice"
        assert call_kwargs["user_lang"] == "ru"
        assert call_kwargs["show_more"] is True
        assert call_kwargs["last_message_id"] == 7
        assert call_kwargs["mtlap"] == "somekey"
        assert call_kwargs["use_ton"] is True

    @pytest.mark.asyncio
    async def test_clear_state_removes_transient_keys(self, mock_state, monkeypatch):
        """clear_state must NOT carry over transient keys like some_transient_key."""
        import sys
        fake_other = MagicMock()
        fake_other.faststream_tools = MagicMock(clear_pending_tx=AsyncMock())
        monkeypatch.setitem(sys.modules, "other", fake_other)
        monkeypatch.setitem(sys.modules, "other.faststream_tools", fake_other.faststream_tools)

        await clear_state(mock_state)

        call_kwargs = mock_state.set_data.call_args[0][0]
        assert "some_transient_key" not in call_kwargs
