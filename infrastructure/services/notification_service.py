import asyncio
import aiohttp
from aiohttp import web
from loguru import logger
from sqlalchemy import select, update, cast
from typing import Optional, List, Any
from datetime import datetime
from urllib.parse import quote

from db.db_pool import DatabasePool
from db.models import MyMtlWalletBot, TOperations, NotificationFilter
from infrastructure.services.app_context import AppContext
from infrastructure.utils.common_utils import float2str
from other.lang_tools import my_gettext
from aiogram.fsm.storage.base import StorageKey
from routers.start_msg import cmd_info_message
from infrastructure.utils.notification_utils import decode_db_effect
from stellar_sdk import Keypair
import time
import json
from enum import Enum

class NotifierHeaders(str, Enum):
    ID = "X-Client-ID"
    SIGNATURE = "X-Signature" 
    TIMESTAMP = "X-Timestamp"

class NotificationService:
    def __init__(self, config: Any, db_pool: DatabasePool, bot: Any, localization_service: Any, dispatcher: Any = None):
        self.config = config
        self.db_pool = db_pool
        self.bot = bot
        self.dispatcher = dispatcher
        self.localization_service = localization_service
        
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        # Simple cache to deduplicate events if needed. 
        # Using a set with limited size or cleanup mechanism would be better in prod.
        self.notified_operations = set() 

    def _encode_url_params(self, params: dict) -> str:
        """Encodes parameters to match stellar_notifier logic (key=val&key=val)."""
        if not params:
            return ""
        
        SAFE = "-_.!~*'()"
        parts = []
        # Ensure consistent order. JS Object.keys iterates in insertion order for strings.
        # Python dicts (3.7+) also maintain insertion order. 
        # But to match user's explicit example logic where we construct lists, we should be careful.
        # However, `params` here is a dict. The caller must ensure insertion order if it matters, 
        # or we assume alphabetical if JS behaviour is standard?
        # User provided example: pairs = [("reaction_url", ...)] which implies explicit order.
        # But process_notification passes a DICT.
        # Let's hope standard dict iteration matches insertion/definition order which is standard practice now.
        
        for k, v in params.items():
            if isinstance(v, (list, tuple)):
                v = ",".join(str(x) for x in v)
            else:
                v = str(v)
            parts.append(f"{quote(str(k), safe=SAFE)}={quote(v, safe=SAFE)}")
            
        return "&".join(parts)

    def _get_auth_headers(self, payload: dict) -> dict:
        """Generates authentication headers for requests to Notifier."""
        if not self.config.service_secret:
            return {}
            
        try:
            # Add nonce if not present (required by notifier)
            if "nonce" not in payload:
                payload["nonce"] = int(time.time() * 1000) # Milliseconds integer
                
            # Serialize payload for signature
            msg = self._encode_url_params(payload)
            
            # Debug logging
            # logger.debug(f"Signing payload: {msg}")

            kp = Keypair.from_secret(self.config.service_secret.get_secret_value())
            signature = kp.sign(msg.encode('utf-8')).hex()
            
            token = f"ed25519 {kp.public_key}.{signature}"
            
            return {
                "Authorization": token
            }
        except Exception as e:
            logger.error(f"Failed to generate auth headers: {e}")
            return {}

    def _verify_webhook_signature(self, request: web.Request, body_bytes: bytes) -> bool:
        """Verifies the Notifier's signature on the webhook."""
        if not self.config.notifier_public_key:
            # If no key configured, skip verification (insecure mode or not configured)
            return True
            
        try:
            signature = request.headers.get(NotifierHeaders.SIGNATURE.value)
            timestamp = request.headers.get(NotifierHeaders.TIMESTAMP.value)
            
            if not signature or not timestamp:
                logger.warning("Missing signature headers in webhook")
                return False
                
            # Anti-replay check (e.g. 5 minutes)
            # if abs(time.time() - int(timestamp)) > 300: ... 
            
            msg = f"{timestamp}.".encode('utf-8') + body_bytes
            kp = Keypair.from_public_key(self.config.notifier_public_key)
            
            kp.verify(msg, bytes.fromhex(signature))
            return True
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False

    async def start_server(self):
        """Starts the internal Webhook Listener."""
        app = web.Application()
        app.router.add_post('/webhook', self.handle_webhook)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        
        # Determine host/port. Default 0.0.0.0 to be accessible from Docker network
        port = self.config.webhook_port
        self.site = web.TCPSite(self.runner, '0.0.0.0', port)
        
        logger.info(f"Starting Webhook Listener on port {port}")
        await self.site.start()

    async def stop(self):
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

    async def handle_webhook(self, request: web.Request):
        try:
            # We need raw bytes for verification
            body_bytes = await request.read()
            if not body_bytes:
                 return web.Response(text="Empty payload", status=400)

            # Verify Signature
            if not self._verify_webhook_signature(request, body_bytes):
                return web.Response(text="Invalid Signature", status=403)

            try:
                payload = json.loads(body_bytes)
            except json.JSONDecodeError:
                return web.Response(text="Invalid JSON", status=400)

            logger.info(f"Webhook received payload: {payload}")

            # Process asynchronously to return quickly?
            # For robustness, we await processing.
            await self.process_notification(payload)
            
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return web.Response(text=f"Error: {e}", status=500)

    async def process_notification(self, payload: dict):
        """Process the notification payload."""
        # 1. Identify the Wallet. 
        # The payload format from operations-notifier needs to be handled.
        # Assuming payload contains 'resource_id' (the watched address) or 'account'.
        # And 'data' or top-level keys for operation.
        
        # Check if this is a test notification or real one
        resource_id = payload.get('resource_id') or payload.get('account') or payload.get('to') or payload.get('source_account')
        
        if not resource_id:
             logger.warning(f"No resource_id in payload: {payload}")
             return

        # Deduplicate
        op_id = payload.get('id')
        if op_id and op_id in self.notified_operations:
             logger.info(f"Skipping duplicate operation {op_id}")
             return
        if op_id:
             self.notified_operations.add(op_id)
             # Cleanup logic omitted for brevity (e.g. keep last 1000)
             if len(self.notified_operations) > 1000:
                 self.notified_operations.clear()

        # 2. Convert Payload to TOperations-like object
        op_data = self._map_payload_to_operation(payload)
        if not op_data:
             logger.warning("Could not map payload to operation")
             return

        # 3. Find Users watching this wallet
        # We need to find wallets linked to ANY of the involved accounts (to, from, etc.)
        # Logic in blockchain_monitor: 
        #   or_(TOperations.for_account == account, TOperations.from_account == account, TOperations.code2 == account)
        # Here we have the involved accounts in op_data.
        # But we only get webhook for the *subscribed* address usually.
        # If we subscribe to Alice, we get events for Alice.
        # So we should look for wallets where public_key == key_in_webhook.
        
        # We might have multiple involved accounts.
        involved_accounts = {op_data.for_account, op_data.from_account}
        involved_accounts.discard(None)
        
        if not involved_accounts:
            return

        async with self.db_pool.get_session() as session:
            stmt = select(MyMtlWalletBot).where(
                MyMtlWalletBot.public_key.in_(involved_accounts),
                MyMtlWalletBot.need_delete == 0,
                MyMtlWalletBot.user_id > 0
            )
            result = await session.execute(stmt)
            wallets = result.scalars().all()
            
            for wallet in wallets:
                await self._send_notification_to_user(wallet, op_data)

    def _map_payload_to_operation(self, payload: dict) -> Optional[TOperations]:
        """Maps JSON payload to TOperations entity."""
        try:
            # Flatten "data" if present
            data = payload.get('data', {})
            if data:
                # Merge data into payload, keeping payload keys if collision (or vice versa)
                payload = {**data, **payload}

            op_type = payload.get('type')
            
            # Map common fields
            op = TOperations(
                id=payload.get('id'),
                operation=op_type,
                dt=datetime.utcnow(), # Approximate
                from_account=payload.get('source_account') or payload.get('from'),
                transaction_hash=payload.get('transaction_hash')
            )
            
            # Type specific mapping
            if op_type == 'payment':
                op.for_account = payload.get('to')
                op.amount1 = float(payload.get('amount', 0))
                op.code1 = payload.get('asset_code', 'XLM') # Native if missing usually
                if payload.get('asset_type') == 'native':
                    op.code1 = 'XLM'
            elif op_type == 'create_account':
                op.for_account = payload.get('account')
                op.amount1 = float(payload.get('starting_balance', 0))
                op.code1 = 'XLM'
            elif op_type in ('path_payment_strict_send', 'path_payment_strict_receive'):
                 op.for_account = payload.get('to')
                 op.amount1 = float(payload.get('amount', 0))
                 op.code1 = payload.get('asset_code', 'XLM')
                 # amount2/code2 for source asset? 
                 op.amount2 = float(payload.get('source_amount', 0))
                 op.code2 = payload.get('source_asset_code', 'XLM')
            else:
                 # Generic fallback
                 op.for_account = payload.get('to') or payload.get('account')
                 op.amount1 = 0.0
                 op.code1 = 'UNK'

            return op
            
        except Exception as e:
            logger.error(f"Mapping error: {e}")
            return None

    async def _send_notification_to_user(self, wallet: MyMtlWalletBot, operation: TOperations):
        try:
            # 1. Decode Message
            # decode_db_effect expects: operation, decode_for(public_key), user_id, app_context (optional), localization_service
            message_text = decode_db_effect(operation, str(wallet.public_key), int(wallet.user_id), 
                                            localization_service=self.localization_service)
            
            # If decode returns None or empty? It usually returns string.
            if not message_text:
                return

            # 2. Check Filters
            # This logic mimics handle_address filtering
            async with self.db_pool.get_session() as session:
                stmt_filter = select(NotificationFilter).where(NotificationFilter.user_id == wallet.user_id)
                result_filter = await session.execute(stmt_filter)
                user_filters = result_filter.scalars().all()

            should_send = True
            msg_amount = operation.amount1
            if msg_amount is None:
                try:
                     msg_amount = float(operation.amount1 or 0)
                except:
                     msg_amount = 0.0
            
            for f in user_filters:
                if (f.public_key is None or f.public_key == wallet.public_key) and \
                        (f.asset_code is None or f.asset_code == operation.code1) and \
                        f.min_amount > msg_amount and \
                        f.operation_type == operation.operation:
                    should_send = False
                    break

            if not should_send:
                return

            # 3. Send
            # Reset FSM last_message_id? logic from blockchain_monitor
            fsm_storage_key = StorageKey(bot_id=self.bot.id, user_id=wallet.user_id,
                                         chat_id=wallet.user_id)
            if self.dispatcher:
                 await self.dispatcher.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
            
            await cmd_info_message(None, wallet.user_id, message_text,
                                   operation_id=operation.id,
                                   public_key=str(wallet.public_key),
                                   wallet_id=int(wallet.id) if wallet.id else 0,
                                   bot=self.bot,
                                   dispatcher=self.dispatcher,
                                   localization_service=self.localization_service)
                                   
        except Exception as e:
            logger.error(f"Failed to send notification to {wallet.user_id}: {e}")

    async def subscribe(self, public_key: str):
        """Subscribe a wallet to the notifier."""
        if not self.config.notifier_url:
            return 
            
        url = f"{self.config.notifier_url}/api/subscription"
        webhook = self.config.webhook_public_url
        
        # API requires 'reaction_url' and 'account' (or other filters)
        # Order matters for signature!
        data = {
            "reaction_url": webhook,
            "account": public_key,
            # Add nonce explicitly matches signature
            "nonce": int(time.time() * 1000)
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                # Serialize precisely to ensure signature matches what is sent
                payload_json = json.dumps(data, separators=(',', ':'))
                headers = self._get_auth_headers(data)
                
                headers['Content-Type'] = 'application/json'
                async with session.post(url, data=payload_json, headers=headers) as resp:
                    if resp.status in (200, 201):
                        logger.debug(f"Subscribed {public_key}")
                    else:
                        text = await resp.text()
                        logger.error(f"Failed to subscribe {public_key}: {resp.status} {text}")
            except Exception as e:
                logger.error(f"Exception subscribing {public_key}: {e}")

    async def sync_subscriptions(self):
        """Syncs all DB wallets with Notifier subscriptions."""
        if not self.config.notifier_url:
            logger.warning("Notifier URL not set, skipping sync")
            return

        logger.info("Starting subscription sync...")
        try:
            # 1. Get active subs from Notifier
            # Handle paginated response / list
            notifier_keys = await self._get_active_subscriptions()
            logger.info(f"Notifier has {len(notifier_keys)} subscriptions")

            # 2. Get DB wallets
            async with self.db_pool.get_session() as session:
                stmt = select(MyMtlWalletBot.public_key).where(
                    MyMtlWalletBot.need_delete == 0, 
                    MyMtlWalletBot.user_id > 0
                ).group_by(MyMtlWalletBot.public_key)
                result = await session.execute(stmt)
                db_keys = set(result.scalars().all())
                
            logger.info(f"DB has {len(db_keys)} wallets")

            # 3. Calculate diff
            missing = db_keys - notifier_keys
            
            logger.info(f"Found {len(missing)} missing subscriptions.")
            count = 0
            for key in missing:
                if not key: continue
                await self.subscribe(key)
                count += 1
                if count % 10 == 0:
                    await asyncio.sleep(0.1) # Rate limit
                    
            logger.info("Sync completed.")
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")

    async def _get_active_subscriptions(self) -> set:
        url = f"{self.config.notifier_url}/api/subscription" 
        async with aiohttp.ClientSession() as session:
             try:
                # Prepare params with nonce for signature AND query params
                params = {"nonce": int(time.time() * 1000)}
                headers = self._get_auth_headers(params)
                
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # data might be list of dicts: [{"resource_id": "..."}, ...]
                        if isinstance(data, list):
                            return {item.get('resource_id') for item in data if isinstance(item, dict)}
                        elif isinstance(data, dict):
                             # Maybe wrapped in {"results": [...]}
                             results = data.get('results') or data.get('data')
                             if isinstance(results, list):
                                 return {item.get('resource_id') for item in results}
                        return set()
                    else:
                        logger.error(f"Get subs failed: {resp.status}")
                        return set()
             except Exception as e:
                 logger.error(f"Error fetching subs: {e}")
                 return set()
