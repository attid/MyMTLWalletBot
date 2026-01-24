
import pytest
import asyncio
import aiohttp
import time
import json
import os
from urllib.parse import quote
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_for_logs
from stellar_sdk import Keypair
from infrastructure.services.notification_service import NotificationService, NotifierHeaders
from other.config_reader import Settings

# Mark as integration test
pytestmark = pytest.mark.integration

@pytest.fixture(scope="module")
def keys():
    return {
        "notifier": Keypair.random(),
        "bot": Keypair.random(),
        "neighbor": Keypair.random()
    }

class NotifierContainer(DockerContainer):
    def __init__(self, image="ghcr.io/montelibero/stellar_notifier:latest", **kwargs):
        super().__init__(image, **kwargs)
        self.with_exposed_ports(8080)

def encode_url_params(pairs):
    """
    Encodes parameters to match stellar_notifier logic (key=val&key=val).
    pairs: list of (key, value) tuples to preserve order.
    """
    SAFE = "-_.!~*'()"
    parts = []
    for k, v in pairs:
        if isinstance(v, (list, tuple)):
            v = ",".join(str(x) for x in v)
        else:
            v = str(v)
        parts.append(f"{quote(str(k), safe=SAFE)}={quote(v, safe=SAFE)}")
    return "&".join(parts)

@pytest.mark.asyncio
async def test_notifier_initial_connection(mock_horizon, horizon_server_config, mock_app_context, keys):
    """
    Step 1: Verify Connectivity & Subscription Isolation
    
    1. Start Notifier Container (Real Image) connected to PUBLIC HORIZON (Testnet).
       - This avoids the "insecure HTTP" error.
       - Use Mongo:6 for storage.
    2. "Neighbor" creates a subscription.
    3. "Bot" creates a separate subscription.
    4. Verify both return 200 OK.
    5. Verify Bot's `_get_active_subscriptions` return ONLY Bot's wallet.
    """
    
    notifier_signing_key = keys["notifier"]
    notifier_secret_seed = notifier_signing_key.secret
    
    with Network() as network:
        # 1. Start MongoDB
        mongo = DockerContainer("mongo:6")
        mongo.with_network(network)
        mongo.with_network_aliases("mongodb")
        mongo.with_env("MONGO_INITDB_DATABASE", "notifier")
        
        with mongo:
            wait_for_logs(mongo, "Waiting for connections")

            # 2. Start Stellar Notifier with PUBLIC HORIZON
            notifier = NotifierContainer()
            notifier.with_network(network)
            notifier.with_env("ENVIRONMENT", "production") 
            notifier.with_env("STORAGE_PROVIDER", "mongodb")
            notifier.with_env("STORAGE_CONNECTION_STRING", "mongodb://mongodb:27017/notifier")
            notifier.with_env("AUTHORIZATION", "enabled")
            notifier.with_env("SIGNATURE_SECRET", notifier_secret_seed)
            notifier.with_env("API_PORT", "8080")
            
            # USE PUBLIC TESTNET HORIZON (HTTPS) TO AVOID INSECURE ERROR
            notifier.with_env("HORIZON", "https://horizon-testnet.stellar.org")
            
            with notifier:
                try:
                    # Wait for startup
                    wait_for_logs(notifier, "Listening on port 8080", timeout=60)
                except Exception as e:
                    print(f"DEBUG: Container Startup Failed. Logs:\n{notifier.get_logs()}")
                    raise e
                
                notifier_port = notifier.get_exposed_port(8080)
                notifier_url = f"http://localhost:{notifier_port}"
                
                # 3. Configure Bot Service
                from tests.conftest import get_free_port
                webhook_port = get_free_port()
                config = Settings()
                config.notifier_url = notifier_url
                config.webhook_public_url = f"http://host.docker.internal:{webhook_port}/webhook"
                config.webhook_port = webhook_port
                config.notifier_public_key = keys["notifier"].public_key
                config.service_secret = settings_secret(keys["bot"].secret)

                # Mock DB Context
                from unittest.mock import AsyncMock, MagicMock
                session_mock = AsyncMock()
                mock_app_context.db_pool.get_session.return_value.__aenter__.return_value = session_mock
                mock_app_context.db_pool.get_session.return_value.__aexit__ = AsyncMock(return_value=None)
                
                service = NotificationService(config, mock_app_context.db_pool, mock_app_context.bot, 
                                            mock_app_context.localization_service, mock_app_context.dispatcher)
                
                try:
                    try:
                        # 4. Neighbor Subscription
                        # Manually construct signed request matching new logic
                        async with aiohttp.ClientSession() as session:
                            neighbor_kp = keys["neighbor"]
                            neighbor_target = Keypair.random().public_key
                            
                            # Define FIELDS AS LIST OF TUPLES
                            neighbor_nonce = int(time.time() * 1000)
                            pairs = [
                                ("reaction_url", f"http://neighbor-svc:{webhook_port}/webhook"),
                                ("account", neighbor_target),
                                ("nonce", neighbor_nonce),
                            ]
                            
                            # Sign encoded string
                            msg = encode_url_params(pairs)
                            sig = neighbor_kp.sign(msg.encode('utf-8')).hex()
                            token = f"ed25519 {neighbor_kp.public_key}.{sig}"
                            
                            headers = {
                                "Authorization": token,
                                'Content-Type': 'application/json'
                            }
                            
                            from collections import OrderedDict
                            json_data = json.dumps(OrderedDict(pairs), separators=(',', ':'))
                            
                            async with session.post(f"{notifier_url}/api/subscription", 
                                                    data=json_data, headers=headers) as resp:
                                assert resp.status == 200, f"Neighbor sub failed: {await resp.text()}"

                            # 5. Bot Subscription
                            bot_wallet = Keypair.random().public_key
                            # Service.subscribe now handles usage of new auth headers internally
                            await service.subscribe(bot_wallet)
                            
                            # 6. Verify Isolation
                            # Bot should only see its own subscription
                            subs = await service._get_active_subscriptions()
                            print(f"DEBUG: Retrieved Subs: {subs}")
                            
                            assert bot_wallet in subs
                            assert len(subs) == 1
                            
                            print("Step 1 SUCCESS: Notifier Connected, Subscriptions created & Isolated.")

                    except Exception as e:
                        try:
                            logs = notifier.get_logs()
                            if isinstance(logs, tuple):
                                stdout, stderr = logs
                                log_str = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
                            else:
                                log_str = str(logs)
                        except:
                            log_str = "Could not retrieve logs"
                            
                        with open("tests/integration/container_logs.txt", "w") as f:
                            f.write(log_str)
                            f.write(f"\n\nException: {e}")
                        raise e
                finally:
                    await service.stop()

def settings_secret(s):
    from pydantic import SecretStr
    return SecretStr(s)
