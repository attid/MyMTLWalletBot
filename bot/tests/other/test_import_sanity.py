import os
import pytest
import importlib
import sys
from other.config_reader import Settings

# Add project root to path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)


def get_python_modules(root_path):
    modules = []
    for root, dirs, files in os.walk(root_path):
        # Skip hidden directories, venv, and __pycache__
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".") and d != "venv" and d != "__pycache__"
        ]

        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                # Convert path to module dotted path
                rel_path = os.path.relpath(os.path.join(root, file), root_path)
                module_name = rel_path.replace(os.path.sep, ".")[:-3]

                # Skip tests themselves to avoid recursion issues or test discovery issues
                if module_name.startswith("tests."):
                    continue

                modules.append(module_name)
    return modules


@pytest.mark.parametrize("module_name", get_python_modules(PROJECT_ROOT))
def test_import_sanity(module_name):
    """
    Tries to import every python module to catch NameError, ImportError, SyntaxError at module level.
    """
    try:
        importlib.import_module(module_name)
    except (NameError, ImportError, AttributeError, SyntaxError) as e:
        pytest.fail(f"Failed to import {module_name}: {e}")
    except Exception as e:
        # Other runtime errors during import (e.g. database connection init at top level)
        # might be ignored or handled, but ideally top level code shouldn't do side effects.
        # For now, we fail on them too to encourage clean modules.
        pytest.fail(f"Runtime error during import of {module_name}: {e}")


def _build_settings_without_mongodb_url() -> dict[str, object]:
    return {
        "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "test_bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "base_fee": 100,
        "db_url": "sqlite+aiosqlite:///test.db",
        "redis_url": "redis://localhost:6379/0",
        "tron_api_key": "test-tron-api-key",
        "tron_master_address": "TTestMasterAddress",
        "tron_master_key": "test-tron-master-key",
        "thothpay_api": "test-thothpay-api",
        "openai_key": "test-openai-key",
        "eurmtl_key": "test-eurmtl-key",
        "sentry_dsn": "https://example.com/sentry",
        "horizon_url": "https://horizon.stellar.org",
        "horizon_url_rw": "https://horizon.stellar.org",
        "grist_token": "test-grist-token",
        "tonconsole_token": "test-tonconsole-token",
        "ton_token": "test-ton-token",
        "wallet_cost": 1.0,
    }


def test_settings_allows_missing_mongodb_url(monkeypatch):
    monkeypatch.delenv("MONGODB_URL", raising=False)
    settings = Settings(_env_file=None, **_build_settings_without_mongodb_url())

    assert settings.mongodb_url is None


@pytest.mark.asyncio
async def test_db_mongo_import_is_safe_without_mongodb_url(monkeypatch):
    import other.config_reader as config_reader

    monkeypatch.delenv("MONGODB_URL", raising=False)
    original_module = sys.modules.pop("db.mongo", None)
    original_config = config_reader.config
    config_reader.config = Settings(
        _env_file=None, **_build_settings_without_mongodb_url()
    )

    try:
        mongo_module = importlib.import_module("db.mongo")

        assert mongo_module.client is None
        assert mongo_module.db is None
        assert mongo_module.accounts_collection is None
        assert await mongo_module.check_account_id_from_grist("GTESTACCOUNT") is False
    finally:
        config_reader.config = original_config
        sys.modules.pop("db.mongo", None)
        if original_module is not None:
            sys.modules["db.mongo"] = original_module
