"""Stub PIL.ImageFilter for Nanvix (no native Pillow)."""


class Filter:
    pass


class GaussianBlur(Filter):
    name = "GaussianBlur"

    def __init__(self, radius=2):
        self.radius = radius


class BLUR(Filter):
    name = "BLUR"


class SMOOTH(Filter):
    name = "SMOOTH"
