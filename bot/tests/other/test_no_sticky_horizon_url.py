"""Guard: no component may capture a Horizon URL at import or constructor time.

The production bug this plan fixes was exactly that: ``StellarService`` kept the
URL it was constructed with and ``AnchorDiscoveryService`` kept the one it read
at import, so switching the endpoint changed nothing for most traffic.
"""

import re
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[2]

SCANNED_FILES = sorted((BOT_ROOT / "infrastructure" / "services").glob("*.py")) + [
    BOT_ROOT / "other" / "stellar_tools.py"
]

FORBIDDEN_PATTERNS = (
    re.compile(r"horizon_url\s*=\s*config\."),
    re.compile(r"self\._horizon_url\s*="),
    re.compile(r"^_HORIZON_URL\s*=", re.MULTILINE),
)


def test_horizon_url_is_never_captured_in_a_field() -> None:
    offenders: list[str] = []
    for path in SCANNED_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line_number = text[: match.start()].count("\n") + 1
                offenders.append(
                    f"{path.relative_to(BOT_ROOT)}:{line_number}: {match.group(0)}"
                )

    assert not offenders, (
        "Resolve the Horizon URL from infrastructure.services.horizon_pool on "
        "every call instead of storing it:\n" + "\n".join(offenders)
    )
