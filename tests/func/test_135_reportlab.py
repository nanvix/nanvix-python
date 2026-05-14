"""Test: reportlab"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch

    assert letter == (612.0, 792.0)
    assert inch == 72

    print("reportlab: PASS")
except ImportError as e:
    print(f"reportlab: SKIP ({e})")
except Exception as e:
    print(f"reportlab: FAIL: {e}")
    sys.exit(1)
