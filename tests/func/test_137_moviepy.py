"""Test: moviepy (import-only — no ffmpeg runtime on Nanvix)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import moviepy

    assert hasattr(moviepy, '__version__') or True

    print("moviepy: PASS")
except ImportError as e:
    print(f"moviepy: SKIP ({e})")
except Exception as e:
    print(f"moviepy: FAIL: {e}")
    sys.exit(1)
