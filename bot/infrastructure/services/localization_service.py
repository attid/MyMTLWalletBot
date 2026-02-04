import json
import os
from typing import Dict, Union, Tuple
from sqlalchemy.future import select
from db.models import MyMtlWalletBotUsers

class LocalizationService:
    """
    Service for managing translations and user language preferences.
    Replaces global_data.lang_dict and global_data.user_lang_dic.
    """
    def __init__(self, db_pool):
        # db_pool is expected to be DatabasePool or object with get_session async context manager
        self.lang_dict: Dict[str, Dict] = {}
        self.user_lang_cache: Dict[int, str] = {}
        self.db_pool = db_pool

    async def load_languages(self, lang_dir: str):
        """Load all language JSON files from directory"""
        if not os.path.exists(lang_dir):
            return

        for file in os.listdir(lang_dir):
            if file.endswith(".json"):
                try:
                    with open(os.path.join(lang_dir, file), "r", encoding="utf-8") as fp:
                        self.lang_dict[file.split('.')[0]] = json.load(fp)
                except Exception as e:
                    print(f"Error loading language file {file}: {e}")

    async def get_user_language_async(self, user_id: int) -> str:
        """Get user's language (cached or from DB asynchronously)"""
        if user_id in self.user_lang_cache:
            return self.user_lang_cache[user_id]
        
        # If not in cache, try to fetch from DB
        async with self.db_pool.get_session() as session:
            try:
                stmt = select(MyMtlWalletBotUsers.lang).where(MyMtlWalletBotUsers.user_id == user_id)
                result = await session.execute(stmt)
                lang = result.scalar_one_or_none()
                lang = lang if lang else 'en'
            except Exception:
                lang = 'en'
        
        self.user_lang_cache[user_id] = lang
        return lang

    def get_user_language(self, user_id: int) -> str:
        """Get user's language from CACHE ONLY. Fallback to 'en'."""
        return self.user_lang_cache.get(user_id, 'en')

    def set_user_language(self, user_id: int, lang: str):
        """Update user's language in cache."""
        self.user_lang_cache[user_id] = lang

    def get_text(self, user_id: Union[int, str], key: str, params: Tuple = ()) -> str:
        """Get localized text for user (synchronous, cache-based)"""
        if isinstance(user_id, str):
            lang = user_id
        else:
            # Ensure user_id is integer
            try:
                user_id = int(str(user_id))
                lang = self.get_user_language(user_id)
            except ValueError:
                lang = 'en'

        # Fallback to English if key not found in user's language, then key itself
        user_lang_dict = self.lang_dict.get(lang, {})
        en_lang_dict = self.lang_dict.get('en', {})
        
        text = user_lang_dict.get(key)
        if text is None:
            text = en_lang_dict.get(key)
            if text is None:
                # Log warning if key missing entirely
                from loguru import logger
                logger.warning(f"Localization key missing: '{key}' for lang '{lang}' (user_id={user_id})")
                text = f'{key} 0_0'
        
        # Simple format replacement
        for par in params:
            text = text.replace('{}', str(par), 1)
            
        return text
