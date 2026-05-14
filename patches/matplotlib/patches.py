"""Nanvix matplotlib.patches stub."""


class Patch:
    def __init__(self, **kwargs):
        pass

class Rectangle(Patch):
    def __init__(self, xy, width, height, **kwargs):
        self.xy = xy
        self.width = width
        self.height = height

class Circle(Patch):
    def __init__(self, xy, radius=5, **kwargs):
        self.center = xy
        self.radius = radius

class FancyBboxPatch(Patch):
    def __init__(self, xy, width, height, boxstyle="round", **kwargs):
        self.xy = xy
        self.width = width
        self.height = height
