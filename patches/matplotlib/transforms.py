"""Nanvix matplotlib.transforms stub."""

class Transform:
    pass

class Affine2D(Transform):
    def __init__(self, matrix=None): pass
    def rotate_deg(self, degrees): return self
    def translate(self, tx, ty): return self
    def scale(self, sx, sy=None): return self
    def __add__(self, other): return self

class Bbox:
    def __init__(self, points=None): pass
    @staticmethod
    def from_bounds(x0, y0, width, height): return Bbox()
    @staticmethod
    def from_extents(x0, y0, x1, y1): return Bbox()

class BboxBase:
    pass

class TransformedBbox(BboxBase):
    def __init__(self, bbox, transform): pass

class BlendedGenericTransform(Transform):
    def __init__(self, x_transform, y_transform): pass

class CompositeGenericTransform(Transform):
    def __init__(self, a, b): pass

class ScaledTranslation(Affine2D):
    def __init__(self, xt, yt, scale_trans): pass

class IdentityTransform(Transform):
    pass

def blended_transform_factory(x_transform, y_transform):
    return BlendedGenericTransform(x_transform, y_transform)

def offset_copy(trans, fig=None, x=0, y=0, units='inches'):
    return trans
