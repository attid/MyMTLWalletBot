# 2026-04-14-escape-sc-tags-decoded-xdr: Escape Soroban Sc-tags in decoded XDR

## Context

`get_web_decoded_xdr` proxies `https://eurmtl.me/remote/decode`, which
dumps Soroban SCVal objects into the HTML output using their Python repr,
e.g. `<SCString [sc_string=b'...']>`. When the result is then sent via
aiogram with `SULGUK_PARSE_MODE`, sulguk's HTML parser treats `<scstring>`
as a real tag and raises `ValueError: Unsupported tag: scstring`, which
breaks `cmd_decode_xdr`.

## Files/Directories To Change

- `bot/other/web_tools.py`
- `docs/exec-plans/active/2026-04-14-2026-04-14-escape-sc-tags-decoded-xdr.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> 1  (chose option 1 — escape Sc-tags at the source)
> прогони

## Change Plan

1. [x] Add a module-level regex that matches opening/closing tags whose
       name starts with `Sc` (case-insensitive) and a helper
       `_escape_scval_tags` that HTML-escapes such tags.
2. [x] Call `_escape_scval_tags` on the decoded text returned by
       `get_web_decoded_xdr` before returning it.
3. [x] Verify against the real failing transaction (uri_nb-gRR-I-KyX60ImtY98NEA4aHw):
       fetched the stored URI, extracted XDR, POSTed to `/remote/decode`,
       confirmed raw response fails sulguk with "Unsupported tag: scstring"
       and escaped response parses successfully.

## Risks / Open Questions

- Regex only targets tags with `Sc*` prefix. If the upstream decoder
  dumps other Python reprs (e.g. `<SomeOther ...>`), sulguk will still
  fail. Acceptable for now — those are not observed in practice.

## Verification

- Reproduced with `uri_nb-gRR-I-KyX60ImtY98NEA4aHw`:
  - raw text → `sulguk.transform_html` → `Unsupported tag: scstring`
  - escaped text → `sulguk.transform_html` → OK
