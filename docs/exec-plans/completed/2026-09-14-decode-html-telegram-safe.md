# decode-html-telegram-safe: Make eurmtl.me decode HTML Telegram-safe (span/div/target)

## Context

`eurmtl.me/remote/decode` returns web-oriented HTML (`<span >MaxTime ...</span>`,
`<a ... target="_blank">`, `<div style="color: orange;">`). The bot sends it with
global `parse_mode="HTML"`, but Telegram's HTML subset does not allow bare
`<span>`/`<div>` or `target` attributes, so the send fails with
`Bad Request: can't parse entities: Tag "span" must have class "tg-spoiler"`.
`get_web_decoded_xdr` (bot/other/web_tools.py) only escapes soroban `<sc...>`
artifacts today, and `routers/mtltools.py` does its own raw decode call.

## Files/Directories To Change

- `bot/other/web_tools.py`
- `bot/routers/mtltools.py`
- `bot/tests/other/test_web_tools.py` (new)
- `bot/tests/routers/test_mtltools.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved ("++") the proposed scope: extend sanitize handling in
> `bot/other/web_tools.py`, switch `bot/routers/mtltools.py` to the helper, add
> a sanitizer test with the real decode output as fixture.

## Change Plan

1. [x] In `bot/other/web_tools.py` add `_sanitize_decode_html`: `<br>` variants to
   newlines, `&nbsp;` to NBSP, `<a href="X" ...>` keeps only href, bare
   `<span>`/`<div>` tags become `<b>` (content preserved), remaining non-Telegram
   tags stripped; apply it in `get_web_decoded_xdr` after the scval escape.
   Anchor open/close pairs are normalized atomically (href-less links keep text).
2. [x] In `bot/routers/mtltools.py` replaced the raw decode call with
   `get_web_decoded_xdr`; the idle `get_web_request` import was replaced.
3. [x] Added `bot/tests/other/test_web_tools.py` (10 tests) with the real decode
   fragment (`<span >MaxTime ...</span>`, `target="_blank"`, orange `<div>`, scval tags).
4. [x] Updated `test_cmd_tools_update_multi` patch target to the helper.
5. [x] Ran `just check-fast` (458 passed); re-ran generate+decode+sanitize live for
   GCVT...GORA: no forbidden tags left, display length 2158 (< 4096).

## Risks / Open Questions

- `wallet_setting.py` and `sign.py` also consume `get_web_decoded_xdr`; the helper
  change makes their output Telegram-safe too (same tags would crash those flows).
- An `<a>` without href in future service output would be stripped (content kept).

## Verification

- `just check-fast` green.
- Live decode for GCVT...GORA sanitized: output contains no `target=`, no bare
  `<span>`/`<div>`, keeps `MaxTime` warning and links.
