"""Nanvix matplotlib.markers stub."""

class MarkerStyle:
    filled_markers = ('o', 'v', '^', '<', '>', 's', 'p', '*', 'h', 'H', 'D', 'd')
    fillstyles = ('full', 'left', 'right', 'bottom', 'top', 'none')

    def __init__(self, marker=None, fillstyle=None):
        self._marker = marker
        self._fillstyle = fillstyle

    def get_path(self): return None
    def get_transform(self): return None
    def is_filled(self): return True
