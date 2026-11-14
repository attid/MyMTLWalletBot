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

## Покрытые маршруты

| Маршрут | Тест | Что проверяется |
|---|---|---|
| создать кошелёк | `test_wallet_lifecycle.py` | строка в БД, аккаунт в сети, trustline |
| принять | `test_receive.py` | адрес и QR на экране |
| отправить | `test_send.py` | 2 XLM доходят; free wallet блокируется |
| ордер | `test_trade_swap.py` | оффер реально появляется в книге |
| swap | `test_trade_swap.py` | купленный актив приходит на баланс |

Итого 6 тестов, ~3 минуты прогона (friendbot + транзакции в testnet).

## Что ещё не покрыто

- SEP-24 флоу против живого анкора (нужен анкор в testnet);
- WebApp-подпись (биометрия) — там отдельный контур Redis/WebApp;
- чеки, TON/Tron-ветки.

## Найденные E2E дефекты

- **Свободный кошелёк мог отправить XLM через мастер отправки** (`/send` →
  подтверждение → PIN): политика free-wallet применялась только в
  `cmd_check_xdr`, а `SigningFacade` подписывал XDR без проверки. Срез
  `signing-facade-free-wallet-guard` перенёс проверку в фасад — теперь
  `test_free_wallet_cannot_send_native_xlm` зелёный.
