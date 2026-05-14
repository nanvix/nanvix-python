"""Nanvix cryptography.hazmat.primitives stub."""


class hashes:
    class SHA256:
        name = "sha256"
        digest_size = 32
        block_size = 64

    class SHA1:
        name = "sha1"
        digest_size = 20
        block_size = 64

    class MD5:
        name = "md5"
        digest_size = 16
        block_size = 64

    class Hash:
        def __init__(self, algorithm, backend=None):
            import hashlib
            self._h = hashlib.new(algorithm.name)

        def update(self, data):
            self._h.update(data)

        def finalize(self):
            return self._h.digest()

        def copy(self):
            h = hashes.Hash.__new__(hashes.Hash)
            h._h = self._h.copy()
            return h
