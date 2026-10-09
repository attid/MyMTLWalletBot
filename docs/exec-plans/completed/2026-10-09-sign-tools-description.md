# sign-tools-description: Human-readable sign_tools descriptions in webapp memo and chat

## Context

User signs a transaction via eurmtl.me sign_tools link. Bot shows raw slug
"sign_tools" as the operation description both in the WebApp confirm screen
(memo) and in chat prompts. Meanwhile eurmtl.me stores a human-readable
`tx_description` and now exposes it: `GET /remote/get_xdr/<hash>` returns
`{"description": ..., "xdr": ...}` (verified live on 2026-10-09).

Goal: show the description (fallback: local classic-ops render, fallback:
generic label) in webapp memo, chat prompt before signing, and chat message
after signing.

## Files/Directories To Change

- `bot/other/stellar_tools.py`
- `bot/other/tx_render.py` (new)
- `bot/routers/sign.py`
- `bot/infrastructure/workers/signing_worker.py`
- `bot/tests/other/test_tx_render.py` (new)
- `bot/tests/fixtures/classic/` (new XDR fixtures)
- `bot/tests/routers/test_sign_tools_description.py` (new)
- `docs/exec-plans/active/2026-10-09-sign-tools-description.md` (this plan)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved design A+B on 2026-10-09: "ГО" (go ahead) after design message
> describing exactly these files (stellar_tools get_eurmtl_xdr, tx_render.py,
> sign.py cmd_check_xdr, signing_worker tools branch, tests, exec plan).

## Change Plan

1. [x] `bot/other/tx_render.py`: new `render_classic_ops(xdr) -> list[str]`
   rendering classic Stellar operations (Payment, SetOptions signer, ChangeTrust,
   ManageData, AccountMerge, CreateAccount) via stellar_sdk, pattern of
   `render_soroban_sub_invocations`.
2. [x] `bot/other/stellar_tools.py`: `get_eurmtl_xdr` returns
   `(xdr, description)`; update all callers.
3. [x] `bot/routers/sign.py` `cmd_check_xdr`: for sign_tools links fetch
   description; set `operation` to short description (fallback render summary,
   fallback "sign_tools"); store full render lines in `soroban_preview`.
4. [x] `bot/infrastructure/workers/signing_worker.py`: tools branch — prepend
   preview lines before "Ваша транзакция c подписью".
5. [x] Add `bot/tests/other/test_tx_render.py`; add
   `bot/tests/routers/test_sign_tools_description.py` (4 router-level cases).
6. [x] Run `just check`.

## Risks / Open Questions

- `operation` value must stay out of logic switches: verify nothing branches on
  `operation == "sign_tools"` (worker branches on `tools` field).
- WebApp memo width: trim description to ~100 chars.
- Old links without description in eurmtl.me DB → fallback path must work.

## Verification

- `just check` green.
- Unit: `render_classic_ops` for SetOptions-add-signer fixture returns
  "SetOptions: ..." line; non-parse input returns [].
- Router test: `cmd_check_xdr` with sign_tools URL stores description in FSM
  `operation` and render lines in `soroban_preview`.
- Manual smoke: fake link → chat prompt shows description instead of
  "sign_tools" (requires deployed eurmtl.me API, covered by live check above).
