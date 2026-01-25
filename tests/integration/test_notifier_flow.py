
import pytest
import asyncio
import aiohttp
from aiohttp import web
import time
import json
import os
from urllib.parse import quote
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_for_logs
from stellar_sdk import Keypair

# Mark as integration test
pytestmark = pytest.mark.integration

@pytest.fixture(scope="module")
def keys():
    return {
        "notifier": Keypair.random(),
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

@pytest.fixture
async def notifier_service(mock_horizon, horizon_server_config):
    """
    Starts Notifier container connected to Mock Horizon.
    Returns the base URL of the notifier.
    """
    notifier_kp = Keypair.random()
    notifier_secret = notifier_kp.secret

    with Network() as network:
        notifier = NotifierContainer()
        notifier.with_network(network)
        notifier.with_env("ENVIRONMENT", "production")
        notifier.with_env("STORAGE_PROVIDER", "memory")
        notifier.with_env("AUTHORIZATION", "enabled")
        notifier.with_env("SIGNATURE_SECRET", notifier_secret)
        notifier.with_env("API_PORT", "8080")

        # Use Mock Horizon (HTTP) via host.docker.internal
        mock_horizon_url = f"http://host.docker.internal:{horizon_server_config['port']}"
        notifier.with_env("HORIZON", mock_horizon_url)
        notifier.with_env("HORIZON_ALLOW_HTTP", "true")
        
        # Enable host.docker.internal on Linux
        notifier.with_kwargs(extra_hosts={"host.docker.internal": "host-gateway"})

        with notifier:
            wait_for_logs(notifier, "Listening on port 8080", timeout=60)
            notifier_port = notifier.get_exposed_port(8080)
            notifier_base_url = f"http://localhost:{notifier_port}"
            yield notifier_base_url, notifier

@pytest.fixture
async def http_session():
    async with aiohttp.ClientSession() as session:
        yield session

async def subscribe(session, notifier_url, user_kp, target_pubkey, webhook):
    nonce = int(time.time() * 1000)
    pairs = [
        ("account", target_pubkey),
        ("nonce", nonce),
        ("reaction_url", webhook)
    ]

    msg = encode_url_params(pairs)
    sig = user_kp.sign(msg.encode('utf-8')).hex()
    token = f"ed25519 {user_kp.public_key}.{sig}"

    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }

    from collections import OrderedDict
    json_data = json.dumps(OrderedDict(pairs), separators=(',', ':'))

    async with session.post(f"{notifier_url}/api/subscription",
                          data=json_data, headers=headers) as resp:
        assert resp.status == 200, f"Sub failed: {await resp.text()}"

async def get_subs_count(session, notifier_url, user_kp):
    nonce = int(time.time() * 1000)
    pairs = [("nonce", nonce)]
    msg = encode_url_params(pairs)
    sig = user_kp.sign(msg.encode('utf-8')).hex()
    token = f"ed25519 {user_kp.public_key}.{sig}"
    
    url = f"{notifier_url}/api/subscription?nonce={nonce}"
    headers = {"Authorization": token}

    async with session.get(url, headers=headers) as resp:
         assert resp.status == 200
         data = await resp.json()
         return len(data)

@pytest.mark.asyncio
async def test_notifier_subscription_isolation(notifier_service, http_session):
    """
    Test that users only see their own subscriptions.
    """
    notifier_url, _ = notifier_service
    webhook_url = "http://example.com/webhook" # Dummy URL for this test
    
    # --- User 1 Logic ---
    user1_kp = Keypair.random()
    user1_targets = [Keypair.random().public_key for _ in range(3)]
    
    print(f"DEBUG: User 1 ({user1_kp.public_key}) subscribing to 3 targets")
    for target in user1_targets:
        await subscribe(http_session, notifier_url, user1_kp, target, webhook_url)
        
    # --- User 2 Logic ---
    user2_kp = Keypair.random()
    user2_targets = [Keypair.random().public_key for _ in range(4)]
    
    print(f"DEBUG: User 2 ({user2_kp.public_key}) subscribing to 4 targets")
    for target in user2_targets:
        await subscribe(http_session, notifier_url, user2_kp, target, webhook_url)
        
    # --- Verification ---
    count1 = await get_subs_count(http_session, notifier_url, user1_kp)
    print(f"DEBUG: User 1 subs count: {count1}")
    assert count1 == 3, f"User 1 should have 3 subs, got {count1}"
    
    count2 = await get_subs_count(http_session, notifier_url, user2_kp)
    print(f"DEBUG: User 2 subs count: {count2}")
    assert count2 == 4, f"User 2 should have 4 subs, got {count2}"
    
    print("SUCCESS: User isolation verified.")

@pytest.mark.asyncio
async def test_notifier_webhook_delivery(notifier_service, http_session, mock_horizon):
    """
    Test E2E notification delivery: Subscription -> Payment Injection -> Webhook Receive.
    """
    notifier_url, notifier = notifier_service
    # --- Webhook Server Setup ---
    webhook_queue = asyncio.Queue()
    webhook_port = 8081
    
    async def webhook_handler(request):
        data = await request.json()
        print(f"DEBUG: Webhook received: {data}")
        await webhook_queue.put(data)
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', webhook_port)
    await site.start()
    
    try:
        user_kp = Keypair.random()
        target_kp = Keypair.random()
        
        webhook_url = f"http://host.docker.internal:{webhook_port}/webhook"
        
        print(f"DEBUG: User ({user_kp.public_key}) subscribing to target {target_kp.public_key}")
        
        # Subscribe
        await subscribe(http_session, notifier_url, user_kp, target_kp.public_key, webhook_url)
        
        # Verify sub exists
        count = await get_subs_count(http_session, notifier_url, user_kp)
        assert count == 1
        
        print("DEBUG: Subscription confirmed. Injecting payment...")
        
        # Inject Payment
        mock_horizon.add_payment(
            from_account=Keypair.random().public_key,
            to_account=target_kp.public_key,
            amount="10.0",
            asset_type="native"
        )
        
        # Wait for Webhook
        try:
            webhook_data = await asyncio.wait_for(webhook_queue.get(), timeout=15.0)
            # Notifier service sends 'operation' type for operation events
            assert webhook_data['type'] == 'operation'
            # Depending on Notifier implementation, verify content
            
        except asyncio.TimeoutError:
            pytest.fail("Timed out waiting for webhook notification.")

    finally:
        await runner.cleanup()
