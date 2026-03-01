"""Backfill wallet_crypto_v2 from legacy wallet fields.

Version A migration strategy:
- keep legacy fields untouched (rollback-safe)
- fill wallet_crypto_v2 where migration is possible
- skip wallets that require user PIN/password (use_pin in 1,2)

Usage examples:
  python scripts/migrate_wallet_crypto_v2.py --dry-run
  python scripts/migrate_wallet_crypto_v2.py --batch-size 200
  python scripts/migrate_wallet_crypto_v2.py --user-id 123456
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

# Add bot package root for direct script execution.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.db_pool import db_pool
from db.models import MyMtlWalletBot
from infrastructure.services.encryption_service import EncryptionService


@dataclass
class Counters:
    scanned: int = 0
    migrated: int = 0
    skipped_has_v2: int = 0
    skipped_missing_secret: int = 0
    skipped_requires_user_pin: int = 0
    skipped_decrypt_failed: int = 0
    failed: int = 0


def _wallet_kind(is_free: bool, is_ton: bool) -> str:
    if is_ton:
        return "ton_free"
    return "stellar_free" if is_free else "stellar_user"


def _mode(use_pin: int) -> str:
    # In current product model, no-password flow is treated as free/server mode.
    return "free" if use_pin == 0 else "user"


async def migrate_wallets(
    *,
    dry_run: bool,
    batch_size: int,
    user_id: int | None,
) -> Counters:
    counters = Counters()
    encryption = EncryptionService()

    async with db_pool.get_session() as session:
        stmt = select(MyMtlWalletBot).where(MyMtlWalletBot.need_delete == 0)
        if user_id is not None:
            stmt = stmt.where(MyMtlWalletBot.user_id == user_id)

        result = await session.execute(stmt)
        wallets = result.scalars().all()

        for wallet in wallets:
            counters.scanned += 1

            if wallet.wallet_crypto_v2:
                counters.skipped_has_v2 += 1
                continue

            if not wallet.secret_key:
                counters.skipped_missing_secret += 1
                continue

            try:
                is_ton = wallet.secret_key == "TON"
                kind = _wallet_kind(is_free=bool(wallet.free_wallet), is_ton=is_ton)
                mode = _mode(int(wallet.use_pin or 0))

                secret_plain: str | None = None
                seed_plain: str | None = None

                if is_ton:
                    secret_plain = "TON"
                    seed_plain = wallet.seed_key
                elif mode == "free":
                    secret_plain = encryption.decrypt(
                        wallet.secret_key,
                        str(wallet.user_id),
                    )
                    if secret_plain and wallet.seed_key:
                        seed_plain = encryption.decrypt(wallet.seed_key, secret_plain)
                else:
                    counters.skipped_requires_user_pin += 1
                    continue

                if not secret_plain:
                    counters.skipped_decrypt_failed += 1
                    continue

                wallet.wallet_crypto_v2 = encryption.encrypt_wallet_container(
                    secret_key=secret_plain,
                    seed_key=seed_plain,
                    mode=mode,
                    wallet_kind=kind,
                    pin=None,
                )
                counters.migrated += 1

                if not dry_run and counters.migrated % batch_size == 0:
                    await session.commit()
                    logger.info(
                        "Committed batch: migrated={} scanned={}",
                        counters.migrated,
                        counters.scanned,
                    )

            except Exception as exc:  # pragma: no cover - defensive reporting path
                counters.failed += 1
                logger.exception(
                    "Failed to migrate wallet id={} user_id={} error={}",
                    wallet.id,
                    wallet.user_id,
                    exc,
                )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return counters


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy wallet secrets to v2")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not persist updates; only print migration counters",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Commit frequency for non-dry-run mode",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Migrate only a specific user_id",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    counters = await migrate_wallets(
        dry_run=args.dry_run,
        batch_size=max(args.batch_size, 1),
        user_id=args.user_id,
    )
    logger.info(
        (
            "Migration result: scanned={} migrated={} skipped_has_v2={} "
            "skipped_missing_secret={} skipped_requires_user_pin={} "
            "skipped_decrypt_failed={} failed={} dry_run={}"
        ),
        counters.scanned,
        counters.migrated,
        counters.skipped_has_v2,
        counters.skipped_missing_secret,
        counters.skipped_requires_user_pin,
        counters.skipped_decrypt_failed,
        counters.failed,
        args.dry_run,
    )
    return 0 if counters.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
