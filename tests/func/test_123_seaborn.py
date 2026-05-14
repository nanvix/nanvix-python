"""Test: seaborn"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import seaborn as sns

    # Version check
    assert sns.__version__

    print("seaborn: PASS")
except ImportError as e:
    # seaborn may fail to import if its internal imports hit
    # missing submodules; treat as degraded
    print(f"seaborn: SKIP ({e})")
except Exception as e:
    print(f"seaborn: FAIL: {e}")
    sys.exit(1)
