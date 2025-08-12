# ton_service.py
import asyncio
import base64
from decimal import Decimal
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs

from tonutils.client import ToncenterV3Client
from tonutils.wallet import WalletV5R1  # можно заменить на WalletV4R2
from tonutils.wallet.messages import TransferJettonMessage
from tonutils.jetton import JettonMasterStablecoin

USDT_MASTER = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"  # официальный мастер USDT
USDT_TEST_MASTER = "kQD0GKBM8ZbryVk2aESmzfU6b9b_8era_IkvBSELujFZPsyy"  # USDTTT (testnet)
USDT_DECIMALS = 6

NANOS = Decimal(10) ** 9
USDT_UNITS = Decimal(10) ** USDT_DECIMALS


class TonService:
    """
    Lightweight service on top of tonutils:
    - create/import a wallet
    - read TON and USDT balances
    - send TON and USDT
    Works via Toncenter V3 (no own node).
    """

    def __init__(self, api_key: Optional[str] = None, is_testnet: bool = False, rps: int = 1):
        self.client = ToncenterV3Client(api_key=api_key, is_testnet=is_testnet, rps=rps, max_retries=3)
        self.wallet: Optional[WalletV5R1] = None
        self.mnemonic: Optional[str] = None
        self.usdt_master = USDT_TEST_MASTER if is_testnet else USDT_MASTER

    # ---------- Wallet
    @staticmethod
    def _to_ton(nano: int) -> Decimal:
        return (Decimal(nano) / NANOS).quantize(Decimal("0.000000001"))

    def create_wallet(self):
        """
        Creates a new mnemonics-based wallet. Returns (service, address, mnemonic).
        """
        wallet, pub, prv, mnemonic = WalletV5R1.create(self.client)
        self.wallet = wallet
        self.mnemonic = " ".join(mnemonic)

    def from_mnemonic(self, mnemonic: str):
        """
        Imports a wallet from a mnemonic.
        """
        wallet, pub, prv, _ = WalletV5R1.from_mnemonic(self.client, mnemonic)
        self.wallet = wallet
        return self

    async def _is_deployed(self) -> bool:
        """ Check if the wallet is deployed on the blockchain. """
        acc = await self.client.get_raw_account(self.wallet.address.to_str())
        return bool(getattr(acc, "code", None))

    # ---------- Balances
    async def get_ton_balance(self) -> Decimal:
        """
        Returns the TON balance in TON units (Decimal).
        """
        acc = await self.client.get_raw_account(self.wallet.address.to_str())
        # acc.balance — int in nanoTON (via V3 indexer)
        return self._to_ton(acc.balance)

    async def get_usdt_balance(self) -> Decimal:
        """
        Returns the USDT balance (Decimal) with 6 decimals.
        """
        #if not await self._is_deployed():
        #    return Decimal(0)

        owner_addr = self.wallet.address.to_str()
        # jetton-wallet address for this owner (USDT = stable jetton)
        try:
            jw_addr = await JettonMasterStablecoin.get_wallet_address(
                self.client, owner_addr, self.usdt_master
            )
            # standard get-method of a jetton wallet
            # get_wallet_data() -> (balance, owner, jetton, jetton_wallet_code)
            raw = await self.client.run_get_method(
                address=jw_addr.to_str(),
                method_name="get_wallet_data",
                stack=[]
            )
            if len(raw) == 1:
                return Decimal(0)
            balance_units = self._extract_int_from_stack(raw)
            return (Decimal(balance_units) / USDT_UNITS).quantize(Decimal("0.000001"))
        except Exception:
            return Decimal(0)

    @staticmethod
    def _extract_int_from_stack(result) -> int:
        """
        Universal parser for different run_get_method response formats for the first stack element (int).
        Supports formats of some RPC/indexers: list/int, dict{'result':{'stack':...}}, etc.
        """
        # 1) tonutils docs promise a list of values
        if isinstance(result, list):
            v = result[0]
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.startswith("0x"):
                return int(v, 16)
        # 2) toncenter/drpc/chainstack styles
        try:
            stack = result["result"]["stack"]
            first = stack[0]
            if isinstance(first, list) and len(first) >= 2 and isinstance(first[1], str):
                return int(first[1], 16)
            if isinstance(first, dict) and "value" in first:
                val = first["value"]
                return int(val, 16) if isinstance(val, str) and val.startswith("0x") else int(val)
        except Exception:
            pass
        raise RuntimeError(f"Failed to parse run_get_method stack: {result!r}")

    # ---------- Transfers

    async def ensure_deployed(self) -> None:
        if await self._is_deployed():
            return

        await self.wallet.deploy()

        for _ in range(30):
            await asyncio.sleep(1.0)
            if await self._is_deployed():
                return

        raise TimeoutError("Wallet was not deployed in time")

    async def send_ton(self, to_address: str, amount_ton: Decimal, comment: str = "") -> str:
        """
        Sends TON. amount_ton — Decimal in TON.
        Returns tx_hash (string).
        """
        await self.ensure_deployed()

        tx_hash = await self.wallet.transfer(
            destination=to_address,
            amount=float(amount_ton),  # the library accepts float for convenience
            body=comment or None,
        )
        return tx_hash

    async def send_usdt(self, to_address: str, amount_usdt: Decimal, comment: str = "") -> str:
        """
        Sends USDT as a jetton.
        amount_usdt — Decimal in human-readable form (e.g., Decimal('12.34')).
        Returns tx_hash (string).
        """
        await self.ensure_deployed()
        tx_hash = await self.wallet.transfer_message(
            message=TransferJettonMessage(
                destination=to_address,
                jetton_master_address=self.usdt_master,
                jetton_amount=float(amount_usdt),
                jetton_decimals=USDT_DECIMALS,
                forward_payload=comment or None,  # will form a TextComment payload
            ),
        )
        return tx_hash

    async def execute_ton_deeplink(self, link: str) -> str:
        u = urlparse(link.replace("ton://", "https://app.tonkeeper.com/"))
        to_addr = u.path.split("/")[-1]
        qs = parse_qs(u.query)
        amount_nano = int(qs["amount"][0])  # из ссылки — в нанотонах
        body_b64url = qs.get("bin", [None])[0]  # может отсутствовать

        from pytoniq_core import Cell  # ignore
        body = None
        if body_b64url:
            boc = base64.urlsafe_b64decode(body_b64url + "=" * (-len(body_b64url) % 4))
            body = Cell.one_from_boc(boc)  # payload из BOC

        tx = await self.wallet.transfer(
            destination=to_addr,
            amount=amount_nano / 1e9,  # в TON
            body=body  # можно и строку-комментарий, и Cell
        )
        return tx


# ---- пример запуска
async def _demo():
    api_key = ""

    test1_mnemonic = ""

    # EQAPuV7aIdtq8A6gVnlDuupO7wFBH3FMd7wh86eOyRny1uHC

    service = TonService(is_testnet=True)
    service.create_wallet()
    # print("address:", service.wallet.address, "\nmnemonic:", service.mnemonic)

    # или импортируй существующий
    service.from_mnemonic(mnemonic=test1_mnemonic)

    print("address:", service.wallet.address.to_str())
    print("address:", service.wallet.public_key)

    # tx = await service.execute_ton_deeplink('ton://transfer/kQDNUDJC0iQvJoZp0ml-YteL1NtTXKphU03CTI5v4VtBhGYs?amount=139000000&bin=te6cckEBAQEAFgAAKClXdJkAAAAAAAAAAAAAAAAF9eEAGftUVg')

    # print("tx:", tx)

    ton = await service.get_ton_balance()
    usdt = await service.get_usdt_balance()
    print("TON balance:", ton)
    print("USDT balance:", usdt)

    # перевод TON
    # tx1 = await service.send_ton("kQDNUDJC0iQvJoZp0ml-YteL1NtTXKphU03CTI5v4VtBhGYs", Decimal("0.139"), )
    # print("TON tx:", tx1)

    # перевод USDT
    # tx2 = await service.send_usdt("kQDNUDJC0iQvJoZp0ml-YteL1NtTXKphU03CTI5v4VtBhGYs", Decimal("1.50"), "order-42")
    # print("USDT tx:", tx2)


if __name__ == "__main__":
    asyncio.run(_demo())
# for test net info https://github.com/ton-community/tma-usdt-payments-demo
