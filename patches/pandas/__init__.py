"""Nanvix pandas shim — pure-Python DataFrame/Series stub.

Provides the minimum pandas API surface needed by downstream packages
(seaborn, plotnine, altair) for import and basic data construction.
"""

__version__ = "2.2.2"

from collections import OrderedDict


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

class Series:
    """Minimal Series stub backed by a Python list."""

    def __init__(self, data=None, index=None, dtype=None, name=None):
        if data is None:
            data = []
        if isinstance(data, Series):
            data = list(data._data)
        elif isinstance(data, dict):
            if index is None:
                index = list(data.keys())
            data = list(data.values())
        elif hasattr(data, 'tolist'):
            data = data.tolist()
        self._data = list(data)
        self.index = index if index is not None else list(range(len(self._data)))
        self.dtype = dtype
        self.name = name

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"Series({self._data})"

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._data[key]
        return self._data[0] if self._data else None

    def __setitem__(self, key, value):
        if isinstance(key, int):
            self._data[key] = value

    @property
    def values(self):
        try:
            import numpy as np
            return np.array(self._data)
        except ImportError:
            return self._data

    @property
    def shape(self):
        return (len(self._data),)

    @property
    def size(self):
        return len(self._data)

    @property
    def empty(self):
        return len(self._data) == 0

    def tolist(self):
        return list(self._data)

    def to_dict(self):
        return dict(zip(self.index, self._data))

    def sum(self):
        return sum(self._data)

    def mean(self):
        return sum(self._data) / len(self._data) if self._data else 0.0

    def max(self):
        return max(self._data) if self._data else None

    def min(self):
        return min(self._data) if self._data else None

    def std(self, ddof=1):
        m = self.mean()
        n = len(self._data)
        if n <= ddof:
            return float('nan')
        return (sum((x - m) ** 2 for x in self._data) / (n - ddof)) ** 0.5

    def head(self, n=5):
        return Series(self._data[:n], name=self.name)

    def tail(self, n=5):
        return Series(self._data[-n:], name=self.name)

    def copy(self):
        return Series(list(self._data), index=list(self.index), dtype=self.dtype, name=self.name)

    def isna(self):
        return Series([x is None or (isinstance(x, float) and x != x) for x in self._data])

    def notna(self):
        return Series([not (x is None or (isinstance(x, float) and x != x)) for x in self._data])

    def fillna(self, value=0):
        data = [value if (x is None or (isinstance(x, float) and x != x)) else x for x in self._data]
        return Series(data, name=self.name)

    def dropna(self):
        data = [x for x in self._data if not (x is None or (isinstance(x, float) and x != x))]
        return Series(data, name=self.name)

    def unique(self):
        seen = []
        for v in self._data:
            if v not in seen:
                seen.append(v)
        return seen

    def nunique(self):
        return len(self.unique())

    def value_counts(self):
        counts = {}
        for v in self._data:
            counts[v] = counts.get(v, 0) + 1
        items = sorted(counts.items(), key=lambda x: -x[1])
        return Series([c for _, c in items], index=[k for k, _ in items])

    def apply(self, func):
        return Series([func(x) for x in self._data], name=self.name)

    def map(self, arg):
        if callable(arg):
            return self.apply(arg)
        if isinstance(arg, dict):
            return Series([arg.get(x, None) for x in self._data], name=self.name)
        return self

    def astype(self, dtype):
        return Series([dtype(x) for x in self._data], name=self.name)

    def sort_values(self, ascending=True):
        data = sorted(self._data, reverse=not ascending)
        return Series(data, name=self.name)

    def reset_index(self, drop=False):
        return self.copy()


# ---------------------------------------------------------------------------
# DataFrame
# ---------------------------------------------------------------------------

class DataFrame:
    """Minimal DataFrame stub backed by a dict of lists."""

    def __init__(self, data=None, index=None, columns=None):
        if data is None:
            data = {}
        if isinstance(data, dict):
            self._columns = OrderedDict()
            col_names = columns or list(data.keys())
            max_len = 0
            for k in col_names:
                vals = data.get(k, [])
                if isinstance(vals, Series):
                    vals = vals._data
                elif hasattr(vals, 'tolist'):
                    vals = vals.tolist()
                elif not isinstance(vals, list):
                    vals = list(vals)
                self._columns[k] = list(vals)
                max_len = max(max_len, len(self._columns[k]))
            # Pad short columns
            for k in self._columns:
                diff = max_len - len(self._columns[k])
                if diff > 0:
                    self._columns[k].extend([None] * diff)
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                keys = columns or list(data[0].keys())
                self._columns = OrderedDict((k, [row.get(k) for row in data]) for k in keys)
            else:
                if columns:
                    self._columns = OrderedDict()
                    for i, col in enumerate(columns):
                        self._columns[col] = [row[i] if isinstance(row, (list, tuple)) else row for row in data]
                else:
                    self._columns = OrderedDict({0: list(data)})
        elif isinstance(data, DataFrame):
            self._columns = OrderedDict((k, list(v)) for k, v in data._columns.items())
        else:
            self._columns = OrderedDict()

        n_rows = max((len(v) for v in self._columns.values()), default=0)
        self.index = index if index is not None else list(range(n_rows))

    @property
    def columns(self):
        return list(self._columns.keys())

    @columns.setter
    def columns(self, value):
        new_cols = OrderedDict()
        for old_k, new_k in zip(self._columns, value):
            new_cols[new_k] = self._columns[old_k]
        self._columns = new_cols

    @property
    def shape(self):
        n_rows = max((len(v) for v in self._columns.values()), default=0)
        return (n_rows, len(self._columns))

    @property
    def dtypes(self):
        return Series([type(v[0]).__name__ if v else 'object' for v in self._columns.values()],
                      index=list(self._columns.keys()))

    @property
    def values(self):
        rows = self.shape[0]
        result = []
        for i in range(rows):
            result.append([self._columns[k][i] for k in self._columns])
        return result

    @property
    def empty(self):
        return self.shape[0] == 0

    @property
    def size(self):
        return self.shape[0] * self.shape[1]

    @property
    def T(self):
        return self

    def __len__(self):
        return self.shape[0]

    def __repr__(self):
        return f"DataFrame({dict(self._columns)})"

    def __getitem__(self, key):
        if isinstance(key, str):
            if key in self._columns:
                return Series(self._columns[key], name=key)
            raise KeyError(key)
        if isinstance(key, list):
            return DataFrame({k: self._columns[k] for k in key if k in self._columns})
        if isinstance(key, int):
            return Series([self._columns[k][key] for k in self._columns],
                          index=list(self._columns.keys()))
        return self

    def __setitem__(self, key, value):
        if isinstance(value, Series):
            self._columns[key] = list(value._data)
        elif isinstance(value, list):
            self._columns[key] = list(value)
        else:
            n_rows = self.shape[0] or 1
            self._columns[key] = [value] * n_rows

    def __contains__(self, key):
        return key in self._columns

    def head(self, n=5):
        return DataFrame({k: v[:n] for k, v in self._columns.items()})

    def tail(self, n=5):
        return DataFrame({k: v[-n:] for k, v in self._columns.items()})

    def copy(self):
        return DataFrame({k: list(v) for k, v in self._columns.items()})

    def to_dict(self, orient='dict'):
        if orient == 'records':
            rows = self.shape[0]
            return [{k: self._columns[k][i] for k in self._columns} for i in range(rows)]
        return dict(self._columns)

    def to_csv(self, path=None, index=True, sep=',', header=True):
        lines = []
        if header:
            h = sep.join(str(k) for k in self._columns)
            if index:
                h = sep + h
            lines.append(h)
        for i in range(self.shape[0]):
            row = sep.join(str(self._columns[k][i]) for k in self._columns)
            if index:
                row = str(self.index[i]) + sep + row
            lines.append(row)
        content = '\n'.join(lines)
        if path:
            with open(path, 'w') as f:
                f.write(content)
        return content

    def describe(self):
        return self

    def info(self):
        print(f"DataFrame: {self.shape[0]} rows x {self.shape[1]} columns")

    def isna(self):
        return DataFrame({k: [x is None or (isinstance(x, float) and x != x) for x in v]
                          for k, v in self._columns.items()})

    def fillna(self, value=0):
        return DataFrame({k: [value if (x is None or (isinstance(x, float) and x != x)) else x for x in v]
                          for k, v in self._columns.items()})

    def dropna(self, how='any'):
        rows = self.shape[0]
        keep = []
        for i in range(rows):
            row_vals = [self._columns[k][i] for k in self._columns]
            has_na = any(x is None or (isinstance(x, float) and x != x) for x in row_vals)
            if how == 'any' and not has_na:
                keep.append(i)
            elif how == 'all' and not all(x is None or (isinstance(x, float) and x != x) for x in row_vals):
                keep.append(i)
        return DataFrame({k: [v[i] for i in keep] for k, v in self._columns.items()})

    def drop(self, labels=None, axis=0, columns=None):
        if columns:
            return DataFrame({k: v for k, v in self._columns.items() if k not in columns})
        return self.copy()

    def rename(self, columns=None, **kwargs):
        if columns:
            new_cols = OrderedDict()
            for k, v in self._columns.items():
                new_cols[columns.get(k, k)] = v
            return DataFrame(new_cols)
        return self.copy()

    def sort_values(self, by, ascending=True):
        if isinstance(by, str):
            by = [by]
        return self.copy()

    def groupby(self, by):
        return _GroupBy(self, by)

    def merge(self, other, on=None, how='inner', left_on=None, right_on=None):
        return self.copy()

    def apply(self, func, axis=0):
        if axis == 1:
            rows = self.shape[0]
            results = []
            for i in range(rows):
                row = Series({k: self._columns[k][i] for k in self._columns})
                results.append(func(row))
            return Series(results)
        return Series([func(Series(v)) for v in self._columns.values()],
                      index=list(self._columns.keys()))

    def iterrows(self):
        for i in range(self.shape[0]):
            row = Series({k: self._columns[k][i] for k in self._columns})
            yield self.index[i], row

    def reset_index(self, drop=False):
        return self.copy()

    def set_index(self, keys):
        return self.copy()

    def assign(self, **kwargs):
        result = self.copy()
        for k, v in kwargs.items():
            if callable(v):
                v = v(result)
            result[k] = v
        return result

    def melt(self, id_vars=None, value_vars=None, var_name='variable', value_name='value'):
        return self.copy()

    def pivot_table(self, values=None, index=None, columns=None, aggfunc='mean'):
        return self.copy()

    @property
    def loc(self):
        return self

    @property
    def iloc(self):
        return self


class _GroupBy:
    def __init__(self, df, by):
        self._df = df
        self._by = by

    def mean(self):
        return self._df.copy()

    def sum(self):
        return self._df.copy()

    def count(self):
        return self._df.copy()

    def agg(self, func):
        return self._df.copy()

    def apply(self, func):
        return self._df.copy()

    def __iter__(self):
        return iter([])


GroupBy = _GroupBy


# ---------------------------------------------------------------------------
# Top-level functions
# ---------------------------------------------------------------------------

def concat(objs, axis=0, ignore_index=False):
    if not objs:
        return DataFrame()
    if isinstance(objs[0], Series):
        data = []
        for s in objs:
            data.extend(s._data)
        return Series(data)
    result_cols = OrderedDict()
    for df in objs:
        for k, v in df._columns.items():
            if k not in result_cols:
                result_cols[k] = []
            result_cols[k].extend(v)
    return DataFrame(result_cols)


def merge(left, right, on=None, how='inner', left_on=None, right_on=None):
    return left.copy()


def read_csv(filepath_or_buffer, sep=',', header='infer', names=None, **kwargs):
    if isinstance(filepath_or_buffer, str):
        with open(filepath_or_buffer) as f:
            lines = f.readlines()
    else:
        lines = filepath_or_buffer.readlines()

    if not lines:
        return DataFrame()

    if header == 'infer' and names is None:
        col_names = [c.strip() for c in lines[0].split(sep)]
        data_lines = lines[1:]
    else:
        col_names = names or [str(i) for i in range(len(lines[0].split(sep)))]
        data_lines = lines

    cols = OrderedDict((k, []) for k in col_names)
    for line in data_lines:
        vals = [v.strip() for v in line.split(sep)]
        for i, k in enumerate(col_names):
            cols[k].append(vals[i] if i < len(vals) else None)

    return DataFrame(cols)


def read_json(path_or_buf, **kwargs):
    import json
    if isinstance(path_or_buf, str):
        with open(path_or_buf) as f:
            data = json.load(f)
    else:
        data = json.load(path_or_buf)
    if isinstance(data, list):
        return DataFrame(data)
    return DataFrame(data)


# Compat stubs
class Index(list):
    pass

class RangeIndex(Index):
    pass

class CategoricalDtype:
    def __init__(self, categories=None, ordered=False):
        self.categories = categories
        self.ordered = ordered

import datetime as _dt

class Timestamp(_dt.datetime):
    """Minimal Timestamp stub wrapping datetime."""
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(_dt.datetime.now().timestamp())

class Timedelta(_dt.timedelta):
    """Minimal Timedelta stub wrapping timedelta."""
    pass

NaT = None  # Not-a-Time sentinel


# API submodule stubs
class _ApiTypes:
    CategoricalDtype = CategoricalDtype
    is_numeric_dtype = staticmethod(lambda x: False)
    is_string_dtype = staticmethod(lambda x: False)
    is_categorical_dtype = staticmethod(lambda x: False)
    is_bool_dtype = staticmethod(lambda x: False)

class _Api:
    types = _ApiTypes()

api = _Api()

# Options stub
class _Options:
    def __init__(self):
        self._opts = {}
    def __call__(self, *args, **kwargs):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

def set_option(*args, **kwargs):
    pass

def get_option(key, default=None):
    return default

option_context = _Options()

# NA sentinel
NA = None

def isna(obj):
    if obj is None:
        return True
    if isinstance(obj, float):
        return obj != obj
    return False

def notna(obj):
    return not isna(obj)

def to_datetime(arg, **kwargs):
    return arg

def to_numeric(arg, **kwargs):
    if isinstance(arg, Series):
        return Series([float(x) if x is not None else float('nan') for x in arg._data])
    return float(arg) if arg is not None else float('nan')

def cut(x, bins, **kwargs):
    return x

def qcut(x, q, **kwargs):
    return x

def Categorical(values, categories=None, ordered=False):
    return Series(values)
