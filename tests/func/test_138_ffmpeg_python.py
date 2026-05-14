"""Test: ffmpeg-python (import-only — no ffmpeg runtime on Nanvix)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import ffmpeg

    # Basic API surface check
    assert hasattr(ffmpeg, 'input')
    assert hasattr(ffmpeg, 'output')

    print("ffmpeg-python: PASS")
except ImportError as e:
    print(f"ffmpeg-python: SKIP ({e})")
except Exception as e:
    print(f"ffmpeg-python: FAIL: {e}")
    sys.exit(1)
