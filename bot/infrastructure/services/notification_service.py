"""
Notification service for handling Stellar operations webhooks.

Notifier payload format documentation:
https://github.com/Montelibero/operations-notifier/blob/master/RESPONSE_EXAMPLES.md
"""

import asyncio
import aiohttp
from aiohttp import web
from loguru import logger
from sqlalchemy import select
from typing import Optional, Any
from datetime import datetime
from urllib.parse import quote
import base64
import sentry_sdk

from db.db_pool import DatabasePool
from db.models import MyMtlWalletBot, NotificationFilter
from core.models.notification import NotificationOperation
from aiogram.fsm.storage.base import StorageKey
from routers.start_msg import cmd_info_message
from infrastructure.utils.notification_utils import decode_db_effect
from stellar_sdk import Keypair
import time
import json
from collections import OrderedDict
from enum import Enum

SAFE = "-_.!~*'()"


class NotifierHeaders(str, Enum):
    ID = "X-Client-ID"
    SIGNATURE = "X-Signature"
    TIMESTAMP = "X-Timestamp"


class NotificationService:
    def __init__(
        self,
        config: Any,
        db_pool: DatabasePool,
        bot: Any,
        localization_service: Any,
        dispatcher: Any = None,
        notification_history: Any = None,
    ):
        self.config = config
        self.db_pool = db_pool
        self.bot = bot
        self.dispatcher = dispatcher
        self.localization_service = localization_service
        self.notification_history = notification_history

        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.notified_operations: set[str] = set()
        # Track transaction hashes to prevent duplicate notifications
        # Using list as a FIFO queue to keep track of the order of transactions
        self.notified_transactions_queue: list[str] = []
        self.notified_transactions_set: set[str] = set()
        self.max_cache_size = (
            100  # Reduced cache size - sufficient for short-term deduplication
        )

        # Nonce management
        self._nonce = 0
        self._nonce_lock = asyncio.Lock()

        # Notifier public key (fetched from /api/status)
        self._notifier_public_key: Optional[str] = None

        # Log initialization
        if not self.bot:
            logger.warning("NotificationService initialized with bot=None")

    def _encode_url_params(self, pairs: list) -> str:
        """
        Encodes parameters to match stellar_notifier logic (key=val&key=val).
        Sorts keys alphabetically to ensure matching order with JS Object.keys().
        """
        # Convert list of tuples to dict to easy sort, then back to sorted list
        # Or just sort the list of tuples by key
        pairs.sort(key=lambda x: x[0])

        parts = []
        for k, v in pairs:
            if isinstance(v, (list, tuple)):
                v = ",".join(str(x) for x in v)
            parts.append(f"{quote(str(k), safe=SAFE)}={quote(str(v), safe=SAFE)}")
        return "&".join(parts)

    def _sign_payload(self, payload: str) -> str:
        """Signs the payload string using the service secret."""
        try:
            kp = Keypair.from_secret(self.config.service_secret.get_secret_value())
            # Notifier ожидает сигнатуру в HEX формате
            signature = kp.sign(payload.encode("utf-8")).hex()
            return f"ed25519 {kp.public_key}.{signature}"
        except Exception as e:
            logger.error(f"Failed to sign payload: {e}")
            raise e

    # ... (skipping lines)
    # _get_active_subscriptions moved to end of class to unify implementation

    async def _fetch_notifier_public_key(self):
        """Fetches the Notifier's public key from /api/status."""
        if not self.config.notifier_url:
            logger.warning("Notifier URL not configured, cannot fetch public key")
            return
            
        if self.config.test_mode:
            logger.info("Test mode enabled: Skipping Notifier public key fetch")
            return

        url = f"{self.config.notifier_url}/api/status"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        public_key = data.get("publicKey")
                        if public_key:
                            self._notifier_public_key = public_key
                            logger.info(
                                f"Fetched Notifier public key: {public_key[:20]}..."
                            )
                        else:
                            logger.warning(
                                "Public key not found in /api/status response"
                            )
                    else:
                        logger.error(
                            f"Failed to fetch Notifier status: {resp.status} {await resp.text()}"
                        )
        except Exception as e:
            logger.error(f"Error fetching Notifier public key: {e}")

    async def _fetch_initial_nonce(self):
        """Fetches the current nonce from the Notifier to initialize the local counter."""
        if not self.config.notifier_url:
            return

        if self.config.test_mode:
            logger.info("Test mode enabled: Skipping initial nonce fetch")
            self._nonce = int(time.time() * 1000)
            return

        # If using Token Auth, we don't need nonce for auth, but still might need it for consistent ordering
        # However, Notifier 0.5.3 with Token Auth might not enforce nonce check the same way.
        # But for backward compatibility or if Notifier still tracks nonce per token user, we keep it.
        # Typically Token Auth is stateless or simple. Let's assume we still use nonce for logic consistency.

        # If token is present, we might not need to sign nonce request
        if getattr(self.config, "notifier_auth_token", None):
            # For token auth, we just trust local counter or fetch without signature if supported
            # But GET /api/nonce requires signature in old version.
            # In 0.5.3 with Token auth, maybe we can just GET /api/nonce with token?
            # Let's try fetching with token auth
            headers = {"Authorization": self.config.notifier_auth_token}
            url = f"{self.config.notifier_url}/api/nonce"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            remote_nonce = int(data.get("nonce", 0))
                            self._nonce = remote_nonce + 1000
                            logger.info(f"Initialized nonce (TokenAuth): {self._nonce}")
                            return
            except Exception as e:
                logger.warning(f"TokenAuth fetch nonce failed: {e}")

        try:
            kp = Keypair.from_secret(self.config.service_secret.get_secret_value())
            public_key = kp.public_key

            # Sign "nonce:<public_key>"
            payload = f"nonce:{public_key}"
            signature = kp.sign(payload.encode("utf-8")).hex()
            auth_header = f"ed25519 {public_key}.{signature}"

            headers = {"Authorization": auth_header}
            url = f"{self.config.notifier_url}/api/nonce"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        remote_nonce = int(data.get("nonce", 0))
                        # Set local nonce to remote nonce + safety margin (e.g., 1000)
                        # to avoid race conditions if multiple instances are starting
                        self._nonce = remote_nonce + 1000
                        logger.info(
                            f"Initialized nonce from Notifier: {remote_nonce} -> Set local to {self._nonce}"
                        )
                    else:
                        logger.warning(
                            f"Failed to fetch initial nonce: {resp.status} {await resp.text()}"
                        )
                        logger.warning(f"Headers: {resp.headers}")
                        # Fallback to current time if fetch fails, to ensure we are likely ahead
                        self._nonce = int(time.time() * 1000)
                        logger.info(
                            f"Fallback to time-based initial nonce: {self._nonce}"
                        )

        except Exception as e:
            logger.error(f"Error fetching initial nonce: {e}")
            # Fallback
            self._nonce = int(time.time() * 1000)

    async def _get_next_nonce(self) -> int:
        """Returns the next sequential nonce."""
        async with self._nonce_lock:
            # Lazy init if still 0 (though start_server should have called it)
            if self._nonce == 0:
                await self._fetch_initial_nonce()

            self._nonce += 1
            return self._nonce

    def _verify_webhook_signature(
        self, request: web.Request, body_bytes: bytes
    ) -> bool:
        """Verifies the Notifier's signature on the webhook (X-Request-ED25519-Signature)."""
        # Используем публичный ключ полученный из /api/status
        if not self._notifier_public_key:
            logger.warning(
                "Notifier public key not available, skipping signature verification"
            )
            return True  # Режим без проверки, если ключ не получен

        sig_base64 = request.headers.get("X-Request-ED25519-Signature")
        if not sig_base64:
            logger.warning("Missing signature header on webhook")
            return False  # Fail validation if signature missing but key configured

        try:
            # Notifier отправляет подпись в Base64
            signature = base64.b64decode(sig_base64)
            kp = Keypair.from_public_key(self._notifier_public_key)
            # Verify raw body bytes (важно: используем сырое тело, не пересобранный JSON)
            kp.verify(body_bytes, signature)
            logger.info("✓ Webhook signature verified successfully")
            return True
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            logger.error(
                f"Signature header (first 100 chars): {sig_base64[:100] if sig_base64 else 'N/A'}"
            )
            logger.error(f"Body size: {len(body_bytes)} bytes")
            return False  # Fail validation

    async def start_server(self):
        """Starts the internal Webhook Listener."""
        # Safety check
        if not self.bot:
            logger.error("Cannot start webhook server: bot is not initialized")
            return

        if self.config.test_mode:
            logger.info("Test mode enabled: Webhook listener will not start")
            return

        # Fetch Notifier's public key from /api/status
        await self._fetch_notifier_public_key()

        # Initialize nonce
        await self._fetch_initial_nonce()

        app = web.Application()
        app.router.add_post("/webhook", self.handle_webhook)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        # Determine host/port. Default 0.0.0.0 to be accessible from Docker network
        port = self.config.webhook_port
        self.site = web.TCPSite(self.runner, "0.0.0.0", port)

        logger.info(f"Starting Webhook Listener on port {port}")
        await self.site.start()

    async def stop(self):
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def handle_webhook(self, request: web.Request):
        try:
            # 1. Читаем байты (нужны для проверки подписи)
            body_bytes = await request.read()
            if not body_bytes:
                return web.Response(text="Empty payload", status=400)

            # 2. Проверяем подпись
            if not self._verify_webhook_signature(request, body_bytes):
                # Пользователь: "если не верно просто ругнемся не будем игнорировать" -> значит отклоняем (403)
                return web.Response(text="Invalid Signature", status=403)

            # 3. Парсим JSON
            try:
                payload = json.loads(body_bytes)
            except json.JSONDecodeError:
                return web.Response(text="Invalid JSON", status=400)

            # 4. Обрабатываем
            await self.process_notification(payload)
            return web.Response(text="OK")

        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return web.Response(text=f"Error: {e}", status=500)

    async def process_notification(self, payload: dict):
        """Process the notification payload."""
        op_info = payload.get("operation", {})

        # Исправлено: Однократное корректное определение ID
        resource_id = (
            payload.get("subscription")
            or op_info.get("account")
            or op_info.get("source_account")
            or op_info.get("to")
            or op_info.get("destination")
        )

        if not resource_id:
            logger.warning(
                f"Could not determine resource_id. Payload keys: {payload.keys()}"
            )
            return

        # Deduplicate by Stellar operation ID
        stellar_op_id = op_info.get("id")
        if stellar_op_id and stellar_op_id in self.notified_operations:
            logger.info(f"Skipping duplicate operation {stellar_op_id}")
            return
        if stellar_op_id:
            self.notified_operations.add(stellar_op_id)
            if len(self.notified_operations) > 1024:
                self.notified_operations.clear()

        # 2. Convert Payload to TOperations-like object
        op_data_mapped = self._map_payload_to_operation(payload)
        if not op_data_mapped:
            logger.warning("Could not map payload to operation")
            return

        # 3. Find Users watching this wallet
        involved_accounts = {op_data_mapped.for_account, op_data_mapped.from_account}
        # Add trustor for set_trustline_flags operation
        op_info = payload.get("operation", {})
        if op_info.get("trustor"):
            involved_accounts.add(op_info.get("trustor"))
        involved_accounts.discard(None)

        if not involved_accounts:
            return

        async with self.db_pool.get_session() as session:
            stmt = select(MyMtlWalletBot).where(
                MyMtlWalletBot.public_key.in_(involved_accounts),
                MyMtlWalletBot.need_delete == 0,
                MyMtlWalletBot.user_id > 0,
            )
            result = await session.execute(stmt)
            wallets = result.scalars().all()

            for wallet in wallets:
                await self._send_notification_to_user(wallet, op_data_mapped)
                
                # Special case: Self-payment to the same wallet.
                # User wants to see both "Sent" and "Received" messages.
                if (op_data_mapped.operation == "payment" and 
                    wallet.public_key == op_data_mapped.from_account and 
                    wallet.public_key == op_data_mapped.for_account):
                    # Trigger the "Debit" (Sent) perspective, as the default is "Credit" (Received)
                    # when decode_for == for_account.
                    await self._send_notification_to_user(wallet, op_data_mapped, force_perspective='debit')

        # 4. Process internal trades (for Match Orders / Makers)
        trades = payload.get("operation", {}).get("trades", [])
        if trades:
            # Collect makers (sellers)
            makers = set()
            for trade in trades:
                if trade.get("type") == "order_book":
                    seller = trade.get("seller_id")
                    if seller:
                        makers.add(seller)

            if makers:
                async with self.db_pool.get_session() as session:
                    stmt = select(MyMtlWalletBot).where(
                        MyMtlWalletBot.public_key.in_(makers),
                        MyMtlWalletBot.need_delete == 0,
                        MyMtlWalletBot.user_id > 0,
                    )
                    result = await session.execute(stmt)
                    maker_wallets = result.scalars().all()
                    
                    # Create a map for quick lookup
                    maker_map = {w.public_key: w for w in maker_wallets}


                        
                    # Prepare common data
                    tx_hash = payload.get("transaction", {}).get("hash")
                    op_info = payload.get("operation", {})            # Helper to create trade op
            for i, trade in enumerate(trades):
                if trade.get("type") == "order_book":
                    seller = trade.get("seller_id")
                    maker_wallet = maker_map.get(seller)
                    
                    if maker_wallet:
                        # Ensure we use the Stellar Operation ID
                        stellar_op_id = op_info.get("id")
                        if not stellar_op_id and tx_hash:
                            stellar_op_id = f"{tx_hash}_{i}"
                        
                        op_trade = NotificationOperation(
                            id=f"{stellar_op_id}_t{i}",
                            operation="trade",
                            dt=datetime.utcnow(),
                            for_account=seller,
                            from_account=seller, # It's their trade
                            transaction_hash=tx_hash or "",
                        )

                        # Helper to safely get asset code or "XLM" for native
                        def get_trade_asset(trade_item, side):
                            # side is "sold" or "bought"
                            # Try explicit code first
                            code = trade_item.get(f"{side}_asset_code")
                            if code:
                                return code
                            
                            type_ = trade_item.get(f"{side}_asset_type")
                            if type_ in ("native", 0):
                                return "XLM"
                            
                            # Try nested object if flat fields missing
                            asset_obj = trade_item.get(f"asset_{side}") or {}
                            if asset_obj.get("asset_code"):
                                return asset_obj.get("asset_code")
                            if asset_obj.get("asset_type") in ("native", 0):
                                return "XLM"
                            
                            return "?"

                        op_trade.trade_sold_amount = float(trade.get("amount_sold") or 0)
                        op_trade.trade_sold_asset = get_trade_asset(trade, "sold")
                        
                        op_trade.trade_bought_amount = float(trade.get("amount_bought") or 0)
                        op_trade.trade_bought_asset = get_trade_asset(trade, "bought")
                        
                        await self._send_notification_to_user(maker_wallet, op_trade)
        
    def _map_payload_to_operation(self, payload: dict) -> Optional[NotificationOperation]:
        """Maps JSON payload to NotificationOperation entity."""
        try:
            op_data = payload.get("operation")
            if not op_data:
                # logger.warning(f"No operation data in payload: {payload.keys()}")
                return None

            op_type = op_data.get("type")

            # Map common fields
            # Extract memo if available
            memo = None
            transaction_data = payload.get("transaction", {})
            if transaction_data and "memo" in transaction_data:
                memo_data = transaction_data.get("memo", {})
                if memo_data:
                    memo_type = memo_data.get("type")
                    memo_value = memo_data.get("value")

                    if (
                        memo_type == "text"
                        and isinstance(memo_value, dict)
                        and "data" in memo_value
                    ):
                        # Handle Buffer type memo
                        try:
                            memo_bytes = bytes(memo_value.get("data", []))
                            memo = f'TEXT: "{memo_bytes.decode("utf-8")}"'
                        except Exception as e:
                            logger.error(f"Failed to decode memo bytes: {e}")
                            memo = "TEXT: (binary data)"
                    elif memo_value:
                        memo = f'{memo_type.upper()}: "{memo_value}"'

            op = NotificationOperation(
                id=str(op_data.get("id", "")),
                operation=op_type,
                dt=datetime.utcnow(),
                from_account=op_data.get("source_account")
                or op_data.get("from")
                or op_data.get("account"),
                transaction_hash=payload.get("transaction", {}).get("hash"),
                memo=memo,
            )

            # Type specific mapping
            if op_type == "payment":
                op.for_account = op_data.get("to") or op_data.get("destination")
                op.payment_amount = float(op_data.get("amount", 0))
                op.payment_asset = op_data.get("asset", {}).get("asset_code", "XLM")
                if op_data.get("asset", {}).get("asset_type") in ("native", 0):
                    op.payment_asset = "XLM"

            elif op_type == "create_account":
                op.for_account = op_data.get("account") or op_data.get("destination")
                op.payment_amount = float(op_data.get("amount", 0))
                op.payment_asset = "XLM"

            elif op_type in ("path_payment_strict_send", "path_payment_strict_receive"):
                op.for_account = (
                    op_data.get("to")
                    or op_data.get("destination")
                    or op_data.get("account")
                )
                
                # Helper for asset code
                def get_asset_code_local(asset_obj):
                    if not asset_obj:
                        return "XLM"
                    if asset_obj.get("asset_type") in ("native", 0, "0"):
                        return "XLM"
                    return asset_obj.get("asset_code", "XLM")

                # Destination Asset (Received) -> path_received
                op.path_received_asset = get_asset_code_local(op_data.get("asset"))
                
                # Source Asset (Sent) -> path_sent
                op.path_sent_asset = get_asset_code_local(op_data.get("source_asset"))

                # Amount Mapping depends on type
                if op_type == "path_payment_strict_send":
                    # We sent exact 'amount' of source_asset
                    # We received at least 'dest_min' of asset, but prefer 'dest_amount' (actual)
                    op.path_sent_amount = float(op_data.get("amount", 0)) # Sent
                    
                    # Use actual dest_amount if available (Notifier update), else dest_min
                    dest_amt = op_data.get("dest_amount")
                    if dest_amt:
                        op.path_received_amount = float(dest_amt)
                    else:
                        op.path_received_amount = float(op_data.get("dest_min", 0)) # Received (Approx/Min)
                else:
                    # path_payment_strict_receive
                    # We received exact 'amount' of asset
                    # We sent at most 'source_max' of source_asset, but prefer 'source_amount' (actual)
                    op.path_received_amount = float(op_data.get("amount", 0)) # Received
                    
                    # Use actual source_amount if available (Notifier update), else source_max
                    src_amt = op_data.get("source_amount")
                    if src_amt:
                        op.path_sent_amount = float(src_amt)
                    else:
                        op.path_sent_amount = float(op_data.get("source_max", 0)) # Sent (Approx/Max)

            elif op_type == "manage_sell_offer":
                op.for_account = op_data.get("account")
                # Amount to sell
                op.offer_amount = float(op_data.get("amount", 0))
                # Amount to sell
                op.offer_amount = float(op_data.get("amount", 0))
                
                # Check offer_id, fallback to created_offer_id if 0
                o_id = int(op_data.get("offer_id", 0))
                if o_id == 0:
                     o_id = int(op_data.get("created_offer_id", 0))
                op.offer_id = o_id
                
                # Selling Asset
                if "source_asset" in op_data:
                    op.offer_selling_asset = op_data.get("source_asset", {}).get("asset_code", "XLM")
                    if op_data.get("source_asset", {}).get("asset_type") in ("native", 0):
                        op.offer_selling_asset = "XLM"
                else:
                    op.offer_selling_asset = "unknown"

                # Buying Asset
                op.offer_buying_asset = op_data.get("asset", {}).get("asset_code", "XLM")
                if op_data.get("asset", {}).get("asset_type") in ("native", 0):
                    op.offer_buying_asset = "XLM"

                # Price per unit
                op.offer_price = float(op_data.get("price", 0))

                # Store offer ID in transaction_hash for reuse?? 
                # Model has transaction_hash but we misuse it for offerId in legacy code?
                # Let's keep existing logic but maybe comment it.
                # "Store offer ID in transaction_hash for reuse" - seems hacky but maintaining behavior.
                if op_data.get("offerId"):
                     # We can't overwrite transaction_hash if it's real hash. 
                     # But legacy code did: op.transaction_hash = op_data.get("offerId", "")
                     # Let's verify if 'transaction_hash' is used for anything else.
                     # It is used in notification_service to dedup? No, dedup uses stellar_op_id.
                     # It is NOT used in decode_db_effect directly.
                     # It seems safe to leave original tx hash.
                     pass 

            elif op_type == "manage_buy_offer":
                op.for_account = op_data.get("account")
                # Amount of buying asset
                op.offer_amount = float(op_data.get("amount", 0))
                
                # Check offer_id, fallback to created_offer_id if 0
                o_id = int(op_data.get("offer_id", 0))
                if o_id == 0:
                     o_id = int(op_data.get("created_offer_id", 0))
                op.offer_id = o_id
                
                # Buying Asset
                if "buying_asset" in op_data:
                    op.offer_buying_asset = op_data.get("buying_asset", {}).get("asset_code", "XLM")
                    if op_data.get("buying_asset", {}).get("asset_type") in ("native", 0):
                        op.offer_buying_asset = "XLM"
                else:
                    op.offer_buying_asset = "unknown"

                # Price per unit
                op.offer_price = float(op_data.get("price", 0))

                # Selling Asset
                if "selling_asset" in op_data:
                    op.offer_selling_asset = op_data.get("selling_asset", {}).get("asset_code", "XLM")
                    if op_data.get("selling_asset", {}).get("asset_type") in ("native", 0):
                        op.offer_selling_asset = "XLM"
                else:
                    op.offer_selling_asset = "unknown"

            elif op_type == "manage_data":
                op.for_account = op_data.get("source_account") or op_data.get("account")
                op.data_name = op_data.get("name") or "DATA"
                
                # Decode value from Base64
                data_value = op_data.get("value")
                if data_value:
                    try:
                        op.data_value = base64.b64decode(data_value).decode("utf-8")
                    except Exception:
                         # Fallback if not utf-8 text or decode error
                        op.data_value = str(data_value)
                else:
                    # Value is None -> Data Removed
                    op.data_value = None

            else:
                op.for_account = (
                    op_data.get("to")
                    or op_data.get("account")
                    or op_data.get("trustor")  # change_trust
                    or op_data.get("source_account")
                )
                # op.amount = 0.0 # Default
                # op.asset_code = "UNK" # Default

                # Log unknown operation type (skip known ops that just need cache reset)
                known_cache_only_ops = {
                    "change_trust",
                    "claim_claimable_balance",
                    "clawback",
                    "create_claimable_balance",  # only notify creator, not claimants (spam)
                    "invoke_host_function",
                    "set_options",
                    "set_trustline_flags",
                }
                if op_type not in known_cache_only_ops:
                    logger.warning(f"Unknown operation type: {op_type}, payload: {json.dumps(payload, indent=2)}")

                    # Send to Sentry if initialized
                    if sentry_sdk.Hub.current.client is not None:
                        sentry_sdk.capture_message(
                            f"Unknown operation type: {op_type}",
                            level="warning",
                            extras={"payload": payload, "op_type": op_type}
                        )

            return op

        except Exception as e:
            logger.error(f"Mapping error: {e}")
            return None

    async def _send_notification_to_user(
        self, wallet: MyMtlWalletBot, operation: NotificationOperation, force_perspective: Optional[str] = None
    ):
        if wallet.user_id is None:
            return
        user_id = int(wallet.user_id)

        try:
            message_text = decode_db_effect(
                operation,
                str(wallet.public_key),
                user_id,
                localization_service=self.localization_service,
                force_perspective=force_perspective,
            )

            if not message_text:
                return

            async with self.db_pool.get_session() as session:
                stmt_filter = select(NotificationFilter).where(
                    NotificationFilter.user_id == user_id
                )
                result_filter = await session.execute(stmt_filter)
                user_filters = result_filter.scalars().all()

            should_send = True
            msg_amount = float(operation.display_amount_value or 0.0)

            for f in user_filters:
                if (
                    (f.public_key is None or f.public_key == wallet.public_key)
                    and (f.asset_code is None or f.asset_code == operation.display_asset_code)
                    and (f.min_amount or 0.0) > msg_amount
                    and f.operation_type == operation.operation
                ):
                    should_send = False
                    break

            if not should_send:
                return

            if not self.bot:
                logger.warning(
                    f"Bot not initialized, cannot send notification to {user_id}"
                )
                return

            fsm_storage_key = StorageKey(
                bot_id=self.bot.id, user_id=user_id, chat_id=user_id
            )
            if self.dispatcher:
                await self.dispatcher.storage.update_data(
                    key=fsm_storage_key, data={"last_message_id": 0}
                )

            await cmd_info_message(
                None,
                user_id,
                message_text,
                operation_id=operation.id,
                public_key=str(wallet.public_key),
                wallet_id=int(wallet.id) if wallet.id else 0,
                bot=self.bot,
                dispatcher=self.dispatcher,
                localization_service=self.localization_service,
            )

            # Save to notification history for filter creation
            if self.notification_history:
                try:
                    self.notification_history.add(
                        user_id=user_id,
                        operation=operation,
                        wallet_id=int(wallet.id) if wallet.id else 0,
                        public_key=str(wallet.public_key),
                    )
                except Exception as history_error:
                    logger.warning(f"Failed to save notification to history: {history_error}")

            # Reset balance cache to ensure user sees updated balance
            # after receiving the transaction notification
            try:
                from infrastructure.persistence.sqlalchemy_wallet_repository import (
                    SqlAlchemyWalletRepository,
                )

                async with self.db_pool.get_session() as session:
                    repo = SqlAlchemyWalletRepository(session)
                    await repo.reset_balance_cache(user_id)
                    await session.commit()
                    logger.debug(f"Balance cache reset for user {user_id}")
            except Exception as cache_error:
                logger.error(
                    f"Failed to reset balance cache for user {user_id}: {cache_error}"
                )

        except Exception as e:
            logger.exception(f"Failed to send notification to {user_id}: {e}")

    async def subscribe(self, public_key: str):
        """Subscribe a wallet to the notifier."""
        # Basic validation for Stellar Public Key (G...)
        if not public_key or not public_key.startswith("G") or len(public_key) != 56:
            return

        if not self.config.notifier_url:
            return

        if self.config.test_mode:
            logger.debug(f"Test mode: Skipping subscription for {public_key}")
            return

        url = f"{self.config.notifier_url}/api/subscription"
        webhook = self.config.webhook_public_url

        # Use sequential nonce
        nonce = await self._get_next_nonce()
        pairs = [("account", public_key), ("nonce", nonce), ("reaction_url", webhook)]

        body_json = json.dumps(OrderedDict(pairs), separators=(",", ":"))

        # Token Auth Logic
        auth_token = getattr(self.config, "notifier_auth_token", None)
        if auth_token:
            headers = {
                "Authorization": auth_token,  # authorization: "token"
                "Content-Type": "application/json",
            }
            payload_str = "TOKEN_AUTH_MODE"
            auth_header = auth_token
        else:
            # Fallback to Signature
            payload_str = self._encode_url_params(pairs)
            auth_header = self._sign_payload(payload_str)
            headers = {"Authorization": auth_header, "Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=body_json, headers=headers) as resp:
                    if resp.status in (200, 201):
                        logger.debug(f"Subscribed {public_key}")
                    else:
                        text = await resp.text()
                        logger.error(
                            f"Failed to subscribe {public_key}: {resp.status} {text}"
                        )
                        # Only log debug details if not token auth (safe)
                        if not auth_token:
                            logger.error(f"DEBUG: Payload Signed: '{payload_str}'")
                            logger.error(f"DEBUG: Auth Header: '{auth_header}'")
                        else:
                            logger.error("DEBUG: Token Auth used.")
            except Exception as e:
                logger.error(f"Exception subscribing {public_key}: {e}")

    async def sync_subscriptions(self):
        """Syncs all DB wallets with Notifier subscriptions.

        Re-subscribes all keys to ensure webhook URL is up-to-date
        (e.g. after moving to a different node).
        """
        if not self.config.notifier_url:
            logger.warning("Notifier URL not set, skipping sync")
            return

        logger.info("Starting subscription sync...")
        try:
            async with self.db_pool.get_session() as session:
                stmt = (
                    select(MyMtlWalletBot.public_key)
                    .where(MyMtlWalletBot.need_delete == 0, MyMtlWalletBot.user_id > 0)
                    .group_by(MyMtlWalletBot.public_key)
                )
                result = await session.execute(stmt)
                db_keys = set(result.scalars().all())

            logger.info(f"DB has {len(db_keys)} wallets, re-subscribing all with webhook {self.config.webhook_public_url}")

            count = 0
            for key in db_keys:
                if not key:
                    continue
                await self.subscribe(key)
                count += 1
                if count % 10 == 0:
                    await asyncio.sleep(0.1)  # Rate limit

            logger.info(f"Sync completed: {count} subscriptions updated.")

        except Exception as e:
            logger.error(f"Sync failed: {e}")

    async def _get_active_subscriptions(self) -> set:
        nonce = await self._get_next_nonce()

        auth_token = getattr(self.config, "notifier_auth_token", None)
        if auth_token:
            headers = {"Authorization": auth_token}
            # Token auth might not require signed params query
            # Just pass nonce if needed or nothing
            # Assuming GET /api/subscription returns list for the token user
            url = f"{self.config.notifier_url}/api/subscription?nonce={nonce}"
        else:
            pairs = [("nonce", nonce)]
            payload_str = self._encode_url_params(pairs)
            auth_header = self._sign_payload(payload_str)
            url = f"{self.config.notifier_url}/api/subscription?{payload_str}"
            headers = {"Authorization": auth_header}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = set()
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    key = item.get("account") or item.get("resource_id")
                                    if key:
                                        results.add(key)
                        return results
                    else:
                        logger.error(
                            f"Get subs failed: {resp.status} {await resp.text()}"
                        )
                        return set()
            except Exception as e:
                logger.error(f"Error fetching subs: {e}")
                return set()
