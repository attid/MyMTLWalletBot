from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = (
    "AI_FIRST.md",
    "AGENTS.md",
    "docs/architecture.md",
    "docs/conventions.md",
    "docs/golden-principles.md",
    "docs/quality-grades.md",
    "docs/glossary.md",
    "docs/runbooks",
    "docs/exec-plans/active",
    "docs/exec-plans/completed",
    "adr",
)


def main() -> int:
    missing: list[str] = []
    for relative in REQUIRED_PATHS:
        path = ROOT / relative
        if not path.exists():
            missing.append(relative)

    if missing:
        print("Missing required AI-first docs paths:")
        for item in missing:
            print(f"- {item}")
        return 1

    print("Docs contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
