from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
LANGS_DIR = ROOT_DIR / "langs"
LANG_FILES = sorted(LANGS_DIR.glob("*.json"))


def test_lang_files_present() -> None:
    assert LANG_FILES, "No language JSON files found in langs/"


@pytest.mark.parametrize("path", LANG_FILES)
def test_lang_files_are_valid_json(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        pytest.fail(f"{path.name} invalid JSON: {exc}")

    assert isinstance(data, dict)
