"""Nanvix scipy.interpolate stub."""


class interp1d:
    def __init__(self, x, y, kind='linear', **kwargs):
        self._x = x
        self._y = y

    def __call__(self, x_new):
        return x_new
