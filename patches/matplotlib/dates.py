"""Nanvix matplotlib.dates stub."""
from matplotlib.ticker import Formatter, Locator

class DateFormatter(Formatter):
    def __init__(self, fmt, tz=None): self.fmt = fmt

class DateLocator(Locator): pass
class AutoDateLocator(DateLocator): pass
class AutoDateFormatter(DateFormatter):
    def __init__(self, locator, tz=None): pass
class ConciseDateFormatter(DateFormatter):
    def __init__(self, locator, tz=None, formats=None, offset_formats=None, show_offset=True): pass

class YearLocator(DateLocator): pass
class MonthLocator(DateLocator): pass
class DayLocator(DateLocator): pass
class HourLocator(DateLocator): pass

def date2num(d): return 0.0
def num2date(x, tz=None): return None
