# 2026-10-07-cancel-offer-notification: correct notifications for cancelled offers

## Context

Уведомление `info_sell_offer` печатает «is selling 0 USDM for EURMTL»,
когда на самом деле ордер УДАЛЁН: в Stellar `manage_sell_offer` с
`amount = 0` и существующим `offer_id` — это отмена ордера. Пример из
прода: операция 278387238822731777 (аккаунт GCPO..MXY7, USDM→EURMTL,
price 1, amount 0, offer_id 1822268137; ордер действительно исчез из
списка живых). Бот должен писать «отменил ордер», а не «продаёт 0».

То же касается `manage_buy_offer` (amount = 0 + offer_id > 0 = отмена
buy-ордера). Форматирование amount=0 как «продаёт 0» — некорректное
сообщение; исправляется в `decode_db_effect`.

Согласовано с владельцем:
- Отмена определяется ТОЛЬКО как `offer_amount == 0 and offer_id > 0`
  (семантика Stellar: amount=0 при существующем offer_id = delete).
  Никаких проверок «ордер ещё жив в Horizon» — нотификатор не ходит в сеть.
- Новые ключи локалей: `info_sell_offer_cancelled`, `info_buy_offer_cancelled`
  в 6 файлах (en, ru, ua, me, am, hy).
- Тексты упоминаний в существующих ключах не меняем — правим только
  ветку рендера.
- Попутно удалить дублирующую строку `op.offer_amount = ...` в
  `notification_service.py` (строка 793-795, присваивание дважды).

## Files/Directories To Change

- `bot/infrastructure/utils/notification_utils.py`
- `bot/infrastructure/services/notification_service.py` (только дубль
  присваивания)
- `bot/langs/en.json`
- `bot/langs/ru.json`
- `bot/langs/ua.json`
- `bot/langs/me.json`
- `bot/langs/am.json`
- `bot/langs/hy.json`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/active/2026-10-07-cancel-offer-notification.md`
  (жизненный цикл плана)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User said: «Го» (m00575) — GO в ответ на план агента с перечисленными
> файлами: notification_utils.py, notification_service.py (дубль),
> bot/langs/*.json (6 шт), test_notification_webhook.py + план.

## Change Plan

1. [x] `notification_utils.py` — в ветках `manage_sell_offer` и
       `manage_buy_offer`: если `offer_amount == 0 and offer_id > 0`,
       рендерить новый ключ отмены (с account_link, selling/buying asset
       и op_link), иначе прежний текст.
2. [x] `notification_service.py:792-795` — убрать дубль присваивания
       `op.offer_amount`.
3. [x] 6 локалей — добавить `info_sell_offer_cancelled` /
       `info_buy_offer_cancelled` рядом с существующими ключами.
4. [x] Тесты: red→green — отмена sell и buy (amount=0, offer_id>0) даёт
       текст отмены; обычные ордера (amount>0) не меняются; ордер с
       amount=0 и offer_id=0 (теоретически невозможен, но пусть падает в
       обычную ветку, а не в отмену).
5. [x] `just test-fast` + `just lint` зелёные.
6. [x] Ревью agy (2 круга, `docs/drafts/agy_cancel_offer_review*.md`):
       guard `(offer_id or 0) > 0`, симметричный buy-тест, сквозной
       парсинг прод-payload'а, снят лишний `async` с синхронных
       decode-тестов.

## Risks / Open Questions

- Если старые сохранённые уведомления в БД уже отрендерены — их текст не
  переписывается, меняется только рендер новых.
- Отмена buy-ордера редко встречается в прода, но симметрична.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py -q`
- `just test-fast` и `just lint`.
