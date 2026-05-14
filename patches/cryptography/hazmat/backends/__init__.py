"""Nanvix cryptography.hazmat.backends stub."""


def default_backend():
    """Return the default backend (stub)."""
    return _DefaultBackend()


class _DefaultBackend:
    name = "nanvix-stub"

    def __repr__(self):
        return "<NanvixStubBackend>"
