"""Test: pytesseract (import-only — no tesseract runtime on Nanvix)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pytesseract

    assert hasattr(pytesseract, 'image_to_string')
    assert pytesseract.pytesseract  # submodule access

    print("pytesseract: PASS")
except ImportError as e:
    print(f"pytesseract: SKIP ({e})")
except Exception as e:
    print(f"pytesseract: FAIL: {e}")
    sys.exit(1)
