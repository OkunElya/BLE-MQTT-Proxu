import hmac
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import device


async def get_salt(self) -> bytes:
    bluetooth_device = self._parent_link._parent_link
    salt_sertvice = bluetooth_device.services.get("Salt", None)
    if salt_sertvice is None:
        raise ValueError("'Salt' service not found in device")
    salt_char = salt_sertvice.characteristics.get("salt", None)
    if salt_char is None:
        raise ValueError("'salt' characteristic not found in 'Salt' service")
    await salt_char.read()
    return bytes(salt_char.value)


async def sign_postfix(self,msg:bytes):
    key = self._parent_link._parent_link.secret_key
    if key is None:
        raise ValueError("Secret key missing, add 'secretKey' to the device section")
    salt = await get_salt(self)
    hmac_ = hmac.new(key, msg + salt, "sha256").digest()
    return msg + hmac_
