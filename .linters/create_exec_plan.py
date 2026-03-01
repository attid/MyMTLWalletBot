from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "docs" / "exec-plans" / "template.md"
ACTIVE_DIR = ROOT / "docs" / "exec-plans" / "active"


def sanitize_task_id(raw: str) -> str:
    value = raw.strip().lower().replace(" ", "-")
    return "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})


def normalize_title(raw: str) -> str:
    value = raw.strip()
    if value.startswith("title="):
        return value.split("=", 1)[1].strip()
    return value


def build_content(task_id: str, title: str) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    heading = f"# {task_id}: {title}" if title else f"# {task_id}: <short title>"
    lines = template.splitlines()
    if lines:
        lines[0] = heading
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create AI-first execution plan file")
    parser.add_argument(
        "task_id", help="Short task identifier, e.g. signing-flow-cleanup"
    )
    parser.add_argument("--title", default="", help="Optional human-readable title")
    args = parser.parse_args()

    task_id = sanitize_task_id(args.task_id)
    if not task_id:
        print("Task id is empty after sanitization.")
        return 1

    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}-{task_id}.md"
    target = ACTIVE_DIR / filename

    if target.exists():
        print(f"Execution plan already exists: {target.relative_to(ROOT)}")
        return 1

    content = build_content(task_id=task_id, title=normalize_title(args.title))
    target.write_text(content, encoding="utf-8")
    print(f"Created execution plan: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
