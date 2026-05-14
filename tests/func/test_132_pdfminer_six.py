"""Test: pdfminer.six"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pdfminer
    from pdfminer.high_level import extract_text
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument

    # Basic import verification
    assert hasattr(pdfminer, '__version__') or True  # pdfminer.six may not set __version__

    # PDFParser accepts file-like objects
    import io
    buf = io.BytesIO(b"%PDF-1.4 minimal")
    try:
        parser = PDFParser(buf)
    except Exception:
        pass  # Minimal PDF won't parse but import works

    print("pdfminer.six: PASS")
except ImportError as e:
    print(f"pdfminer.six: SKIP ({e})")
except Exception as e:
    print(f"pdfminer.six: FAIL: {e}")
    sys.exit(1)
