# E2E-тесты (реальный testnet)

Поднимают те же объекты, что `start.py`: настоящий `StellarService`, настоящие
репозитории, настоящий aiogram-диспетчер. Подменены только Telegram API
(`mock_telegram`) и БД (sqlite в `tmp_path`).

## Запуск

```bash
# только e2e (маркер external)
HORIZON_URLS=https://horizon.stellar.org \
  cd bot && uv run --package mmwb-bot pytest tests/e2e -m external -v
```

Нужны: интернет, доступ к `horizon-testnet.stellar.org` и `friendbot.stellar.org`
(переопределяются через `E2E_HORIZON_URL` и `E2E_FRIENDBOT_URL`).
Обычный `pytest` эти тесты не запускает — маркер `external` отсекается в
`pytest.ini`.

## Что уже покрыто

- `test_wallet_lifecycle.py::test_free_wallet_is_created_in_db_and_on_testnet`
  — нажатие «создать кошелёк» → запись в БД (free, default, wallet_crypto_v2) →
  аккаунт реально создан в testnet → trustline на тестовый актив создан.
  Это ровно тот сценарий, который месяцами не работал и не ловился ночным canary.

## Как устроено

- `SqlitePool` — обёртка с тем же контрактом `get_session()`, что у
  `DatabasePool` (без автокоммита).
- Master-кошелёк (`user_id=0`) и эмитент тестового актива создаются на лету:
  два аккаунта фондируются friendbot'ом, мастер шифруется ключом `"0"` и
  пишется в sqlite.
- `FREE_WALLET_ASSETS` подменяется на тестовый актив: проектные активы
  (USDM/EURMTL/…) существуют только в mainnet.
- Флаги `DISABLE_WORKERS` / `DISABLE_SCHEDULER` выключают фоновые воркеры и
  планировщик, если harness когда-нибудь начнёт поднимать `start.main()`.

## Что ещё не покрыто (следующие срезы)

- отправка XLM между двумя кошельками;
- ордер (`manage_sell_offer`) и проверка оффера в Horizon;
- swap (path payment) — нужен второй актив и оффер/пул;
- приём средств (адрес/QR) — только рендер, без сети.

## Найденные E2E дефекты

- **Свободный кошелёк может отправить XLM через мастер отправки** (`/send` →
  подтверждение → PIN). Политика free-wallet применяется только в
  `cmd_check_xdr` (вставка XDR / URI / sign_tools), а `SigningFacade`
  подписывает XDR без проверки. Тест
  `test_free_wallet_cannot_send_native_xlm` помечен `xfail(strict=True)` и
  станет зелёным, когда проверку добавят в фасад.
