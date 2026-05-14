"""Nanvix matplotlib.path stub."""

class Path:
    MOVETO = 1
    LINETO = 2
    CURVE3 = 3
    CURVE4 = 4
    CLOSEPOLY = 79

    def __init__(self, vertices=None, codes=None, closed=False):
        self.vertices = vertices
        self.codes = codes

    @classmethod
    def unit_circle(cls): return cls()
    @classmethod
    def unit_rectangle(cls): return cls()
