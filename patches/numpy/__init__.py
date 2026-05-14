"""Nanvix numpy shim — pure-Python array stub.

Provides the minimum numpy API surface needed by downstream packages
(seaborn, plotnine, altair, pandas, matplotlib, wordcloud) for import
and basic construction.  No actual numerical computation.
"""

__version__ = "1.26.4"

import math as _math
import builtins as _builtins

# Save builtins before module-level functions shadow them
_builtin_sum = sum
_builtin_max = max
_builtin_min = min
_builtin_abs = _builtins.abs

# ---------------------------------------------------------------------------
# Dtype stubs
# ---------------------------------------------------------------------------

class dtype:
    """Minimal dtype descriptor."""
    def __init__(self, tp=None):
        self._tp = tp or float
        if isinstance(tp, str):
            self.name = tp
        elif tp is int:
            self.name = "int64"
        elif tp is float:
            self.name = "float64"
        elif tp is bool:
            self.name = "bool"
        elif tp is complex:
            self.name = "complex128"
        else:
            self.name = "float64"
        self.kind = self.name[0] if self.name else "f"

    def __repr__(self):
        return f"dtype('{self.name}')"

    def __eq__(self, other):
        if isinstance(other, dtype):
            return self.name == other.name
        return self.name == str(other)

    def __hash__(self):
        return hash(self.name)


_dtype_class = dtype  # alias to avoid shadowing by parameter names


float16 = dtype("float16")
float32 = dtype("float32")
float64 = dtype("float64")
int8 = dtype("int8")
int16 = dtype("int16")
int32 = dtype("int32")
int64 = dtype("int64")
uint8 = dtype("uint8")
uint16 = dtype("uint16")
uint32 = dtype("uint32")
uint64 = dtype("uint64")
bool_ = dtype("bool")
complex64 = dtype("complex64")
complex128 = dtype("complex128")
object_ = dtype("object")
str_ = dtype("str")

# Scalar type aliases
floating = float
integer = int
signedinteger = int
unsignedinteger = int
number = (int, float, complex)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

inf = float("inf")
nan = float("nan")
pi = _math.pi
e = _math.e
newaxis = None
PINF = float("inf")
NINF = float("-inf")

# ---------------------------------------------------------------------------
# ndarray
# ---------------------------------------------------------------------------

class ndarray:
    """Minimal ndarray stub backed by a flat Python list."""

    def __init__(self, shape, dtype=None, buffer=None):
        if isinstance(shape, int):
            shape = (shape,)
        self.shape = tuple(shape)
        self.dtype = dtype if isinstance(dtype, _dtype_class) else _dtype_class(dtype)
        self.ndim = len(self.shape)
        self._size = 1
        for s in self.shape:
            self._size *= s
        if buffer is not None:
            self._data = list(buffer)[:self._size]
            self._data.extend([0] * (self._size - len(self._data)))
        else:
            self._data = [0] * self._size

    @property
    def size(self):
        return self._size

    @property
    def T(self):
        return self

    def __len__(self):
        return self.shape[0] if self.shape else 0

    def __repr__(self):
        return f"array({self._data})"

    def __iter__(self):
        if self.ndim <= 1:
            return iter(self._data)
        # For multi-dim, iterate over first axis
        step = self._size // self.shape[0] if self.shape[0] else 1
        rows = []
        for i in range(self.shape[0]):
            sub = ndarray(self.shape[1:], self.dtype)
            sub._data = self._data[i * step:(i + 1) * step]
            rows.append(sub)
        return iter(rows)

    def __getitem__(self, key):
        if isinstance(key, tuple):
            # Multi-dimensional indexing: arr[i, j, ...]
            idx = 0
            for dim, k in enumerate(key):
                stride = 1
                for s in self.shape[dim + 1:]:
                    stride *= s
                idx += k * stride
            remaining = self.shape[len(key):]
            if not remaining:
                return self._data[idx]
            sub = ndarray(remaining, self.dtype)
            step = 1
            for s in remaining:
                step *= s
            sub._data = self._data[idx:idx + step]
            return sub
        if isinstance(key, int):
            if self.ndim <= 1:
                return self._data[key]
            step = self._size // self.shape[0]
            sub = ndarray(self.shape[1:], self.dtype)
            sub._data = self._data[key * step:(key + 1) * step]
            return sub
        if isinstance(key, slice):
            items = self._data[key]
            result = ndarray((len(items),), self.dtype)
            result._data = items
            return result
        return self._data[0] if self._data else 0

    def __setitem__(self, key, value):
        if isinstance(key, tuple):
            idx = 0
            for dim, k in enumerate(key):
                stride = 1
                for s in self.shape[dim + 1:]:
                    stride *= s
                idx += k * stride
            self._data[idx] = value
        elif isinstance(key, int):
            self._data[key] = value

    def __add__(self, other):
        return _binop(self, other, lambda a, b: a + b)

    def __sub__(self, other):
        return _binop(self, other, lambda a, b: a - b)

    def __mul__(self, other):
        return _binop(self, other, lambda a, b: a * b)

    def __truediv__(self, other):
        return _binop(self, other, lambda a, b: a / b if b != 0 else nan)

    def __radd__(self, other):
        return self.__add__(other)

    def __rsub__(self, other):
        return _binop(self, other, lambda a, b: b - a)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __neg__(self):
        result = ndarray(self.shape, self.dtype)
        result._data = [-x for x in self._data]
        return result

    def __eq__(self, other):
        return _binop(self, other, lambda a, b: a == b)

    def __lt__(self, other):
        return _binop(self, other, lambda a, b: a < b)

    def __gt__(self, other):
        return _binop(self, other, lambda a, b: a > b)

    def __le__(self, other):
        return _binop(self, other, lambda a, b: a <= b)

    def __ge__(self, other):
        return _binop(self, other, lambda a, b: a >= b)

    def __hash__(self):
        return id(self)

    def __bool__(self):
        if self._size == 1:
            return bool(self._data[0])
        raise ValueError("truth value of array with more than one element is ambiguous")

    def __float__(self):
        if self._size == 1:
            return float(self._data[0])
        raise TypeError("only length-1 arrays can be converted to scalars")

    def __int__(self):
        if self._size == 1:
            return int(self._data[0])
        raise TypeError("only length-1 arrays can be converted to scalars")

    def reshape(self, *shape):
        if len(shape) == 1 and isinstance(shape[0], (tuple, list)):
            shape = tuple(shape[0])
        result = ndarray(shape, self.dtype)
        result._data = list(self._data)
        return result

    def flatten(self):
        result = ndarray((self._size,), self.dtype)
        result._data = list(self._data)
        return result

    def ravel(self):
        return self.flatten()

    def copy(self):
        result = ndarray(self.shape, self.dtype)
        result._data = list(self._data)
        return result

    def tolist(self):
        return list(self._data)

    def astype(self, dtype):
        result = ndarray(self.shape, dtype)
        result._data = list(self._data)
        return result

    def sum(self, axis=None):
        return _builtin_sum(self._data)

    def mean(self, axis=None):
        return _builtin_sum(self._data) / len(self._data) if self._data else 0.0

    def max(self, axis=None):
        return _builtin_max(self._data) if self._data else 0

    def min(self, axis=None):
        return _builtin_min(self._data) if self._data else 0

    def std(self, axis=None, ddof=0):
        m = self.mean()
        n = len(self._data)
        if n <= ddof:
            return nan
        return (_builtin_sum((x - m) ** 2 for x in self._data) / (n - ddof)) ** 0.5

    def var(self, axis=None, ddof=0):
        m = self.mean()
        n = len(self._data)
        if n <= ddof:
            return nan
        return _builtin_sum((x - m) ** 2 for x in self._data) / (n - ddof)

    def transpose(self, *axes):
        return self.copy()

    def squeeze(self, axis=None):
        new_shape = tuple(s for s in self.shape if s != 1)
        if not new_shape:
            new_shape = (1,)
        return self.reshape(new_shape)

    def clip(self, a_min=None, a_max=None):
        result = ndarray(self.shape, self.dtype)
        result._data = [
            max(a_min, min(a_max, x)) if a_min is not None and a_max is not None
            else (max(a_min, x) if a_min is not None else (min(a_max, x) if a_max is not None else x))
            for x in self._data
        ]
        return result

    def argmax(self, axis=None):
        return self._data.index(max(self._data)) if self._data else 0

    def argmin(self, axis=None):
        return self._data.index(min(self._data)) if self._data else 0


def _binop(a, b, op):
    if isinstance(b, ndarray):
        result = ndarray(a.shape, a.dtype)
        result._data = [op(x, y) for x, y in zip(a._data, b._data)]
    else:
        result = ndarray(a.shape, a.dtype)
        result._data = [op(x, b) for x in a._data]
    return result


# ---------------------------------------------------------------------------
# Array creation
# ---------------------------------------------------------------------------

def array(obj, dtype=None):
    if isinstance(obj, ndarray):
        return obj.copy()
    if isinstance(obj, (list, tuple)):
        flat = _flatten_nested(obj)
        shape = _infer_shape(obj)
        result = ndarray(shape, dtype)
        result._data = [float(x) if dtype is None else x for x in flat]
        return result
    result = ndarray((1,), dtype)
    result._data = [obj]
    return result


def _flatten_nested(obj):
    if isinstance(obj, (list, tuple)):
        result = []
        for item in obj:
            result.extend(_flatten_nested(item))
        return result
    return [obj]


def _infer_shape(obj):
    if isinstance(obj, (list, tuple)):
        if not obj:
            return (0,)
        inner = _infer_shape(obj[0])
        return (len(obj),) + inner
    return ()


def asarray(a, dtype=None):
    if isinstance(a, ndarray):
        return a
    return array(a, dtype)


def zeros(shape, dtype=None):
    if isinstance(shape, int):
        shape = (shape,)
    result = ndarray(shape, dtype)
    return result


def ones(shape, dtype=None):
    if isinstance(shape, int):
        shape = (shape,)
    result = ndarray(shape, dtype)
    result._data = [1] * result._size
    return result


def empty(shape, dtype=None):
    return zeros(shape, dtype)


def full(shape, fill_value, dtype=None):
    if isinstance(shape, int):
        shape = (shape,)
    result = ndarray(shape, dtype)
    result._data = [fill_value] * result._size
    return result


def arange(start, stop=None, step=1, dtype=None):
    if stop is None:
        start, stop = 0, start
    data = []
    v = start
    while (step > 0 and v < stop) or (step < 0 and v > stop):
        data.append(v)
        v += step
    result = ndarray((len(data),), dtype)
    result._data = data
    return result


def linspace(start, stop, num=50, endpoint=True, dtype=None):
    if num <= 0:
        return ndarray((0,), dtype)
    if num == 1:
        result = ndarray((1,), dtype)
        result._data = [float(start)]
        return result
    if endpoint:
        step = (stop - start) / (num - 1)
    else:
        step = (stop - start) / num
    data = [start + i * step for i in range(num)]
    result = ndarray((num,), dtype)
    result._data = data
    return result


def eye(N, M=None, k=0, dtype=None):
    if M is None:
        M = N
    result = ndarray((N, M), dtype)
    for i in range(N):
        j = i + k
        if 0 <= j < M:
            result._data[i * M + j] = 1
    return result


def identity(n, dtype=None):
    return eye(n, dtype=dtype)


def diag(v, k=0):
    if isinstance(v, ndarray) and v.ndim == 1:
        n = v._size + abs(k)
        result = zeros((n, n))
        for i in range(v._size):
            row = i if k >= 0 else i - k
            col = i + k if k >= 0 else i
            if 0 <= row < n and 0 <= col < n:
                result._data[row * n + col] = v._data[i]
        return result
    return array(v)


def concatenate(arrays, axis=0):
    data = []
    for a in arrays:
        a = asarray(a)
        data.extend(a._data)
    return array(data)


def stack(arrays, axis=0):
    return concatenate(arrays, axis=axis)


def hstack(arrays):
    return concatenate(arrays)


def vstack(arrays):
    return concatenate(arrays)


def where(condition, x=None, y=None):
    cond = asarray(condition)
    if x is None:
        indices = [i for i, v in enumerate(cond._data) if v]
        return (array(indices),)
    xa = asarray(x)
    ya = asarray(y)
    result = ndarray(cond.shape, xa.dtype)
    result._data = [xa._data[i] if cond._data[i] else ya._data[i] for i in range(cond._size)]
    return result


def isnan(x):
    a = asarray(x)
    result = ndarray(a.shape, bool_)
    result._data = [_math.isnan(v) if isinstance(v, float) else False for v in a._data]
    return result


def isinf(x):
    a = asarray(x)
    result = ndarray(a.shape, bool_)
    result._data = [_math.isinf(v) if isinstance(v, float) else False for v in a._data]
    return result


def isfinite(x):
    a = asarray(x)
    result = ndarray(a.shape, bool_)
    result._data = [_math.isfinite(v) if isinstance(v, float) else True for v in a._data]
    return result


# ---------------------------------------------------------------------------
# Reductions
# ---------------------------------------------------------------------------

def sum(a, axis=None):
    a = asarray(a)
    return a.sum(axis)

def mean(a, axis=None):
    a = asarray(a)
    return a.mean(axis)

def std(a, axis=None, ddof=0):
    a = asarray(a)
    return a.std(axis, ddof=ddof)

def var(a, axis=None, ddof=0):
    a = asarray(a)
    return a.var(axis, ddof=ddof)

def max(a, axis=None):
    a = asarray(a)
    return a.max(axis)

def min(a, axis=None):
    a = asarray(a)
    return a.min(axis)

def abs(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_builtin_abs(x) for x in a._data]
    return result

def sqrt(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.sqrt(x) if x >= 0 else nan for x in a._data]
    return result

def log(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.log(x) if x > 0 else nan for x in a._data]
    return result

def exp(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.exp(x) for x in a._data]
    return result

def sin(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.sin(x) for x in a._data]
    return result

def cos(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.cos(x) for x in a._data]
    return result

def ceil(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.ceil(x) for x in a._data]
    return result

def floor(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.floor(x) for x in a._data]
    return result

def clip(a, a_min, a_max):
    a = asarray(a)
    return a.clip(a_min, a_max)

def unique(a):
    a = asarray(a)
    seen = []
    for v in a._data:
        if v not in seen:
            seen.append(v)
    return array(sorted(seen))

def argsort(a):
    a = asarray(a)
    indices = sorted(range(len(a._data)), key=lambda i: a._data[i])
    return array(indices)

def sort(a, axis=-1):
    a = asarray(a)
    result = a.copy()
    result._data.sort()
    return result

def median(a, axis=None):
    a = asarray(a)
    s = sorted(a._data)
    n = len(s)
    if n == 0:
        return nan
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0

def percentile(a, q, axis=None):
    a = asarray(a)
    s = sorted(a._data)
    n = len(s)
    if n == 0:
        return nan
    idx = (q / 100.0) * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return float(s[-1])
    frac = idx - lo
    return s[lo] * (1 - frac) + s[hi] * frac

def atleast_1d(*arys):
    results = []
    for a in arys:
        a = asarray(a)
        if a.ndim == 0:
            a = a.reshape((1,))
        results.append(a)
    return results[0] if len(results) == 1 else results

def atleast_2d(*arys):
    results = []
    for a in arys:
        a = asarray(a)
        if a.ndim == 0:
            a = a.reshape((1, 1))
        elif a.ndim == 1:
            a = a.reshape((1, a.size))
        results.append(a)
    return results[0] if len(results) == 1 else results

def where(condition, x=None, y=None):
    condition = asarray(condition)
    if x is None and y is None:
        indices = [i for i, v in enumerate(condition._data) if v]
        return (array(indices),)
    x = asarray(x)
    y = asarray(y)
    result = ndarray(condition.shape, x.dtype)
    result._data = [xv if c else yv for c, xv, yv in zip(condition._data, x._data, y._data)]
    return result

def concatenate(arrays, axis=0):
    data = []
    for a in arrays:
        a = asarray(a)
        data.extend(a._data)
    return array(data)

def stack(arrays, axis=0):
    return concatenate(arrays, axis)

def vstack(tup):
    return concatenate(tup, 0)

def hstack(tup):
    return concatenate(tup, 0)

def column_stack(tup):
    return concatenate(tup, 0)

def isnan(a):
    a = asarray(a)
    result = ndarray(a.shape, bool_)
    result._data = [_math.isnan(x) if isinstance(x, float) else False for x in a._data]
    return result

def isinf(a):
    a = asarray(a)
    result = ndarray(a.shape, bool_)
    result._data = [_math.isinf(x) if isinstance(x, float) else False for x in a._data]
    return result

def isfinite(a):
    a = asarray(a)
    result = ndarray(a.shape, bool_)
    result._data = [_math.isfinite(x) if isinstance(x, float) else True for x in a._data]
    return result

def allclose(a, b, rtol=1e-5, atol=1e-8):
    a = asarray(a)
    b = asarray(b)
    for x, y in zip(a._data, b._data):
        if _builtin_abs(x - y) > atol + rtol * _builtin_abs(y):
            return False
    return True

def dot(a, b):
    a = asarray(a)
    b = asarray(b)
    if a.ndim == 1 and b.ndim == 1:
        return _builtin_sum(x * y for x, y in zip(a._data, b._data))
    return a

def meshgrid(*xi, indexing="xy"):
    return tuple(asarray(x) for x in xi)

def tile(A, reps):
    a = asarray(A)
    if isinstance(reps, int):
        reps = (reps,)
    data = a._data * reps[0]
    return array(data)

def repeat(a, repeats, axis=None):
    a = asarray(a)
    data = []
    for v in a._data:
        data.extend([v] * repeats)
    return array(data)

def round(a, decimals=0):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_builtins.round(x, decimals) for x in a._data]
    return result

around = round

def reshape(a, newshape):
    a = asarray(a)
    return a.reshape(newshape)

def squeeze(a, axis=None):
    a = asarray(a)
    return a.squeeze(axis)

def expand_dims(a, axis):
    a = asarray(a)
    new_shape = list(a.shape)
    new_shape.insert(axis, 1)
    return a.reshape(tuple(new_shape))

def ravel(a):
    a = asarray(a)
    return a.ravel()

def flatten(a):
    a = asarray(a)
    return a.flatten()

def transpose(a, axes=None):
    a = asarray(a)
    return a.transpose()

def swapaxes(a, axis1, axis2):
    return asarray(a)

def moveaxis(a, source, destination):
    return asarray(a)

def take(a, indices, axis=None):
    a = asarray(a)
    indices = asarray(indices)
    result_data = [a._data[int(i)] for i in indices._data]
    return array(result_data)

def any(a, axis=None):
    a = asarray(a)
    return _builtins.any(a._data)

def all(a, axis=None):
    a = asarray(a)
    return _builtins.all(a._data)

def prod(a, axis=None):
    a = asarray(a)
    result = 1
    for x in a._data:
        result *= x
    return result

def cumsum(a, axis=None):
    a = asarray(a)
    data = []
    s = 0
    for x in a._data:
        s += x
        data.append(s)
    return array(data)

def diff(a, n=1, axis=-1):
    a = asarray(a)
    data = a._data
    for _ in range(n):
        data = [data[i+1] - data[i] for i in range(len(data)-1)]
    return array(data)

def searchsorted(a, v, side='left'):
    a = asarray(a)
    v_scalar = v if not isinstance(v, ndarray) else v._data[0]
    import bisect
    if side == 'left':
        return bisect.bisect_left(a._data, v_scalar)
    return bisect.bisect_right(a._data, v_scalar)

def digitize(x, bins, right=False):
    x = asarray(x)
    bins = asarray(bins)
    result = []
    for v in x._data:
        idx = 0
        for b in bins._data:
            if v >= b:
                idx += 1
            else:
                break
        result.append(idx)
    return array(result)

def histogram(a, bins=10, range=None):
    a = asarray(a)
    if isinstance(bins, int):
        mn = _builtin_min(a._data) if a._data else 0
        mx = _builtin_max(a._data) if a._data else 1
        if mn == mx:
            mx = mn + 1
        step = (mx - mn) / bins
        bin_edges = [mn + i * step for i in _builtins.range(bins + 1)]
    else:
        bin_edges = list(bins) if hasattr(bins, '__iter__') else [bins]
    counts = [0] * (_builtin_max(len(bin_edges) - 1, 0))
    return array(counts), array(bin_edges)

def histogram2d(x, y, bins=10, range=None):
    return array([]), array([]), array([])

def histogram_bin_edges(a, bins=10, range=None):
    a = asarray(a)
    if isinstance(bins, int):
        mn = _builtin_min(a._data) if a._data else 0
        mx = _builtin_max(a._data) if a._data else 1
        if mn == mx:
            mx = mn + 1
        step = (mx - mn) / bins
        return array([mn + i * step for i in _builtins.range(bins + 1)])
    return asarray(bins)

def append(arr, values, axis=None):
    arr = asarray(arr)
    values = asarray(values)
    data = list(arr._data) + list(values._data)
    return array(data)

def insert(arr, obj, values, axis=None):
    arr = asarray(arr)
    data = list(arr._data)
    if isinstance(values, ndarray):
        values = values._data
    elif not isinstance(values, (list, tuple)):
        values = [values]
    if isinstance(obj, int):
        for i, v in enumerate(values):
            data.insert(obj + i, v)
    return array(data)

def interp(x, xp, fp):
    x = asarray(x)
    xp = asarray(xp)
    fp = asarray(fp)
    result = []
    for xi in x._data:
        if xi <= xp._data[0]:
            result.append(fp._data[0])
        elif xi >= xp._data[-1]:
            result.append(fp._data[-1])
        else:
            for j in _builtins.range(len(xp._data) - 1):
                if xp._data[j] <= xi <= xp._data[j+1]:
                    t = (xi - xp._data[j]) / (xp._data[j+1] - xp._data[j])
                    result.append(fp._data[j] + t * (fp._data[j+1] - fp._data[j]))
                    break
    return array(result)

def fromiter(iterable, dtype=None, count=-1):
    data = list(iterable) if count < 0 else list(_builtins.zip(_builtins.range(count), iterable))
    if count >= 0:
        data = [v for _, v in data]
    return array(data, dtype)

def sign(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [(1 if x > 0 else (-1 if x < 0 else 0)) for x in a._data]
    return result

def power(a, p):
    a = asarray(a)
    if isinstance(p, ndarray):
        result = ndarray(a.shape, a.dtype)
        result._data = [x ** y for x, y in zip(a._data, p._data)]
    else:
        result = ndarray(a.shape, a.dtype)
        result._data = [x ** p for x in a._data]
    return result

def square(a):
    return power(a, 2)

def log10(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.log10(x) if x > 0 else nan for x in a._data]
    return result

def log2(a):
    a = asarray(a)
    result = ndarray(a.shape, a.dtype)
    result._data = [_math.log2(x) if x > 0 else nan for x in a._data]
    return result

def arctan2(y, x):
    y = asarray(y)
    x = asarray(x)
    result = ndarray(y.shape, y.dtype)
    result._data = [_math.atan2(yi, xi) for yi, xi in zip(y._data, x._data)]
    return result

def average(a, axis=None, weights=None):
    a = asarray(a)
    if weights is None:
        return a.mean()
    weights = asarray(weights)
    wsum = _builtin_sum(w * v for w, v in zip(weights._data, a._data))
    return wsum / _builtin_sum(weights._data)

def cov(m, y=None, rowvar=True):
    return array([[1.0]])

def cumprod(a, axis=None):
    a = asarray(a)
    data = []
    p = 1
    for x in a._data:
        p *= x
        data.append(p)
    return array(data)

def outer(a, b):
    a = asarray(a)
    b = asarray(b)
    data = [x * y for x in a._data for y in b._data]
    result = ndarray((a.size, b.size), a.dtype)
    result._data = data
    return result

def maximum(a, b):
    a = asarray(a)
    b = asarray(b)
    result = ndarray(a.shape, a.dtype)
    result._data = [_builtin_max(x, y) for x, y in zip(a._data, b._data)]
    return result

def minimum(a, b):
    a = asarray(a)
    b = asarray(b)
    result = ndarray(a.shape, a.dtype)
    result._data = [_builtin_min(x, y) for x, y in zip(a._data, b._data)]
    return result

def multiply(a, b):
    return asarray(a) * asarray(b)

def divide(a, b):
    return asarray(a) / asarray(b)

def subtract(a, b):
    return asarray(a) - asarray(b)

def add(a, b):
    return asarray(a) + asarray(b)

def nanmax(a, axis=None):
    a = asarray(a)
    vals = [x for x in a._data if not (_builtins.isinstance(x, float) and _math.isnan(x))]
    return _builtin_max(vals) if vals else nan

def nanmin(a, axis=None):
    a = asarray(a)
    vals = [x for x in a._data if not (_builtins.isinstance(x, float) and _math.isnan(x))]
    return _builtin_min(vals) if vals else nan

def nanpercentile(a, q, axis=None):
    a = asarray(a)
    vals = [x for x in a._data if not (_builtins.isinstance(x, float) and _math.isnan(x))]
    return percentile(array(vals), q, axis)

def nan_to_num(x, nan=0.0, posinf=None, neginf=None):
    x = asarray(x)
    result = ndarray(x.shape, x.dtype)
    result._data = []
    for v in x._data:
        if isinstance(v, float) and _math.isnan(v):
            result._data.append(nan)
        elif isinstance(v, float) and _math.isinf(v):
            result._data.append(posinf if v > 0 else neginf if neginf is not None else 0.0)
        else:
            result._data.append(v)
    return result

def zeros_like(a, dtype=None):
    a = asarray(a)
    return zeros(a.shape, dtype or a.dtype)

def ones_like(a, dtype=None):
    a = asarray(a)
    return ones(a.shape, dtype or a.dtype)

def empty_like(a, dtype=None):
    return zeros_like(a, dtype)

def full_like(a, fill_value, dtype=None):
    a = asarray(a)
    return full(a.shape, fill_value, dtype or a.dtype)

def polyfit(x, y, deg):
    return array([0.0] * (deg + 1))

def polyval(p, x):
    p = asarray(p)
    x = asarray(x)
    result = ndarray(x.shape, x.dtype)
    result._data = [0.0] * x.size
    return result

def ptp(a, axis=None):
    a = asarray(a)
    return a.max() - a.min()

def shape(a):
    a = asarray(a)
    return a.shape

def ndim(a):
    a = asarray(a)
    return a.ndim

def split(ary, indices_or_sections, axis=0):
    ary = asarray(ary)
    if isinstance(indices_or_sections, int):
        n = indices_or_sections
        sz = len(ary._data) // n
        return [array(ary._data[i*sz:(i+1)*sz]) for i in _builtins.range(n)]
    indices = list(indices_or_sections)
    result = []
    prev = 0
    for idx in indices:
        result.append(array(ary._data[prev:idx]))
        prev = idx
    result.append(array(ary._data[prev:]))
    return result

def compress(condition, a, axis=None):
    a = asarray(a)
    condition = asarray(condition)
    data = [v for v, c in zip(a._data, condition._data) if c]
    return array(data)

def isin(element, test_elements):
    element = asarray(element)
    test = asarray(test_elements)
    test_set = set(test._data)
    result = ndarray(element.shape, bool_)
    result._data = [v in test_set for v in element._data]
    return result

def isneginf(a):
    a = asarray(a)
    result = ndarray(a.shape, bool_)
    result._data = [isinstance(x, float) and _math.isinf(x) and x < 0 for x in a._data]
    return result

def isposinf(a):
    a = asarray(a)
    result = ndarray(a.shape, bool_)
    result._data = [isinstance(x, float) and _math.isinf(x) and x > 0 for x in a._data]
    return result

def isscalar(val):
    return isinstance(val, (int, float, complex, str, bytes, bool, type(None)))

def ndenumerate(a):
    a = asarray(a)
    for i, v in enumerate(a._data):
        yield (i,), v

def indices(dimensions):
    return tuple(arange(d) for d in dimensions)

def common_type(*arrays):
    return float

def tril_indices_from(arr, k=0):
    n = arr.shape[0] if arr.shape else 0
    rows, cols = [], []
    for i in _builtins.range(n):
        for j in _builtins.range(i + 1 + k):
            if j < n:
                rows.append(i)
                cols.append(j)
    return array(rows), array(cols)

def triu_indices_from(arr, k=0):
    n = arr.shape[0] if arr.shape else 0
    rows, cols = [], []
    for i in _builtins.range(n):
        for j in _builtins.range(i + k, n):
            rows.append(i)
            cols.append(j)
    return array(rows), array(cols)

class vectorize:
    def __init__(self, pyfunc, otypes=None, excluded=None, signature=None):
        self.pyfunc = pyfunc
    def __call__(self, *args):
        a = asarray(args[0])
        result = ndarray(a.shape, a.dtype)
        result._data = [self.pyfunc(x) for x in a._data]
        return result

class errstate:
    def __init__(self, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

class finfo:
    def __init__(self, dtype=float):
        self.eps = 2.220446049250313e-16
        self.max = 1.7976931348623157e+308
        self.min = 2.2250738585072014e-308
        self.tiny = self.min
        self.resolution = 1e-15

class iinfo:
    def __init__(self, dtype=int):
        self.max = 2**31 - 1
        self.min = -2**31
        self.bits = 32

class datetime64:
    def __init__(self, val=None, unit=None):
        self._val = val
    def astype(self, dtype):
        return self._val

class timedelta64:
    def __init__(self, val=None, unit=None):
        self._val = val

class ufunc:
    """Stub ufunc class."""
    pass

intp = dtype("int32")

class _ConcatenatorClass:
    """Stub for np.c_ and np.r_ index tricks."""
    def __getitem__(self, key):
        if isinstance(key, tuple):
            arrays = [asarray(k) if not isinstance(k, slice) else arange(0) for k in key]
            return concatenate(arrays)
        return asarray(key)

c_ = _ConcatenatorClass()
r_ = _ConcatenatorClass()

class _MaskedArrayModule:
    """Stub for numpy.ma submodule."""
    class MaskedArray(ndarray):
        pass
    masked_invalid = staticmethod(lambda a: asarray(a))
    masked_where = staticmethod(lambda cond, a: asarray(a))
    array = staticmethod(lambda a, mask=None: asarray(a))
    is_masked = staticmethod(lambda a: False)

ma = _MaskedArrayModule()

class _TestingModule:
    """Stub for numpy.testing submodule."""
    @staticmethod
    def assert_array_equal(x, y):
        pass
    @staticmethod
    def assert_array_almost_equal(x, y, decimal=6):
        pass
    @staticmethod
    def assert_allclose(actual, desired, rtol=1e-7, atol=0):
        pass

testing = _TestingModule()

class _TypingModule:
    """Stub for numpy.typing submodule."""
    NDArray = ndarray
    ArrayLike = object

typing = _TypingModule()

class _RandomModule:
    """Stub numpy.random module."""
    def seed(self, s=None):
        import random as _r
        _r.seed(s)

    def rand(self, *shape):
        import random as _r
        n = 1
        for s in shape:
            n *= s
        result = ndarray(shape if shape else (1,))
        result._data = [_r.random() for _ in range(n)]
        return result

    def randn(self, *shape):
        import random as _r
        n = 1
        for s in shape:
            n *= s
        result = ndarray(shape if shape else (1,))
        result._data = [_r.gauss(0, 1) for _ in range(n)]
        return result

    def randint(self, low, high=None, size=None):
        import random as _r
        if high is None:
            low, high = 0, low
        if size is None:
            return _r.randint(low, high - 1)
        if isinstance(size, int):
            size = (size,)
        n = 1
        for s in size:
            n *= s
        result = ndarray(size)
        result._data = [_r.randint(low, high - 1) for _ in range(n)]
        return result

    def choice(self, a, size=None, replace=True, p=None):
        import random as _r
        if isinstance(a, int):
            a = list(range(a))
        elif isinstance(a, ndarray):
            a = a._data
        if size is None:
            return _r.choice(a)
        if isinstance(size, int):
            size = (size,)
        n = 1
        for s in size:
            n *= s
        result = ndarray(size)
        result._data = [_r.choice(a) for _ in range(n)]
        return result

    def uniform(self, low=0.0, high=1.0, size=None):
        import random as _r
        if size is None:
            return _r.uniform(low, high)
        if isinstance(size, int):
            size = (size,)
        n = 1
        for s in size:
            n *= s
        result = ndarray(size)
        result._data = [_r.uniform(low, high) for _ in range(n)]
        return result

    def normal(self, loc=0.0, scale=1.0, size=None):
        import random as _r
        if size is None:
            return _r.gauss(loc, scale)
        if isinstance(size, int):
            size = (size,)
        n = 1
        for s in size:
            n *= s
        result = ndarray(size)
        result._data = [_r.gauss(loc, scale) for _ in range(n)]
        return result

    def shuffle(self, x):
        import random as _r
        if isinstance(x, ndarray):
            _r.shuffle(x._data)
        elif isinstance(x, list):
            _r.shuffle(x)

    def permutation(self, x):
        import random as _r
        if isinstance(x, int):
            data = list(range(x))
        elif isinstance(x, ndarray):
            data = list(x._data)
        else:
            data = list(x)
        _r.shuffle(data)
        return array(data)

    class RandomState:
        def __init__(self, seed=None):
            import random as _r
            self._rng = _r.Random(seed)

        def rand(self, *shape):
            n = 1
            for s in shape:
                n *= s
            result = ndarray(shape if shape else (1,))
            result._data = [self._rng.random() for _ in range(n)]
            return result


random = _RandomModule()


class _LinalgModule:
    """Stub numpy.linalg module."""
    def norm(self, x, ord=None, axis=None):
        a = asarray(x)
        return _math.sqrt(_builtin_sum(v * v for v in a._data))

    def det(self, a):
        return 0.0

    def inv(self, a):
        return asarray(a)

    def eig(self, a):
        a = asarray(a)
        return (zeros(a.shape[0] if a.shape else 0), eye(a.shape[0] if a.shape else 0))

    def solve(self, a, b):
        return asarray(b)

    class LinAlgError(Exception):
        pass

linalg = _LinalgModule()


# ---------------------------------------------------------------------------
# Type checking helpers used by downstream packages
# ---------------------------------------------------------------------------

def issubdtype(arg1, arg2):
    return False

def result_type(*arrays_and_dtypes):
    return float64

def promote_types(type1, type2):
    return float64

def can_cast(from_, to, casting="safe"):
    return True

# Compat
string_ = str_
intp = int64
uintp = uint64
double = float64
single = float32
csingle = complex64
cdouble = complex128
longdouble = float64
clongdouble = complex128
