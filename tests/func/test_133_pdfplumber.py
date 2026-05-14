"""Test: pdfplumber"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pdfplumber

    assert pdfplumber.__version__

    print("pdfplumber: PASS")
except ImportError as e:
    print(f"pdfplumber: SKIP ({e})")
except Exception as e:
    print(f"pdfplumber: FAIL: {e}")
    sys.exit(1)
