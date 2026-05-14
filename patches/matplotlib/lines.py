"""Nanvix matplotlib.lines stub."""


class Line2D:
    def __init__(self, xdata, ydata, **kwargs):
        self.xdata = xdata
        self.ydata = ydata

    def set_data(self, *args):
        pass

    def get_data(self):
        return (self.xdata, self.ydata)

    def set_color(self, c):
        pass

    def set_linewidth(self, w):
        pass

    def remove(self):
        pass
