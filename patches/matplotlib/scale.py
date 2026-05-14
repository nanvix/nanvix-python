"""Nanvix matplotlib.scale stub."""

class ScaleBase:
    def __init__(self, axis, **kwargs): pass
    def get_transform(self): return None

class LinearScale(ScaleBase):
    name = 'linear'

class LogScale(ScaleBase):
    name = 'log'
    def __init__(self, axis, base=10, **kwargs):
        super().__init__(axis)
        self.base = base

class SymmetricalLogScale(ScaleBase):
    name = 'symlog'

class FuncScale(ScaleBase):
    name = 'function'
