"""Nanvix cryptography.hazmat.primitives.ciphers stub."""


class Cipher:
    """Minimal Cipher stub."""
    def __init__(self, algorithm, mode, backend=None):
        self.algorithm = algorithm
        self.mode = mode

    def encryptor(self):
        return _CipherContext()

    def decryptor(self):
        return _CipherContext()


class _CipherContext:
    def update(self, data):
        return data

    def finalize(self):
        return b""


class algorithms:
    """Cipher algorithm stubs."""
    class AES:
        name = "AES"
        block_size = 128
        key_sizes = frozenset(range(128, 257, 64))
        def __init__(self, key):
            self.key = key

    class ARC4:
        name = "ARC4"
        def __init__(self, key):
            self.key = key


class modes:
    """Cipher mode stubs."""
    class CBC:
        name = "CBC"
        def __init__(self, iv):
            self.initialization_vector = iv

    class ECB:
        name = "ECB"
        def __init__(self):
            pass
