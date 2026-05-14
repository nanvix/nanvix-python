"""Nanvix matplotlib.gridspec stub."""

class GridSpec:
    def __init__(self, nrows, ncols, **kwargs):
        self.nrows = nrows
        self.ncols = ncols
    def __getitem__(self, key): return SubplotSpec(self, key)

class SubplotSpec:
    def __init__(self, gridspec, key):
        self._gridspec = gridspec
        self._key = key
    def get_gridspec(self): return self._gridspec

class GridSpecFromSubplotSpec(GridSpec):
    def __init__(self, nrows, ncols, subplot_spec=None, **kwargs):
        super().__init__(nrows, ncols, **kwargs)
