"""Nanvix matplotlib.ticker stub."""


class Formatter:
    def __call__(self, x, pos=None):
        return str(x)

class ScalarFormatter(Formatter):
    def __init__(self, useOffset=None, useMathText=None):
        pass

class FuncFormatter(Formatter):
    def __init__(self, func):
        self.func = func
    def __call__(self, x, pos=None):
        return self.func(x, pos)

class FixedFormatter(Formatter):
    def __init__(self, seq):
        self.seq = seq

class Locator:
    def __call__(self):
        return []

class MaxNLocator(Locator):
    def __init__(self, nbins=None, **kwargs):
        self.nbins = nbins

class FixedLocator(Locator):
    def __init__(self, locs):
        self.locs = locs

class AutoLocator(Locator):
    pass

class NullLocator(Locator):
    pass

class NullFormatter(Formatter):
    def __call__(self, x, pos=None):
        return ""

class AutoMinorLocator(Locator):
    def __init__(self, n=None):
        self.ndivs = n

class MultipleLocator(Locator):
    def __init__(self, base=1.0):
        self.base = base

class LogLocator(Locator):
    def __init__(self, base=10.0, subs=None, numticks=None):
        self.base = base

class LogFormatter(Formatter):
    def __init__(self, base=10.0, labelOnlyBase=False):
        self.base = base

class LogFormatterSciNotation(LogFormatter):
    pass

class PercentFormatter(Formatter):
    def __init__(self, xmax=100, decimals=None, symbol='%'):
        self.xmax = xmax

class StrMethodFormatter(Formatter):
    def __init__(self, fmt):
        self.fmt = fmt
    def __call__(self, x, pos=None):
        return self.fmt.format(x=x)

class FormatStrFormatter(Formatter):
    def __init__(self, fmt):
        self.fmt = fmt
    def __call__(self, x, pos=None):
        return self.fmt % x

class LinearLocator(Locator):
    def __init__(self, numticks=None):
        self.numticks = numticks

class IndexLocator(Locator):
    def __init__(self, base, offset):
        self.base = base
        self.offset = offset

class SymmetricalLogLocator(Locator):
    def __init__(self, transform=None, subs=None, linthresh=None, base=None):
        pass

class EngFormatter(Formatter):
    ENG_PREFIXES = {}
    def __init__(self, unit="", places=None, sep=" ", usetex=None, useMathText=None):
        self.unit = unit
        self.places = places
        self.sep = sep
    def __call__(self, x, pos=None):
        return f"{x}{self.sep}{self.unit}"
