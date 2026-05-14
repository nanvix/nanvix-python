"""Test: matplotlib (shim)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import matplotlib
    import matplotlib.pyplot as plt

    # Backend
    matplotlib.use("agg")
    assert matplotlib.get_backend() == "agg"

    # Figure creation
    fig, ax = plt.subplots()
    assert fig is not None
    assert ax is not None

    # Plot operations (no-op rendering)
    ax.plot([1, 2, 3], [4, 5, 6])
    ax.set_title("Test")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    assert ax.get_title() == "Test"

    # Scatter
    ax.scatter([1, 2], [3, 4])

    # Cleanup
    plt.close(fig)

    # rcParams
    assert "figure.figsize" in matplotlib.rcParams

    # Version
    assert matplotlib.__version__

    print("matplotlib: PASS")
except Exception as e:
    print(f"matplotlib: FAIL: {e}")
    sys.exit(1)
