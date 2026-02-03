import hmac

def get_salt() -> bytes:
    salt = ...
    return bytes(salt)

def sign_postfix(msg):
    loc_locals()
    salt = get_salt()
    hmac_ = hmac.new(key, msg+salt, 'sha256').digest()
    return msg + hmac_
