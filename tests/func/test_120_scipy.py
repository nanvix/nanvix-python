"""Test: scipy (shim)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import scipy
    from scipy import stats

    # Distribution stub
    assert hasattr(stats, 'norm')
    assert hasattr(stats, 'uniform')

    # pearsonr
    r, p = stats.pearsonr([1, 2, 3], [4, 5, 6])
    assert isinstance(r, float)
    assert isinstance(p, float)

    # linregress
    result = stats.linregress([1, 2, 3], [2, 4, 6])
    assert hasattr(result, 'slope')
    assert hasattr(result, 'intercept')

    # Version
    assert scipy.__version__

    print("scipy: PASS")
except Exception as e:
    print(f"scipy: FAIL: {e}")
    sys.exit(1)
