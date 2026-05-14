"""Nanvix matplotlib.colors stub."""

from __future__ import annotations


def to_rgb(c):
    rgba = to_rgba(c)
    return rgba[:3]


def to_rgba(c, alpha=None):
    if isinstance(c, (tuple, list)):
        if len(c) == 3:
            return (*c, alpha if alpha is not None else 1.0)
        return tuple(c)
    _map = {
        "r": (1, 0, 0, 1), "g": (0, 0.5, 0, 1), "b": (0, 0, 1, 1),
        "k": (0, 0, 0, 1), "w": (1, 1, 1, 1), "c": (0, 1, 1, 1),
        "m": (1, 0, 1, 1), "y": (1, 1, 0, 1),
        "red": (1, 0, 0, 1), "green": (0, 0.5, 0, 1), "blue": (0, 0, 1, 1),
        "black": (0, 0, 0, 1), "white": (1, 1, 1, 1),
    }
    if isinstance(c, str) and c.lower() in _map:
        rgba = _map[c.lower()]
        if alpha is not None:
            rgba = rgba[:3] + (alpha,)
        return rgba
    return (0, 0, 0, alpha if alpha is not None else 1.0)


def to_rgba_array(c, alpha=None):
    if hasattr(c, '__len__') and not isinstance(c, str):
        return [to_rgba(ci, alpha) for ci in c]
    return [to_rgba(c, alpha)]


def to_hex(c, keep_alpha=False):
    rgba = to_rgba(c)
    if keep_alpha:
        return "#{:02x}{:02x}{:02x}{:02x}".format(
            int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255), int(rgba[3]*255))
    return "#{:02x}{:02x}{:02x}".format(
        int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255))


class Normalize:
    def __init__(self, vmin=None, vmax=None, clip=False):
        self.vmin = vmin
        self.vmax = vmax
        self.clip = clip

    def __call__(self, value):
        return value


class Colormap:
    def __init__(self, name="viridis", N=256):
        self.name = name
        self.N = N

    def __call__(self, X, alpha=None):
        return (0.5, 0.5, 0.5, 1.0)


class ListedColormap(Colormap):
    def __init__(self, colors, name="custom", N=None):
        super().__init__(name, N or len(colors))
        self.colors = colors


class LinearSegmentedColormap(Colormap):
    @staticmethod
    def from_list(name, colors, N=256):
        return LinearSegmentedColormap(name, N)

    def __init__(self, name="custom", segmentdata=None, N=256):
        super().__init__(name, N)


class BoundaryNorm(Normalize):
    def __init__(self, boundaries, ncolors, clip=False):
        super().__init__(clip=clip)
        self.boundaries = boundaries
        self.ncolors = ncolors
