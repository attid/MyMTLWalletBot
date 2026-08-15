"""Regression checks for dependency wiring performed inside ``start.main``."""

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from infrastructure.services.app_context import AppContext
from infrastructure.services.notification_service import NotificationService
from other.config_reader import config
from start import get_startup_message, set_commands


START_PATH = Path(__file__).resolve().parents[2] / "start.py"


def _constructor_keywords(class_name: str) -> set[str]:
    tree = ast.parse(START_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == class_name
    ]
    assert len(calls) == 1, f"expected one {class_name} constructor call"
    return {keyword.arg for keyword in calls[0].keywords if keyword.arg is not None}


def test_startup_constructor_keywords_match_real_signatures() -> None:
    constructors = {
        "NotificationService": NotificationService,
        "AppContext": AppContext,
    }

    for class_name, constructor in constructors.items():
        allowed = set(inspect.signature(constructor).parameters)
        assert _constructor_keywords(class_name) <= allowed


def test_startup_injects_sealedbox_service_into_app_context() -> None:
    assert "stellar_sealedbox_service" in _constructor_keywords("AppContext")
    assert "stellar_sealedbox_service" not in _constructor_keywords(
        "NotificationService"
    )


def test_startup_message_includes_short_commit() -> None:
    assert get_startup_message("1234567890") == "Bot started (commit: 1234567)"


def test_startup_message_falls_back_when_commit_is_missing() -> None:
    assert get_startup_message("") == "Bot started (commit: unknown)"


@pytest.mark.asyncio
async def test_set_commands_registers_complete_private_and_admin_menus() -> None:
    bot = AsyncMock(spec=Bot)

    await set_commands(bot)

    calls = bot.set_my_commands.await_args_list
    assert len(calls) == 3
    assert calls[0].kwargs["commands"] == []
    assert isinstance(calls[0].kwargs["scope"], BotCommandScopeDefault)

    private_commands = calls[1].kwargs["commands"]
    assert [(item.command, item.description) for item in private_commands] == [
        ("start", "Start or ReStart bot"),
        ("change_wallet", "Switch to another address"),
        ("send", "Send tokens"),
        ("crypto", "Encrypt or decrypt"),
        ("create_cheque", "Create cheque"),
    ]
    assert isinstance(calls[1].kwargs["scope"], BotCommandScopeAllPrivateChats)

    admin_commands = calls[2].kwargs["commands"]
    assert [(item.command, item.description) for item in admin_commands] == [
        ("start", "Start or ReStart bot"),
        ("change_wallet", "Switch to another address"),
        ("send", "Send tokens"),
        ("crypto", "Encrypt or decrypt"),
        ("create_cheque", "Create cheque"),
        ("restart", "ReStart bot"),
        ("fee", "check fee"),
        ("horizon", "change horizon"),
        ("horizon_rw", "change horizon_rw"),
    ]
    admin_scope = calls[2].kwargs["scope"]
    assert isinstance(admin_scope, BotCommandScopeChat)
    assert admin_scope.chat_id == config.admins[0]
