"""Nanvix matplotlib.pyplot shim — no-op plotting API.

Allows downstream code to call plt.figure(), plt.plot(), etc.
without rendering.
"""

from __future__ import annotations


class Figure:
    """Stub Figure."""

    def __init__(self, figsize=None, dpi=None, **kwargs):
        self.figsize = figsize or (6.4, 4.8)
        self.dpi = dpi or 100
        self._axes = []
        self.number = 1

    def add_subplot(self, *args, **kwargs):
        ax = Axes(self)
        self._axes.append(ax)
        return ax

    def add_axes(self, rect, **kwargs):
        ax = Axes(self)
        self._axes.append(ax)
        return ax

    @property
    def axes(self):
        return self._axes

    def get_axes(self):
        return self._axes

    def gca(self):
        if not self._axes:
            self._axes.append(Axes(self))
        return self._axes[-1]

    def savefig(self, fname, **kwargs):
        pass

    def tight_layout(self, **kwargs):
        pass

    def suptitle(self, t, **kwargs):
        pass

    def subplots_adjust(self, **kwargs):
        pass

    def set_size_inches(self, w, h=None):
        if h is None and hasattr(w, '__len__'):
            w, h = w
        self.figsize = (w, h)

    def clear(self):
        self._axes.clear()

    def clf(self):
        self.clear()

    @property
    def patch(self):
        return _Patch()

    def colorbar(self, mappable=None, **kwargs):
        return _Colorbar()


class Axes:
    """Stub Axes."""

    def __init__(self, fig=None):
        self.figure = fig
        self.lines = []
        self.patches = []
        self.collections = []
        self.images = []
        self.texts = []
        self._title = ""
        self._xlabel = ""
        self._ylabel = ""

    def plot(self, *args, **kwargs):
        return [_Line2D()]

    def scatter(self, *args, **kwargs):
        return _PathCollection()

    def bar(self, *args, **kwargs):
        return [_Patch()]

    def barh(self, *args, **kwargs):
        return [_Patch()]

    def hist(self, *args, **kwargs):
        return ([], [], [])

    def pie(self, *args, **kwargs):
        return ([], [])

    def fill_between(self, *args, **kwargs):
        return _PolyCollection()

    def imshow(self, *args, **kwargs):
        return _AxesImage()

    def contour(self, *args, **kwargs):
        return _ContourSet()

    def contourf(self, *args, **kwargs):
        return _ContourSet()

    def pcolormesh(self, *args, **kwargs):
        return _QuadMesh()

    def axhline(self, *args, **kwargs):
        return _Line2D()

    def axvline(self, *args, **kwargs):
        return _Line2D()

    def hlines(self, *args, **kwargs):
        return _LineCollection()

    def vlines(self, *args, **kwargs):
        return _LineCollection()

    def errorbar(self, *args, **kwargs):
        return (_Line2D(), [], [])

    def set_title(self, label, **kwargs):
        self._title = label

    def set_xlabel(self, label, **kwargs):
        self._xlabel = label

    def set_ylabel(self, label, **kwargs):
        self._ylabel = label

    def get_title(self):
        return self._title

    def get_xlabel(self):
        return self._xlabel

    def get_ylabel(self):
        return self._ylabel

    def set_xlim(self, *args, **kwargs):
        pass

    def set_ylim(self, *args, **kwargs):
        pass

    def get_xlim(self):
        return (0, 1)

    def get_ylim(self):
        return (0, 1)

    def set_xscale(self, value, **kwargs):
        pass

    def set_yscale(self, value, **kwargs):
        pass

    def set_xticks(self, ticks, labels=None, **kwargs):
        pass

    def set_yticks(self, ticks, labels=None, **kwargs):
        pass

    def tick_params(self, **kwargs):
        pass

    def legend(self, *args, **kwargs):
        return _Legend()

    def annotate(self, text, xy, **kwargs):
        return _Annotation()

    def text(self, x, y, s, **kwargs):
        return _Text()

    def grid(self, visible=None, **kwargs):
        pass

    def set_aspect(self, aspect, **kwargs):
        pass

    def invert_yaxis(self):
        pass

    def invert_xaxis(self):
        pass

    def twinx(self):
        return Axes(self.figure)

    def twiny(self):
        return Axes(self.figure)

    def clear(self):
        pass

    def cla(self):
        self.clear()

    def set_facecolor(self, color):
        pass

    @property
    def xaxis(self):
        return _Axis()

    @property
    def yaxis(self):
        return _Axis()

    @property
    def patch(self):
        return _Patch()

    def get_position(self):
        class _Bbox:
            x0 = 0
            y0 = 0
            x1 = 1
            y1 = 1
            width = 1
            height = 1
        return _Bbox()

    def set_position(self, pos):
        pass

    @property
    def spines(self):
        return _Spines()


# Stub artist classes
class _Line2D:
    def set_data(self, *args): pass
    def set_color(self, c): pass
    def set_linewidth(self, w): pass
    def get_data(self): return ([], [])
    def remove(self): pass

class _Patch:
    def set_facecolor(self, c): pass
    def set_edgecolor(self, c): pass
    def set_alpha(self, a): pass
    def get_facecolor(self): return (1, 1, 1, 1)

class _PathCollection:
    def set_offsets(self, offsets): pass

class _PolyCollection:
    pass

class _AxesImage:
    def set_data(self, data): pass

class _ContourSet:
    pass

class _QuadMesh:
    pass

class _LineCollection:
    pass

class _Legend:
    def set_title(self, title): pass
    def get_title(self): return _Text()

class _Annotation:
    pass

class _Text:
    def set_text(self, s): pass
    def get_text(self): return ""

class _Colorbar:
    def set_label(self, label): pass

class _Axis:
    def set_visible(self, b): pass
    def set_label_text(self, label): pass
    def set_ticks(self, ticks): pass

class _Spine:
    def set_visible(self, b): pass
    def set_color(self, c): pass

class _Spines(dict):
    def __getitem__(self, key):
        return _Spine()
    def __missing__(self, key):
        return _Spine()
    def values(self):
        return [_Spine() for _ in range(4)]


# ---------------------------------------------------------------------------
# Module-level pyplot functions
# ---------------------------------------------------------------------------

_current_fig = None


def figure(num=None, figsize=None, dpi=None, **kwargs):
    global _current_fig
    _current_fig = Figure(figsize=figsize, dpi=dpi)
    return _current_fig


def subplots(nrows=1, ncols=1, *, squeeze=True, figsize=None, **kwargs):
    fig = Figure(figsize=figsize)
    if nrows == 1 and ncols == 1:
        ax = fig.add_subplot()
        return fig, ax
    axes = [[fig.add_subplot() for _ in range(ncols)] for _ in range(nrows)]
    if squeeze:
        if nrows == 1:
            axes = axes[0]
        elif ncols == 1:
            axes = [row[0] for row in axes]
    return fig, axes


def subplot(*args, **kwargs):
    fig = gcf()
    return fig.add_subplot(*args, **kwargs)


def gcf():
    global _current_fig
    if _current_fig is None:
        _current_fig = Figure()
    return _current_fig


def gca():
    return gcf().gca()


def plot(*args, **kwargs):
    return gca().plot(*args, **kwargs)


def scatter(*args, **kwargs):
    return gca().scatter(*args, **kwargs)


def bar(*args, **kwargs):
    return gca().bar(*args, **kwargs)


def barh(*args, **kwargs):
    return gca().barh(*args, **kwargs)


def hist(*args, **kwargs):
    return gca().hist(*args, **kwargs)


def pie(*args, **kwargs):
    return gca().pie(*args, **kwargs)


def imshow(*args, **kwargs):
    return gca().imshow(*args, **kwargs)


def contour(*args, **kwargs):
    return gca().contour(*args, **kwargs)


def contourf(*args, **kwargs):
    return gca().contourf(*args, **kwargs)


def fill_between(*args, **kwargs):
    return gca().fill_between(*args, **kwargs)


def axhline(*args, **kwargs):
    return gca().axhline(*args, **kwargs)


def axvline(*args, **kwargs):
    return gca().axvline(*args, **kwargs)


def errorbar(*args, **kwargs):
    return gca().errorbar(*args, **kwargs)


def title(label, **kwargs):
    gca().set_title(label, **kwargs)


def xlabel(label, **kwargs):
    gca().set_xlabel(label, **kwargs)


def ylabel(label, **kwargs):
    gca().set_ylabel(label, **kwargs)


def xlim(*args, **kwargs):
    gca().set_xlim(*args, **kwargs)


def ylim(*args, **kwargs):
    gca().set_ylim(*args, **kwargs)


def xscale(value, **kwargs):
    gca().set_xscale(value, **kwargs)


def yscale(value, **kwargs):
    gca().set_yscale(value, **kwargs)


def xticks(ticks=None, labels=None, **kwargs):
    if ticks is not None:
        gca().set_xticks(ticks, labels=labels, **kwargs)


def yticks(ticks=None, labels=None, **kwargs):
    if ticks is not None:
        gca().set_yticks(ticks, labels=labels, **kwargs)


def legend(*args, **kwargs):
    return gca().legend(*args, **kwargs)


def grid(visible=None, **kwargs):
    gca().grid(visible, **kwargs)


def colorbar(mappable=None, **kwargs):
    return _Colorbar()


def annotate(text, xy, **kwargs):
    return gca().annotate(text, xy, **kwargs)


def text(x, y, s, **kwargs):
    return gca().text(x, y, s, **kwargs)


def savefig(fname, **kwargs):
    gcf().savefig(fname, **kwargs)


def show(*args, **kwargs):
    pass


def close(fig=None):
    global _current_fig
    _current_fig = None


def clf():
    global _current_fig
    if _current_fig:
        _current_fig.clf()


def cla():
    gca().cla()


def tight_layout(**kwargs):
    gcf().tight_layout(**kwargs)


def suptitle(t, **kwargs):
    gcf().suptitle(t, **kwargs)


def subplots_adjust(**kwargs):
    gcf().subplots_adjust(**kwargs)


def switch_backend(backend):
    pass


def ion():
    pass


def ioff():
    pass


def isinteractive():
    return False


def get_cmap(name=None, lut=None):
    """Return a stub colormap."""
    class _StubCmap:
        def __init__(self, name):
            self.name = name
        def __call__(self, x, alpha=None, bytes=False):
            import numpy as np
            if hasattr(x, '__len__'):
                return [(0.0, 0.0, 0.0, 1.0)] * len(x)
            return (0.0, 0.0, 0.0, 1.0)
    return _StubCmap(name or "viridis")
