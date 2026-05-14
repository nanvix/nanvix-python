"""Nanvix matplotlib.cbook stub — callback registry and utility helpers."""

from __future__ import annotations
import itertools


class CallbackRegistry:
    """Minimal callback registry stub."""
    def __init__(self, exception_handler=None, *, signals=None):
        self.callbacks = {}
        self._exception_handler = exception_handler

    def connect(self, signal, func):
        self.callbacks.setdefault(signal, []).append(func)
        return len(self.callbacks[signal]) - 1

    def disconnect(self, cid):
        pass

    def process(self, s, *args, **kwargs):
        pass


def flatten(seq, scalarp=None):
    for item in seq:
        if hasattr(item, '__iter__') and not isinstance(item, str):
            yield from flatten(item, scalarp)
        else:
            yield item


def is_scalar_or_string(val):
    return isinstance(val, str) or not hasattr(val, '__iter__')


def sanitize_sequence(data):
    if isinstance(data, dict):
        return list(data.values())
    if hasattr(data, 'tolist'):
        return data.tolist()
    return list(data)


def normalize_kwargs(kw, alias_mapping=None):
    return dict(kw) if kw else {}


def silent_list(type_str, seq):
    return list(seq)


class maxdict(dict):
    def __init__(self, maxsize):
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key, value):
        if len(self) >= self.maxsize:
            try:
                del self[next(iter(self))]
            except (StopIteration, KeyError):
                pass
        super().__setitem__(key, value)
