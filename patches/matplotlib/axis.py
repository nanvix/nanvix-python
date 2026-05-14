"""Nanvix matplotlib.axis stub."""
from matplotlib.ticker import Formatter, Locator

class Axis:
    def set_major_formatter(self, formatter): pass
    def set_minor_formatter(self, formatter): pass
    def set_major_locator(self, locator): pass
    def set_minor_locator(self, locator): pass
    def set_label_text(self, label): pass
    def get_label(self): return type('', (), {'get_text': lambda: ''})()

class XAxis(Axis): pass
class YAxis(Axis): pass
