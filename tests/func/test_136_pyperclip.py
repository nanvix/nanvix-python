"""Test: pyperclip (stub on Nanvix — no clipboard)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pyperclip

    # On Nanvix there is no clipboard backend, but the module should import
    assert hasattr(pyperclip, 'copy')
    assert hasattr(pyperclip, 'paste')

    print("pyperclip: PASS")
except ImportError as e:
    print(f"pyperclip: SKIP ({e})")
except Exception as e:
    print(f"pyperclip: FAIL: {e}")
    sys.exit(1)
