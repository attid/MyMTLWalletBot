from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ACTIVE_PLANS_DIR = ROOT / "docs" / "exec-plans" / "active"

REQUIRED_SNIPPETS = (
    "## Files/Directories To Change",
    "## Edit Permission",
    "- [x] Allowed paths confirmed by user.",
    "- [x] No edits outside listed paths.",
)


def should_check(path: Path) -> bool:
    return path.suffix == ".md" and path.name != "README.md"


def main() -> int:
    missing = []
    for plan in sorted(ACTIVE_PLANS_DIR.glob("*.md")):
        if not should_check(plan):
            continue
        text = plan.read_text(encoding="utf-8")
        not_found = [snippet for snippet in REQUIRED_SNIPPETS if snippet not in text]
        if not_found:
            missing.append((plan, not_found))

    if missing:
        print("Execution plan scope-lock check failed:")
        for plan, snippets in missing:
            rel = plan.relative_to(ROOT)
            print(f"- {rel} is missing required items:")
            for snippet in snippets:
                print(f"  - {snippet}")
        print(
            "Fix: update active plan with explicit allowed paths and checked permission items."
        )
        return 1

    print("Execution plan scope-lock checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
