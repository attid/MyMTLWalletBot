"""Regression checks for dependency wiring performed inside ``start.main``."""

import ast
import inspect
from pathlib import Path

from infrastructure.services.app_context import AppContext
from infrastructure.services.notification_service import NotificationService
from start import get_startup_message


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


def test_private_commands_include_crypto_entry() -> None:
    content = START_PATH.read_text(encoding="utf-8")

    assert 'command="crypto"' in content
