"""Pure-Python font metrics for NanVix.

Provides deterministic text metrics used by python-pptx layout code when
computing text box dimensions.  No actual font rendering.
"""

from __future__ import annotations


class FreeTypeFont:
    """Minimal font metrics stub."""

    def __init__(self, font=None, size=10, index=0, encoding="", layout_engine=None):
        self.size = size
        self.path = font
        self.font = self  # self-reference for .font.getsize() pattern

    def getlength(self, text, mode="", direction="", features=None, language=None):
        return len(text) * self.size * 0.6

    def getbbox(self, text, mode="", direction="", features=None, language=None, anchor=None):
        w = self.getlength(text)
        return (0, 0, int(w), int(self.size * 1.2))

    def getsize(self, text, *args, **kwargs):
        w = int(self.getlength(text))
        h = int(self.size * 1.2)
        return (w, h), (0, 0)

    def getmetrics(self):
        return (int(self.size * 0.8), int(self.size * 0.2))


def truetype(font=None, size=10, index=0, encoding="", layout_engine=None):
    return FreeTypeFont(font=font, size=size, index=index, encoding=encoding)


def load_default():
    return FreeTypeFont(size=10)


class TransposedFont:
    """Stub for TransposedFont (wraps a font with a rotation)."""

    def __init__(self, font, orientation=None):
        self.font = font
        self.orientation = orientation

    def getlength(self, text, *args, **kwargs):
        return self.font.getlength(text, *args, **kwargs)

    def getbbox(self, text, *args, **kwargs):
        return self.font.getbbox(text, *args, **kwargs)

    def getsize(self, text, *args, **kwargs):
        return self.font.getsize(text, *args, **kwargs)
