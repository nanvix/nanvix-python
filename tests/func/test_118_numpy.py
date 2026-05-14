"""Test: numpy native C extension"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    # Verify native builtin exists
    assert '_np_multiarray_umath' in sys.builtin_module_names

    import numpy as np

    # Array creation and basic ops
    a = np.array([1, 2, 3, 4, 5])
    assert a.shape == (5,)
    assert a.sum() == 15
    assert a.mean() == 3.0

    # Dtype and reshape
    b = np.zeros((2, 3), dtype=np.float64)
    assert b.shape == (2, 3)
    assert b.size == 6

    # Ufuncs
    c = np.arange(4)
    d = c * 2
    assert list(d) == [0, 2, 4, 6]

    # Dot product
    e = np.array([1.0, 2.0, 3.0])
    f = np.array([4.0, 5.0, 6.0])
    assert np.dot(e, f) == 32.0

    print("numpy: PASS")
except Exception as e:
    print(f"numpy: FAIL: {e}")
    sys.exit(1)
