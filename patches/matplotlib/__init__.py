"""Nanvix matplotlib shim — non-rendering visualization stub.

Provides the minimum matplotlib API surface needed by downstream
packages (seaborn, plotnine, wordcloud) for import and figure
construction.  No actual rendering.
"""

__version__ = "3.9.2"

# Backend configuration
_backend = "agg"


def use(backend, force=False):
    global _backend
    _backend = backend


def get_backend():
    return _backend


# Expose rcParams as a dict-like
class _RcParams(dict):
    def __init__(self):
        super().__init__()
        self.update({
            "backend": "agg",
            "figure.figsize": [6.4, 4.8],
            "figure.dpi": 100,
            "font.size": 10,
            "axes.labelsize": "medium",
            "axes.titlesize": "large",
            "lines.linewidth": 1.5,
            "lines.markersize": 6,
            "legend.fontsize": "medium",
            "savefig.dpi": "figure",
            "savefig.format": "png",
        })

    def __getattr__(self, name):
        if name.startswith("_"):
            return super().__getattribute__(name)
        return self.get(name)

rcParams = _RcParams()
rc_context = rcParams


def rc(group, **kwargs):
    for k, v in kwargs.items():
        rcParams[f"{group}.{k}"] = v


def rcdefaults():
    pass


# Sentinel for style submodule
class _Style:
    available = ["default", "ggplot", "seaborn", "classic"]
    library = {}

    def use(self, style):
        pass

    def context(self, style, after_reset=False):
        class _Ctx:
            def __enter__(self_):
                pass
            def __exit__(self_, *args):
                pass
        return _Ctx()

style = _Style()

# Make submodules accessible as attributes (e.g. matplotlib.cm, matplotlib.ticker)
from matplotlib import cm, ticker, colors, pyplot, patches, collections  # noqa: E402
from matplotlib import figure, axes, axis, cbook, lines, markers  # noqa: E402
from matplotlib import path, scale, transforms, dates, gridspec, legend  # noqa: E402
from matplotlib import artist  # noqa: E402
