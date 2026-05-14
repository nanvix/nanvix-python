"""Test: altair"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import altair as alt

    assert alt.__version__

    print("altair: PASS")
except ImportError as e:
    print(f"altair: SKIP ({e})")
except Exception as e:
    print(f"altair: FAIL: {e}")
    sys.exit(1)
