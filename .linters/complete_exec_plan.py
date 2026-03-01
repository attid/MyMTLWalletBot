from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_DIR = ROOT / "docs" / "exec-plans" / "active"
COMPLETED_DIR = ROOT / "docs" / "exec-plans" / "completed"


def resolve_active_plan(plan_name: str) -> Path:
    direct = ACTIVE_DIR / plan_name
    if direct.exists():
        return direct
    with_suffix = ACTIVE_DIR / f"{plan_name}.md"
    if with_suffix.exists():
        return with_suffix
    raise FileNotFoundError(plan_name)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move execution plan from active to completed"
    )
    parser.add_argument(
        "plan_name",
        help="Filename in docs/exec-plans/active (with or without .md)",
    )
    args = parser.parse_args()

    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        source = resolve_active_plan(args.plan_name)
    except FileNotFoundError:
        print(f"Active execution plan not found: {args.plan_name}")
        return 1

    target = COMPLETED_DIR / source.name
    if target.exists():
        print(f"Completed execution plan already exists: {target.relative_to(ROOT)}")
        return 1

    source.rename(target)
    print(f"Moved execution plan to completed: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
