"""Test: pypdfium2 (shim)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pypdfium2

    # Basic import and version
    assert pypdfium2.__version__

    # Document constructor
    doc = pypdfium2.PdfDocument()
    assert len(doc) == 0

    # Context manager
    with pypdfium2.PdfDocument() as doc2:
        assert doc2.page_count == 0

    # Error class
    try:
        doc.get_page(0)
        assert False, "should have raised"
    except pypdfium2.PdfiumError:
        pass

    print("pypdfium2: PASS")
except Exception as e:
    print(f"pypdfium2: FAIL: {e}")
    sys.exit(1)
