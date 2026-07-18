# user-wallets-copy-viewer: Make admin wallet addresses copyable and link viewer

## Context

The admin `/user_wallets` command renders plain Stellar addresses. Make each
address copyable through Telegram's monospace/code interaction and append a
viewer link after the wallet labels for immediate balance inspection.

## Files/Directories To Change

- `bot/routers/admin.py`
- `bot/tests/routers/test_admin.py`
- `docs/exec-plans/active/2026-07-18-user-wallets-copy-viewer.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Add a failing router regression for copyable addresses, wallet labels,
   and account viewer links across multiple wallets.
2. [x] Render each address with `<code>` and append the canonical
   `viewer.eurmtl.me/account/<address>` link after labels.
3. [x] Run focused Admin tests, full tests, and repository gates.
4. [x] Move this plan to completed after verification.

## Risks / Open Questions

- HTML markup must remain valid under the bot's default HTML parse mode.
- The address must remain separate from the anchor so tapping it copies rather
  than opens the viewer.

## Verification

- `uv run pytest bot/tests/routers/test_admin.py -q`
- `just test`
- `just check-fast`
- `git diff --check`
- Expected line:
  `<code>G...</code> (main, free, no pin) (<a href="https://viewer.eurmtl.me/account/G...">viewer</a>)`.

Verification evidence:

- RED: focused regression failed because the response contained plain addresses
  and no viewer links.
- GREEN: focused regression: `1 passed`.
- Admin router suite: `11 passed`.
- Full test suite: `854 passed, 7 deselected`.
- `just check-fast`: Ruff and mypy passed, `546 passed`, architecture and docs
  checks passed.
- `git diff --check`: passed.
