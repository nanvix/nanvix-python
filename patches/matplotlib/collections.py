"""Nanvix matplotlib.collections stub."""

class Collection:
    def set_alpha(self, alpha): pass
    def set_visible(self, b): pass

class PathCollection(Collection):
    def __init__(self, paths=None, **kwargs): pass
    def set_offsets(self, offsets): pass

class LineCollection(Collection):
    def __init__(self, segments=None, **kwargs): pass

class PolyCollection(Collection):
    def __init__(self, verts=None, **kwargs): pass

class PatchCollection(Collection):
    def __init__(self, patches=None, **kwargs): pass

class QuadMesh(Collection):
    pass
