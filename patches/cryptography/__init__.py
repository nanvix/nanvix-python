"""Nanvix cryptography shim — minimal pure-Python crypto stubs.

Provides import compatibility for packages that optionally depend on
cryptography (e.g., pdfminer.six for encrypted PDFs).  OpenSSL is
already statically linked in Nanvix CPython.
"""

__version__ = "43.0.0"


class InvalidSignature(Exception):
    pass


class InvalidKey(Exception):
    pass
