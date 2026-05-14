"""Nanvix scipy.stats stub."""

import math as _math


class _Distribution:
    """Base distribution stub."""
    def __init__(self, name="dist"):
        self._name = name

    def pdf(self, x, *args, **kwargs):
        return 0.0

    def cdf(self, x, *args, **kwargs):
        return 0.5

    def ppf(self, q, *args, **kwargs):
        return 0.0

    def rvs(self, *args, size=None, **kwargs):
        if size is None:
            return 0.0
        try:
            import numpy as np
            return np.zeros(size)
        except ImportError:
            return [0.0] * (size if isinstance(size, int) else 1)

    def fit(self, data, *args, **kwargs):
        return (0.0, 1.0)

    def mean(self, *args, **kwargs):
        return 0.0

    def var(self, *args, **kwargs):
        return 1.0

    def std(self, *args, **kwargs):
        return 1.0


norm = _Distribution("norm")
uniform = _Distribution("uniform")
expon = _Distribution("expon")
chi2 = _Distribution("chi2")
t = _Distribution("t")
f = _Distribution("f")
gamma = _Distribution("gamma")
beta = _Distribution("beta")
poisson = _Distribution("poisson")
binom = _Distribution("binom")
lognorm = _Distribution("lognorm")


def pearsonr(x, y):
    return (0.0, 1.0)

def spearmanr(a, b=None):
    return (0.0, 1.0)

def kendalltau(x, y):
    return (0.0, 1.0)

def ttest_ind(a, b, equal_var=True):
    return (0.0, 1.0)

def ttest_1samp(a, popmean):
    return (0.0, 1.0)

def mannwhitneyu(x, y, alternative="two-sided"):
    return (0.0, 1.0)

def wilcoxon(x, y=None):
    return (0.0, 1.0)

def linregress(x, y=None):
    class _Result:
        slope = 0.0
        intercept = 0.0
        rvalue = 0.0
        pvalue = 1.0
        stderr = 0.0
    return _Result()

def zscore(a, axis=0, ddof=0):
    try:
        import numpy as np
        a = np.asarray(a)
        return np.zeros(a.shape)
    except ImportError:
        return a

def describe(a, axis=0):
    class _Desc:
        nobs = 0
        minmax = (0, 0)
        mean = 0.0
        variance = 0.0
        skewness = 0.0
        kurtosis = 0.0
    return _Desc()

def mode(a, axis=0):
    class _Mode:
        mode = a[0] if a else 0
        count = 1
    return _Mode()

def iqr(x, axis=None):
    return 0.0

def entropy(pk, qk=None, base=None):
    return 0.0

def ks_2samp(data1, data2):
    return (0.0, 1.0)

def shapiro(x):
    return (0.0, 1.0)

def normaltest(a):
    return (0.0, 1.0)
