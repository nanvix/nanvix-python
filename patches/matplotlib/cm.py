"""Nanvix matplotlib.cm stub — colormap registry."""

_cmap_registry = {}


class ScalarMappable:
    def __init__(self, norm=None, cmap=None):
        self.norm = norm
        self.cmap = cmap


def get_cmap(name=None, lut=None):
    from . import colors
    if name and name in _cmap_registry:
        return _cmap_registry[name]
    return colors.Colormap(name or "viridis")


def register_cmap(name=None, cmap=None, data=None, lut=None):
    if cmap is not None:
        _cmap_registry[name or getattr(cmap, 'name', 'custom')] = cmap
    elif name is not None:
        from . import colors
        _cmap_registry[name] = colors.Colormap(name)
