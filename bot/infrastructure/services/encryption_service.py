from typing import Optional
import cryptocode  # type: ignore
from core.interfaces.services import IEncryptionService

class EncryptionService(IEncryptionService):
    def encrypt(self, data: str, key: str) -> str:
        return cryptocode.encrypt(data, key)

    def decrypt(self, encrypted_data: str, key: str) -> Optional[str]:
        result = cryptocode.decrypt(encrypted_data, key)
        if result is False: # cryptocode returns False on failure
            return None
        return str(result)
