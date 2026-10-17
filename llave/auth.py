"""Password hashing + session tokens (stdlib only)."""
import hashlib
import hmac
import os
import secrets

ITERATIONS = 200000


def hash_password(password, iterations=ITERATIONS):
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256$%d$%s$%s' % (iterations, salt.hex(), h.hex())


def verify_password(password, stored):
    try:
        algo, it, salt_hex, hash_hex = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(it))
        return hmac.compare_digest(h.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def new_session_token():
    return secrets.token_urlsafe(32)
