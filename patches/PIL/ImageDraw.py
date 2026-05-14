"""Stub PIL.ImageDraw for Nanvix (no native Pillow)."""


class ImageDraw:
    """Minimal ImageDraw stub."""

    def __init__(self, im, mode=None):
        self.im = im
        self._mode = mode

    def text(self, xy, text, fill=None, font=None, anchor=None, **kw):
        pass

    def textbbox(self, xy, text, font=None, anchor=None, **kw):
        return (0, 0, 0, 0)

    def textlength(self, text, font=None, **kw):
        return 0

    def rectangle(self, xy, fill=None, outline=None, width=1):
        pass

    def line(self, xy, fill=None, width=0):
        pass

    def ellipse(self, xy, fill=None, outline=None, width=1):
        pass


class Draw(ImageDraw):
    pass
