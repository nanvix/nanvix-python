"""Test: cryptography (shim)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import cryptography
    from cryptography.fernet import Fernet

    # Key generation
    key = Fernet.generate_key()
    assert isinstance(key, bytes)
    assert len(key) > 0

    # Encrypt/decrypt
    f = Fernet(key)
    token = f.encrypt(b"Hello Nanvix")
    assert isinstance(token, bytes)

    decrypted = f.decrypt(token)
    assert decrypted == b"Hello Nanvix"

    # Hazmat import
    from cryptography.hazmat.primitives import hashes
    h = hashes.Hash(hashes.SHA256())
    h.update(b"test")
    digest = h.finalize()
    assert len(digest) == 32

    # Version
    assert cryptography.__version__

    print("cryptography: PASS")
except Exception as e:
    print(f"cryptography: FAIL: {e}")
    sys.exit(1)
