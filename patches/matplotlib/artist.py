"""Nanvix matplotlib.artist stub."""

class Artist:
    def set_visible(self, b): pass
    def set_alpha(self, alpha): pass
    def get_label(self): return ""
    def set_label(self, s): pass
    def set_zorder(self, level): pass
    def set_clip_on(self, b): pass
    def remove(self): pass
    def get_transform(self): return None

def allow_rasterization(draw):
    return draw

def get(obj, property=None):
    return None

def setp(obj, *args, **kwargs):
    pass

def getp(obj, property=None):
    return None
