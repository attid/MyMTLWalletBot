from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def count_python_files(base: Path) -> int:
    return sum(1 for _ in base.rglob("*.py"))


def count_lines(base: Path) -> int:
    total = 0
    for path in base.rglob("*.py"):
        total += path.read_text(encoding="utf-8", errors="ignore").count("\n") + 1
    return total


def main() -> int:
    bot = ROOT / "bot"
    webapp = ROOT / "webapp"
    shared = ROOT / "shared"

    payload = {
        "python_files": {
            "bot": count_python_files(bot),
            "webapp": count_python_files(webapp),
            "shared": count_python_files(shared),
        },
        "python_loc": {
            "bot": count_lines(bot),
            "webapp": count_lines(webapp),
            "shared": count_lines(shared),
        },
        "tests": {
            "bot_tests": count_python_files(bot / "tests"),
        },
    }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
