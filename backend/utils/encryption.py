"""
Encryption utilities for sensitive data.
"""
import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def generate_encryption_key(password: str, salt: bytes = None) -> bytes:
    """
    Generate an encryption key from a password.

    Args:
        password: Password string to derive key from
        salt: Salt bytes (if None, generates a new one)

    Returns:
        Tuple of (key, salt) where key is base64-encoded bytes suitable for Fernet
    """
    if salt is None:
        salt = os.urandom(16)  # 128-bit salt

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
    return key


def encrypt_data(data: str, key: bytes) -> str:
    """
    Encrypt string data using Fernet symmetric encryption.

    Args:
        data: String data to encrypt
        key: Encryption key (base64-encoded bytes)

    Returns:
        Encrypted string
    """
    f = Fernet(key)
    encrypted_data = f.encrypt(data.encode('utf-8'))
    return encrypted_data.decode('utf-8')


def decrypt_data(encrypted_data: str, key: bytes) -> str:
    """
    Decrypt string data using Fernet symmetric encryption.

    Args:
        encrypted_data: Encrypted string data
        key: Encryption key (base64-encoded bytes)

    Returns:
        Decrypted string
    """
    f = Fernet(key)
    decrypted_data = f.decrypt(encrypted_data.encode('utf-8'))
    return decrypted_data.decode('utf-8')


# Simple wrapper for backward compatibility
class SimpleEncryptor:
    def __init__(self, key_string: str):
        # Derive key from string (in production, use proper key management)
        self.key = self._derive_key(key_string)

    def _derive_key(self, key_string: str) -> bytes:
        """Derive encryption key from string."""
        # Use a fixed salt for simplicity - in production use random salt stored separately
        salt = b'promptql_fixed_salt_for_demo'
        return generate_encryption_key(key_string, salt)

    def encrypt(self, data: str) -> str:
        return encrypt_data(data, self.key)

    def decrypt(self, encrypted_data: str) -> str:
        return decrypt_data(encrypted_data, self.key)