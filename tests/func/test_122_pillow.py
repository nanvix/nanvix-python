"""Test: Pillow (native C extensions)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    # Verify native C module is available
    import _pil_imaging
    assert hasattr(_pil_imaging, 'new')

    from PIL import Image

    # Image.new with native backend
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    assert img.size == (100, 100)
    assert img.mode == "RGB"

    # Verify version
    from PIL import __version__
    assert __version__

    print("Pillow: PASS")
except Exception as e:
    print(f"Pillow: FAIL: {e}")
    sys.exit(1)
