from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BOT_ROOT = ROOT / "bot"


@dataclass(frozen=True)
class Rule:
    source_prefix: str
    forbidden_prefixes: tuple[str, ...]
    reason: str


RULES: tuple[Rule, ...] = (
    Rule(
        source_prefix="core/entities/",
        forbidden_prefixes=(
            "infrastructure",
            "routers",
            "db",
            "middleware",
            "keyboards",
            "services",
            "other",
        ),
        reason="Core entities must stay framework/integration agnostic.",
    ),
    Rule(
        source_prefix="core/value_objects/",
        forbidden_prefixes=(
            "infrastructure",
            "routers",
            "db",
            "middleware",
            "keyboards",
            "services",
            "other",
        ),
        reason="Value objects must stay in the inner layer.",
    ),
    Rule(
        source_prefix="core/interfaces/",
        forbidden_prefixes=(
            "infrastructure",
            "routers",
            "middleware",
            "keyboards",
            "services",
            "other",
        ),
        reason="Interfaces define ports and must not depend on adapters.",
    ),
    Rule(
        source_prefix="core/use_cases/",
        forbidden_prefixes=("routers", "middleware", "keyboards"),
        reason="Use cases must not depend on delivery layer constructs.",
    ),
)


def iter_python_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*.py") if ".venv" not in p.parts)


def read_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.append(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def check_file(path: Path) -> list[str]:
    rel = path.relative_to(BOT_ROOT).as_posix()
    imports = read_imports(path)
    errors: list[str] = []

    for rule in RULES:
        if not rel.startswith(rule.source_prefix):
            continue
        for imp in imports:
            for forbidden in rule.forbidden_prefixes:
                if imp == forbidden or imp.startswith(f"{forbidden}."):
                    errors.append(
                        "ERROR: "
                        f"bot/{rel} imports `{imp}`. "
                        f"Rule: files under `{rule.source_prefix}` must not import "
                        f"`{forbidden}`. Why: {rule.reason} "
                        "Fix: depend on core abstractions/interfaces and inject adapters. "
                        "See docs/architecture.md#boundary-rules-mechanically-checked."
                    )
    return errors


def main() -> int:
    files = iter_python_files(BOT_ROOT)
    errors: list[str] = []
    for path in files:
        errors.extend(check_file(path))

    if errors:
        print("\n".join(errors))
        return 1

    print("Import boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
