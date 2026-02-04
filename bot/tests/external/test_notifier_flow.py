import pytest
import asyncio
import aiohttp
from aiohttp import web
import time
import json
from urllib.parse import quote
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_for_logs
from stellar_sdk import Keypair
from unittest.mock import MagicMock
from infrastructure.services.notification_service import NotificationService

# Mark as external test (requires Docker and external services)
pytestmark = pytest.mark.external


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
    # Testing Token Auth - multiple tokens for isolation testing
    test_token_user1 = "secret-test-token-user1"
    test_token_user2 = "secret-test-token-user2"

    # Use Mock Horizon (HTTP) via host.docker.internal for container access
    mock_horizon_url = f"http://host.docker.internal:{horizon_server_config['port']}"

    with Network() as network:
        notifier = NotifierContainer("ghcr.io/montelibero/stellar_notifier:latest")
        notifier.with_network(network)
        notifier.with_env("HORIZON", mock_horizon_url)
        notifier.with_env("HORIZON_ALLOW_HTTP", "true")
        notifier.with_env("API_PORT", "8080")
        notifier.with_env("AUTHORIZATION", "token")
        # Multiple tokens separated by comma
        notifier.with_env("USER_TOKENS", f"{test_token_user1},{test_token_user2}")

        # Enable host.docker.internal on Linux
        notifier.with_kwargs(extra_hosts={"host.docker.internal": "host-gateway"})

        with notifier:
            wait_for_logs(notifier, "Listening on port 8080", timeout=60)
            notifier_port = notifier.get_exposed_port(8080)
            notifier_base_url = f"http://localhost:{notifier_port}"
            # Yield both tokens and notifier object
            yield notifier_base_url, (test_token_user1, test_token_user2), notifier


@pytest.fixture
async def http_session():
    async with aiohttp.ClientSession() as session:
        yield session


async def subscribe(session, notifier_url, user_kp, target_pubkey, webhook, token):
    nonce = int(time.time() * 1000)

    pairs = [("account", target_pubkey), ("nonce", nonce), ("reaction_url", webhook)]

    from collections import OrderedDict

    json_data = json.dumps(OrderedDict(pairs), separators=(",", ":"))

    headers = {"Authorization": token, "Content-Type": "application/json"}

    async with session.post(
        f"{notifier_url}/api/subscription", data=json_data, headers=headers
    ) as resp:
        assert resp.status == 200, f"Sub failed: {await resp.text()}"
        return nonce


async def get_subs_count(session, notifier_url, user_kp, token):
    nonce = int(time.time() * 1000)

    url = f"{notifier_url}/api/subscription?nonce={nonce}"
    headers = {"Authorization": token}

    async with session.get(url, headers=headers) as resp:
        assert resp.status == 200
        data = await resp.json()
        return len(data)


async def get_remote_nonce(session, notifier_url, user_kp, token):
    """
    Retrieves the current nonce from the Notifier using the new endpoint.
    GET /api/nonce
    Uses Token Auth
    """
    headers = {"Authorization": token}

    async with session.get(f"{notifier_url}/api/nonce", headers=headers) as resp:
        assert resp.status == 200, f"Get nonce failed: {await resp.text()}"
        data = await resp.json()
        return int(data["nonce"])


@pytest.mark.asyncio
async def test_notifier_subscription_isolation(notifier_service, http_session):
    """
    Test that users only see their own subscriptions.
    Uses different tokens for each user to ensure isolation.
    """

    notifier_url, tokens, _ = notifier_service
    test_token_user1, test_token_user2 = tokens
    webhook_url = "http://example.com/webhook"  # Dummy URL for this test

    # --- User 1 Logic ---
    user1_kp = Keypair.random()
    user1_targets = [Keypair.random().public_key for _ in range(3)]

    print(f"DEBUG: User 1 ({user1_kp.public_key}) subscribing to 3 targets with token1")
    for target in user1_targets:
        await subscribe(
            http_session, notifier_url, user1_kp, target, webhook_url, test_token_user1
        )

    # --- User 2 Logic ---
    user2_kp = Keypair.random()
    user2_targets = [Keypair.random().public_key for _ in range(4)]

    print(f"DEBUG: User 2 ({user2_kp.public_key}) subscribing to 4 targets with token2")
    for target in user2_targets:
        await subscribe(
            http_session, notifier_url, user2_kp, target, webhook_url, test_token_user2
        )

    # --- Verification ---
    count1 = await get_subs_count(
        http_session, notifier_url, user1_kp, test_token_user1
    )
    print(f"DEBUG: User 1 subs count: {count1}")
    assert count1 == 3, f"User 1 should have 3 subs, got {count1}"

    count2 = await get_subs_count(
        http_session, notifier_url, user2_kp, test_token_user2
    )
    print(f"DEBUG: User 2 subs count: {count2}")
    assert count2 == 4, f"User 2 should have 4 subs, got {count2}"

    print("SUCCESS: User isolation verified.")


@pytest.mark.asyncio
async def test_notifier_webhook_delivery(notifier_service, http_session, mock_horizon):
    """
    Test E2E notification delivery: Subscription -> Payment Injection -> Webhook Receive.
    """

    notifier_url, tokens, notifier_container = notifier_service
    test_token = tokens[0]  # Use first token for this test
    # --- Webhook Server Setup ---
    webhook_queue = asyncio.Queue()
    webhook_port = 8081

    async def webhook_handler(request):
        data = await request.json()
        print(f"DEBUG: Webhook received: {data}")
        await webhook_queue.put(data)
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", webhook_port)
    await site.start()

    try:
        user_kp = Keypair.random()
        target_kp = Keypair.random()

        webhook_url = f"http://host.docker.internal:{webhook_port}/webhook"

        print(
            f"DEBUG: User ({user_kp.public_key}) subscribing to target {target_kp.public_key}"
        )

        # Subscribe
        await subscribe(
            http_session,
            notifier_url,
            user_kp,
            target_kp.public_key,
            webhook_url,
            test_token,
        )

        # Verify sub exists
        count = await get_subs_count(http_session, notifier_url, user_kp, test_token)
        assert count == 1

        print("DEBUG: Subscription confirmed. Injecting payment...")

        # Inject Payment
        mock_horizon.add_payment(
            from_account=Keypair.random().public_key,
            to_account=target_kp.public_key,
            amount="10.0",
            asset_type="native",
        )

        # Wait for Webhook
        try:
            webhook_data = await asyncio.wait_for(webhook_queue.get(), timeout=15.0)
            # Notifier service sends 'operation' type for operation events
            assert webhook_data["type"] == "operation"
            # Depending on Notifier implementation, verify content

        except asyncio.TimeoutError:
            print("\n!!! TIMEOUT - DUMPING NOTIFIER LOGS !!!")
            print(notifier_container.get_logs())
            pytest.fail("Timed out waiting for webhook notification.")

    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_nonce_lookup(notifier_service, http_session):
    """
    Test the new GET /api/nonce endpoint.
    With Token Auth, Notifier returns nonce=0 as it doesn't track nonces per token.
    This test verifies that the endpoint works correctly in token auth mode.
    """

    notifier_url, tokens, _ = notifier_service
    test_token = tokens[0]  # Use first token for this test
    user_kp = Keypair.random()
    target = Keypair.random().public_key
    webhook = "http://example.com/webhook"

    print(f"DEBUG: Testing Nonce Lookup for user {user_kp.public_key}")

    # 1. First Subscription
    nonce1 = await subscribe(
        http_session, notifier_url, user_kp, target, webhook, test_token
    )
    print(f"DEBUG: Subscribed with nonce {nonce1}")

    # 2. Verify Nonce Lookup - Token Auth returns 0
    remote_nonce1 = await get_remote_nonce(
        http_session, notifier_url, user_kp, test_token
    )
    print(f"DEBUG: Remote nonce after 1st sub: {remote_nonce1}")

    # Token auth doesn't track nonces, so remote nonce is always 0
    assert remote_nonce1 == 0, f"Token auth should return nonce=0, got {remote_nonce1}"

    # 3. Second Subscription (should have higher nonce locally)
    # Ensure time moves forward slightly to guarantee higher nonce if script runs ultra fast
    time.sleep(0.01)
    nonce2 = await subscribe(
        http_session, notifier_url, user_kp, target, webhook, test_token
    )
    print(f"DEBUG: Subscribed again with nonce {nonce2}")

    assert nonce2 > nonce1, "Local nonces should be sequential"

    # 4. Verify Nonce Lookup Again - still returns 0
    remote_nonce2 = await get_remote_nonce(
        http_session, notifier_url, user_kp, test_token
    )
    print(f"DEBUG: Remote nonce after 2nd sub: {remote_nonce2}")

    assert remote_nonce2 == 0, f"Token auth should return nonce=0, got {remote_nonce2}"

    print("SUCCESS: Nonce lookup verified (Token Auth - nonce=0 is expected).")


@pytest.mark.asyncio
async def test_nonce_concurrency(notifier_service):
    """
    Test concurrency safety for nonce generation.
    1. Initialize NotificationService with mock config pointing to real Notifier.
    2. Launch 6 concurrent tasks to fetch nonces using internal _get_next_nonce.
    3. Verify all nonces are unique and sequential (locally).
    """

    notifier_url, tokens, _ = notifier_service
    test_token = tokens[0]  # Use first token for this test

    # Mock Config
    mock_config = MagicMock()
    mock_config.notifier_url = notifier_url
    mock_config.notifier_auth_token = test_token  # Use token
    mock_config.service_secret = None
    mock_config.notifier_public_key = None
    mock_config.test_mode = False
    mock_config.webhook_port = 8080  # Dummy

    # Instantiate Service (db_pool and others as None since we test nonce only)
    service = NotificationService(mock_config, None, None, None)

    # We cheat a bit: verify startup fetches initial nonce
    await service._fetch_initial_nonce()
    initial_nonce = service._nonce
    print(f"DEBUG: Initial Nonce: {initial_nonce}")

    async def get_nonce_worker():
        return await service._get_next_nonce()

    # Launch 6 concurrent tasks
    tasks = [get_nonce_worker() for _ in range(6)]
    results = await asyncio.gather(*tasks)

    print(f"DEBUG: Concurrent Nonces: {results}")

    # Verify uniqueness
    assert len(results) == 6
    assert len(set(results)) == 6

    # Verify strict sequential order relative to initial
    sorted_results = sorted(results)
    assert sorted_results[0] == initial_nonce + 1
    assert sorted_results[-1] == initial_nonce + 6
    for i in range(len(sorted_results) - 1):
        assert sorted_results[i + 1] == sorted_results[i] + 1

    print("SUCCESS: Nonce concurrency verified.")
