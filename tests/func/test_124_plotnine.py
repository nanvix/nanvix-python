"""Test: plotnine"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import plotnine

    assert plotnine.__version__

    print("plotnine: PASS")
except ImportError as e:
    print(f"plotnine: SKIP ({e})")
except Exception as e:
    print(f"plotnine: FAIL: {e}")
    sys.exit(1)
