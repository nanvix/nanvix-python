"""Test: psutil (shim)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import psutil

    # CPU
    count = psutil.cpu_count()
    assert isinstance(count, int) and count >= 1
    pct = psutil.cpu_percent()
    assert isinstance(pct, float)

    # Memory
    mem = psutil.virtual_memory()
    assert mem.total > 0
    assert 0 <= mem.percent <= 100

    # Disk
    disk = psutil.disk_usage("/")
    assert disk.total > 0

    # Process
    p = psutil.Process(1)
    assert p.name() == "nanvix"
    assert p.is_running()

    # Version
    assert psutil.__version__

    print("psutil: PASS")
except Exception as e:
    print(f"psutil: FAIL: {e}")
    sys.exit(1)
