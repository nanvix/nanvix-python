"""Nanvix cryptography.fernet stub."""

import base64
import hashlib
import hmac
import os
import struct
import time


class InvalidToken(Exception):
    pass


class Fernet:
    """Minimal Fernet implementation using stdlib."""

    def __init__(self, key):
        if isinstance(key, str):
            key = key.encode()
        self._key = base64.urlsafe_b64decode(key)
        if len(self._key) != 32:
            raise ValueError("Fernet key must decode to 32 bytes")
        self._signing_key = self._key[:16]
        self._encryption_key = self._key[16:]

    @classmethod
    def generate_key(cls):
        return base64.urlsafe_b64encode(os.urandom(32))

    def encrypt(self, data):
        if isinstance(data, str):
            data = data.encode()
        # Simplified: just base64 encode with HMAC
        current_time = struct.pack(">Q", int(time.time()))
        iv = os.urandom(16)
        payload = current_time + iv + data
        h = hmac.new(self._signing_key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(b"\x80" + payload + h)

    def decrypt(self, token, ttl=None):
        try:
            data = base64.urlsafe_b64decode(token)
        except Exception:
            raise InvalidToken("Invalid base64")
        if not data or data[0:1] != b"\x80":
            raise InvalidToken("Invalid version")
        # Extract payload (simplified)
        payload = data[1:-32]
        if len(payload) < 24:
            raise InvalidToken("Token too short")
        return payload[24:]  # Skip timestamp + IV
