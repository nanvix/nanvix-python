"""Nanvix pandas.api.types stub."""


class CategoricalDtype:
    def __init__(self, categories=None, ordered=False):
        self.categories = categories
        self.ordered = ordered


def is_numeric_dtype(arr_or_dtype):
    return False


def is_string_dtype(arr_or_dtype):
    return False


def is_categorical_dtype(arr_or_dtype):
    return False


def is_bool_dtype(arr_or_dtype):
    return False


def is_integer_dtype(arr_or_dtype):
    return False


def is_float_dtype(arr_or_dtype):
    return False


def is_object_dtype(arr_or_dtype):
    return True


def is_datetime64_any_dtype(arr_or_dtype):
    return False


def is_list_like(obj):
    return isinstance(obj, (list, tuple, set, frozenset))


def is_scalar(val):
    return isinstance(val, (int, float, complex, str, bytes, bool, type(None)))
