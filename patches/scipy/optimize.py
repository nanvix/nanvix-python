"""Nanvix scipy.optimize stub."""


def minimize(fun, x0, method=None, **kwargs):
    class _Result:
        x = x0
        fun = 0.0
        success = True
        message = "stub"
    return _Result()

def curve_fit(f, xdata, ydata, p0=None, **kwargs):
    if p0 is None:
        p0 = [0.0]
    return (p0, [[0.0]])

def root(fun, x0, method=None, **kwargs):
    class _Result:
        x = x0
        success = True
    return _Result()

def fsolve(func, x0, **kwargs):
    return x0

def brentq(f, a, b, **kwargs):
    return (a + b) / 2.0
