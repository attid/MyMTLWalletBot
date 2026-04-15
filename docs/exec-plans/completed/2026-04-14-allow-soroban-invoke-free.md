# allow-soroban-invoke-free: Allow InvokeHostFunction for free wallets + show transfer summaries

## Context

Сейчас `stellar_check_xdr` (`bot/other/stellar_tools.py:239`) для free-аккаунтов
разрешает только `ManageData`, `Payment` (кроме XLM), `ChangeTrust`, `Clawback`,
`SetTrustLineFlags`. `InvokeHostFunction` всегда отклоняется, из-за чего
free-юзеры не могут подписывать web+stellar:tx URI с Soroban-вызовами.

Задача состоит из двух связанных частей:

### Часть A — расширение whitelist для free-кошельков

Разрешить `InvokeHostFunction` для free-аккаунтов, если:

1. В операции есть `auth` с непустыми `sub_invocations`
   (соло-вызовы без авторизованных под-инвокаций остаются запрещёнными).
2. Ни корневой контракт, ни любая под-инвокация не ссылаются на
   `XLM_SOROBAN_CONTRACT` (`CAS3J7GYLGXMF6TDJBBYYSE3HQ6BBSMLNUQ34T6TZMYMW2EVH34XOWMA`) —
   иначе free-юзеры смогут расходовать XLM через Soroban-обёртку в обход запрета
   на XLM Payment.
3. Каждая под-инвокация в дереве должна быть вызовом функции **`transfer`**
   (whitelist). Любой другой function_name (`transfer_from`, `approve`,
   `mint`, `burn` и вообще всё неизвестное) → отказ. Это защитный default:
   пускаем free-юзеров только в явно безопасные операции.

### Часть B — человекочитаемый превью транзакции (локально)

Пользователь (и в free-, и в обычном кошельке, и в webapp при подписи) должен
перед подтверждением видеть, что именно он подписывает. Для транзакций с
`InvokeHostFunction`, у которых есть `sub_invocations`, автоматически показывать
строки вида:

```
Transfer 5.25 MTL from GDLT..AYXI to CCPG..6V6B
```

**Важно:** рендер делаем сами внутри `mmwb_bot`, не через
`get_web_decoded_xdr` → `eurmtl.me/remote/decode`. Референс — коммит `aece3d02`
в `../eurmtl.me`:
- `services/xdr_parser.py::_render_auth_sub_invocation_summaries`,
  `_render_sub_invocation_summaries`, `_render_sub_invocation_summary`,
  `_render_call_argument`, `_decode_contract_address_to_string`,
  `_decode_sc_symbol`;
- `other/stellar_soroban.py::read_token_contract_display_name`
  (кеш 30 дней, maxsize 256, вызывает `read_contract_string` c `name()`).

Перенести эту логику в `bot/other/` или `bot/infrastructure/` как отдельный
модуль (например, `bot/other/soroban_render.py`), без зависимости на quart/
grist/прочее из eurmtl.me.

## Files/Directories To Change

Часть A (check_xdr):
- `bot/other/stellar_tools.py` — расширить `stellar_check_xdr` логикой для
  `InvokeHostFunction` в ветке `for_free_account`.
- `bot/core/constants.py` — уже содержит `XLM_SOROBAN_CONTRACT`, будет
  импортироваться в `stellar_tools.py`.
- `bot/tests/other/test_stellar_tools.py` — тесты allow/deny для Soroban.

Часть B (локальный превью):
- `bot/other/soroban_render.py` (новый) — портированная логика рендера
  sub_invocation → `Transfer X TOKEN from A to B`. Использует py-stellar-base
  SorobanServer для `read_contract_string("name")` с локальным TTL-кешем.
- `bot/other/stellar_tools.py` — публичная функция
  `render_soroban_sub_invocations(xdr) -> list[str]`, обёртка над модулем выше.
- `bot/routers/sign.py` — в `cmd_check_xdr` после успешной валидации, если
  XDR содержит `InvokeHostFunction` c непустыми `sub_invocations`, собрать
  превью и показать через `cmd_show_sign` **до** `cmd_ask_pin`.
- `webapp/app.py` — добавить в `TxData` поле `sub_invocation_summary:
  list[str]`, заполнять через тот же рендер при выдаче `/api/tx/{id}`.
- `webapp/templates/sign.html` — отрисовать `sub_invocation_summary` над
  кнопками подписи как отдельный блок.
- `bot/tests/other/test_soroban_render.py` (новый) — юнит-тесты рендера на
  заготовленных XDR-фикстурах (пользователь пришлёт 4 транзакции).
- `bot/tests/routers/test_sign.py` (или соседний) — тест автоматического
  показа превью перед PIN для Soroban XDR.

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "давай Б" — пользователь подтвердил путь B (рендер превью) после предъявления
> списка файлов: `bot/other/stellar_tools.py`, `bot/other/soroban_render.py`,
> `bot/routers/sign.py`, `webapp/app.py`, `webapp/templates/sign.html`,
> `bot/tests/other/test_stellar_tools.py`, `bot/tests/other/test_soroban_render.py`,
> `bot/tests/fixtures/soroban/*.xdr`.

## Change Plan

Часть A (whitelist для free):
1. [x] Получить от пользователя 4 образца XDR (allow не-XLM transfer; deny
       без sub_invocations; deny корневой XLM_SOROBAN_CONTRACT; deny вложенный
       XLM_SOROBAN_CONTRACT) — сохранить в `bot/tests/fixtures/soroban/`.
2. [x] В `bot/other/stellar_tools.py::stellar_check_xdr` для
       `InvokeHostFunction` под `for_free_account`:
       - транзакция должна содержать **ровно одну** операцию
         `InvokeHostFunction` (ограничение Soroban);
       - требовать непустой `auth`, хотя бы одна `auth_entry.root_invocation`
         должна иметь непустые `sub_invocations`;
       - рекурсивно обойти дерево
         `root_invocation` + все `sub_invocations` и проверить, что ни один
         `contract_address` (включая корневой
         `host_function.invoke_contract.contract_address`) не равен
         `XLM_SOROBAN_CONTRACT`;
       - каждая `sub_invocation` в дереве должна быть вызовом функции
         `transfer` (whitelist по `function_name`); `transfer_from`,
         `approve`, `mint`, `burn` и любые другие — отказ;
       - любое другое — отказ.
3. [x] Импортировать `XLM_SOROBAN_CONTRACT` из `core.constants`.
4. [x] Юнит-тесты на фикстурах:
       - (a) non-XLM transfer с sub_invocations → allow;
       - (b) Soroban без sub_invocations → deny;
       - (c) корневой XLM_SOROBAN_CONTRACT → deny;
       - (d) вложенный XLM_SOROBAN_CONTRACT → deny;
       - (e) sub_invocation с `transfer_from`/`approve`/неизвестной функцией → deny;
       - (f) существующие не-Soroban кейсы не сломаны.

Часть B (локальный превью):
5. [x] Создать `bot/other/soroban_render.py`: портировать из
       `eurmtl.me/services/xdr_parser.py` функции `_decode_sc_symbol`,
       `_decode_contract_address_to_string`, `_decode_sc_string_value`,
       `_render_call_argument`, `_render_auth_sub_invocation_summaries`,
       `_render_sub_invocation_summaries`, `_render_sub_invocation_summary`,
       `_format_sub_invocation_amount`, `decode_scval` (минимально нужное
       подмножество). Без зависимости на quart/grist.
6. [x] Портировать `read_token_contract_display_name` из
       `eurmtl.me/other/stellar_soroban.py`: использовать
       `SorobanServer` py-stellar-base, локальный async TTL-кеш
       (`async_cache_with_ttl` или существующий helper в `mmwb_bot`).
7. [x] Публичная функция
       `render_soroban_sub_invocations(xdr: str) -> list[str]`:
       принимает XDR, возвращает plain-text строки превью (без HTML-ссылок —
       для бота), либо пустой список, если транзакция не содержит
       `InvokeHostFunction` с `sub_invocations`.
8. [x] В `bot/routers/sign.py::cmd_check_xdr` после успешной валидации XDR
       и **до** `cmd_ask_pin` вычислить `render_soroban_sub_invocations(xdr)`;
       если список непустой — показать его пользователю через `cmd_show_sign`
       (или отдельный send_message), затем запросить PIN.
9. [x] `webapp/app.py`: расширить `TxData` полем
       `sub_invocation_summary: list[str]`, заполнять из
       `render_soroban_sub_invocations(unsigned_xdr)`.
10. [x] `webapp/templates/sign.html`: отрисовать `sub_invocation_summary` как
        блок над кнопками подписи (список строк).
11. [x] Тесты: `bot/tests/other/test_soroban_render.py` на фикстурах из п.1;
        тест роутера подписи на авто-показ превью; тест webapp endpoint.
12. [x] `just check-fast` зелёный.

## Resolved

- Путь к sub_invocations: `operation.auth[*].root_invocation.sub_invocations` —
  подтверждено.
- InvokeHostFunction: в транзакции может быть только **одна** такая операция.
- XLM_SOROBAN_CONTRACT: проверяем **рекурсивно** по всему дереву инвокаций.
- Автопревью: показывать **только** при наличии непустых `sub_invocations`.
- Рендер превью: делаем **локально** в `mmwb_bot`, без обращения к
  `eurmtl.me/remote/decode`.

## Open Questions

- **Формат отображения в webapp vs bot:** в боте plain text (HTML-ссылки не
  обязательны), в webapp — можно добавить копируемые адреса. Уточнить при
  реализации.
- **Rpc URL для `read_contract_string("name")`:** использовать существующий
  конфиг или захардкодить `https://soroban-rpc.mainnet.stellar.gateway.fm`
  как в eurmtl.me.
- **Fallback при недоступном RPC:** если `read_token_contract_display_name`
  упал — показывать сокращённый contract_id (`CAFX..SISM`), а не ошибку.
- **4 тестовые транзакции:** пользователь пришлёт образцы для фикстур.

## Verification

- `just check-fast`
- Новые тесты в `bot/tests/` зелёные.
- Ручная проверка 1: free-кошелёк, отправить `web+stellar:tx?xdr=...` с
  Soroban transfer не-XLM токена → должен показаться превью `Transfer X TOKEN
  from ... to ...` и дойти до PIN.
- Ручная проверка 2: free-кошелёк, Soroban transfer XLM (через
  `XLM_SOROBAN_CONTRACT`) → `bad_xdr`.
- Ручная проверка 3: обычный кошелёк, тот же Soroban-XDR → превью виден,
  подпись проходит.
- Ручная проверка 4: webapp `/sign/<tx_id>` с Soroban XDR → `Transfer ...`
  отображается над кнопками подписи.

## Follow-up fix (2026-04-15)

First iteration sent the preview as a standalone chat message right before
`cmd_ask_pin`. In practice it was auto-deleted by the next sign step faster
than the user could read it. Fix: stash the preview string in FSM state
(`soroban_preview`) and prepend it to the `cmd_ask_pin` message across all
four branches (PIN, password, no-password "да/нет" for free wallets, and
WebApp biometric prompt), so the preview lives on the same message that
carries the sign keyboard. No new behaviour — only display placement.

Also shorten G-addresses in the rendered line the same way contract
addresses are shortened, so the preview stays compact:
`Transfer 0.0000022 EURMTL from GDLT..AYXI to CAFX..SISM`.

Second pass: make all `cmd_ask_pin` branches read naturally when a
Soroban preview is available. When `soroban_preview` is set, build a
shared `sign_header` via the existing `biometric_sign_prompt` template
("Подтвердите транзакцию:\n\n{}") and use it as the top of the message
for every branch:

- pin_type 1 (PIN): header → enter_password → stars → long_line, drops
  the `confirm_send_mini_xdr` boilerplate.
- pin_type 2 (password): header → send_password, drops boilerplate.
- pin_type 0 (free да/нет): header replaces the verbose
  `confirm_send_mini` blurb entirely.
- pin_type 10 (WebApp): same header, no change vs. first pass.

Without a preview, every branch keeps its original text.
