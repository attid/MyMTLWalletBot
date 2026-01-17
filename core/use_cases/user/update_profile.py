from typing import Optional
from core.domain.entities import User
from core.interfaces.repositories import IUserRepository

class UpdateUserProfile:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def execute(self, user_id: int, username: Optional[str] = None, 
                      language: Optional[str] = None, default_address: Optional[str] = None,
                      can_5000: Optional[int] = None) -> User:
        """
        Update user profile information.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        is_changed = False
        if username is not None and user.username != username:
            user.username = username
            is_changed = True
        
        if language is not None and user.language != language:
            user.language = language
            is_changed = True
            
        if default_address is not None and user.default_address != default_address:
            user.default_address = default_address
            is_changed = True
            
        if can_5000 is not None and user.can_5000 != can_5000:
            user.can_5000 = can_5000
            is_changed = True
            
        if is_changed:
            user = await self.user_repo.update(user)
            
        return user
