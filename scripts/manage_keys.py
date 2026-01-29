
"""
Script to manage Master Key encryption in the database.

Usage Examples:

1. Re-encrypt existing key (Migration):
   ------------------------------------
   Use this when you want to change the password used to encrypt the Master Key in the DB.
   
   $ python scripts/manage_keys.py reencrypt --old "Old" --new "MySuperSecretPassword"

   *After running this, set MASTER_PASSWORD=MySuperSecretPassword in your .env file.*

2. Set new secret manually (Key Rotation):
   ---------------------------------------
   Use this to set a new Stellar Secret Key (Signer) for the bot.
   It will be encrypted using the CURRENT password defined in config (or '0').
   
   $ python scripts/manage_keys.py set_secret --secret "SD7X7..."

   *The bot address (G...) in the DB remains unchanged. This enables Key Rotation.*
"""
import asyncio
import argparse
import sys
import os

# Add project root to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cryptocode  # type: ignore
from sqlalchemy import select
from loguru import logger
from stellar_sdk import Keypair

from db.db_pool import db_pool
from db.models import MyMtlWalletBot
from other.config_reader import config

async def reencrypt(old_pass: str, new_pass: str):
    logger.info("Starting re-encryption process...")
    async with db_pool.get_session() as session:
        wallet = (await session.execute(select(MyMtlWalletBot).where(MyMtlWalletBot.user_id == 0))).scalar_one_or_none()
        
        if not wallet:
            logger.error("Master wallet (user_id=0) not found!")
            return

        if not wallet.secret_key:
            logger.error("Master wallet has no secret key set.")
            return

        logger.info("Decrypting with old password...")
        decrypted_secret = cryptocode.decrypt(wallet.secret_key, old_pass)
        
        if not decrypted_secret:
            logger.error("Failed to decrypt secret! Invalid old password or corrupted data.")
            return
            
        # Validate that what we decrypted is actually a valid Stellar key (sanity check)
        try:
            Keypair.from_secret(str(decrypted_secret))
        except Exception:
            logger.error("Decrypted data is NOT a valid Stellar secret key! Aborting to prevent corruption.")
            return

        logger.info("Encrypting with new password...")
        encrypted_secret = cryptocode.encrypt(str(decrypted_secret), new_pass)
        
        wallet.secret_key = encrypted_secret
        await session.commit()
        logger.success("Successfully re-encrypted master key!")


async def set_secret(secret_key: str):
    # Validate secret key format
    try:
        Keypair.from_secret(secret_key)
    except Exception as e:
        logger.error(f"Invalid Stellar secret key format: {e}")
        return

    logger.info("Setting new master secret...")
    async with db_pool.get_session() as session:
        wallet = (await session.execute(select(MyMtlWalletBot).where(MyMtlWalletBot.user_id == 0))).scalar_one_or_none()
        
        if not wallet:
            logger.error("Master wallet (user_id=0) not found!")
            return

        current_password = config.master_password.get_secret_value()
        logger.info("Encrypting with current configuration password...")
        
        encrypted_secret = cryptocode.encrypt(secret_key, current_password)
        
        wallet.secret_key = encrypted_secret
        await session.commit()
        logger.success("Successfully updated master secret!")

async def main():
    parser = argparse.ArgumentParser(description="Manage Master Key Encryption")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Re-encrypt command
    reencrypt_parser = subparsers.add_parser("reencrypt", help="Re-encrypt master key with new password")
    reencrypt_parser.add_argument("--old", required=True, help="Old password used for encryption")
    reencrypt_parser.add_argument("--new", required=True, help="New password to use for encryption")

    # Set secret command
    set_secret_parser = subparsers.add_parser("set_secret", help="Manually set master secret (encrypted with current config password)")
    set_secret_parser.add_argument("--secret", required=True, help="The Stellar secret key (starts with S)")

    args = parser.parse_args()

    if args.command == "reencrypt":
        await reencrypt(args.old, args.new)
    elif args.command == "set_secret":
        await set_secret(args.secret)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Aborted by user")
