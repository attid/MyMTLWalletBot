import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from other.config_reader import config

async def main():
    # Helper function to modify the URL scheme
    def get_async_url(sync_url: str) -> str:
        # Replace the driver part, e.g., firebird:// -> firebird+firebird_async://
        # Or firebird+fdb:// -> firebird+firebird_async://
        if "firebird://" in sync_url:
            return sync_url.replace("firebird://", "firebird+firebird_async://")
        elif "firebird+fdb://" in sync_url:
            return sync_url.replace("firebird+fdb://", "firebird+firebird_async://")
        # Handle cases where driver is already specified or implicit
        # Assuming standard format driver://user:pass@host/path
        # We need to make sure we use firebird+firebird_async scheme
        
        # Simple breakdown (naive but sufficient for most connection strings)
        parts = sync_url.split("://", 1)
        if len(parts) == 2:
            return f"firebird+firebird_async://{parts[1]}"
        return sync_url
    
    # Original URL might need 'charset=UTF8' if not present, but firebird-driver handles it well.
    # Check if charset is present
    original_url = config.db_url
    
    # Ensure UTF-8 charset if not present (often needed for Firebird)
    if "charset=" not in original_url:
        join_char = "&" if "?" in original_url else "?"
        original_url += f"{join_char}charset=UTF8"

    async_url = get_async_url(original_url)
    
    print(f"Original URL: {config.db_url.split('@')[-1]}") # Hide credentials
    print(f"Async URL:    {async_url.split('@')[-1]}")
    
    try:
        engine = create_async_engine(async_url, echo=False)

        print("\n--- Testing Connection ---")
        async with engine.begin() as conn:
            # Simple query to check version or just connectivity
            # Firebird typically uses rdb$database for singleton selects
            result = await conn.execute(text("SELECT count(*) FROM rdb$database"))
            val = result.scalar()
            print(f"Connection Successful! Query Result: {val}")
            
            # Check version if possible
            try:
                # This might vary depending on FB version, but usually works
                ver_res = await conn.execute(text("SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') FROM rdb$database"))
                version = ver_res.scalar()
                print(f"Firebird Engine Version: {version}")
            except Exception as e:
                print(f"Could not get version (minor issue): {e}")

        await engine.dispose()
        print("\n--- PoC Finished Successfully ---")
        return 0

    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
