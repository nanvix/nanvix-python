"""Nanvix pypdfium2 shim — PDF document stub.

Provides import compatibility for pdfplumber and other packages
that optionally use pypdfium2.  Actual PDF rendering requires the
pdfium C library.
"""

__version__ = "4.30.1"

V_PDFIUM = "stub"


class PdfiumError(Exception):
    pass


class PdfDocument:
    """Stub PDF document."""

    def __init__(self, input=None, password=None):
        self._pages = []
        if input is not None:
            # Accept but cannot parse
            pass

    def __len__(self):
        return len(self._pages)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        pass

    def get_page(self, index):
        raise PdfiumError("Nanvix pypdfium2 shim cannot render PDF pages")

    @property
    def page_count(self):
        return len(self._pages)


class PdfPage:
    """Stub PDF page."""

    def __init__(self):
        self.width = 612
        self.height = 792

    def get_textpage(self):
        return PdfTextPage()

    def render(self, **kwargs):
        raise PdfiumError("Nanvix pypdfium2 shim cannot render")

    def close(self):
        pass


class PdfTextPage:
    """Stub text page."""

    def get_text_range(self, index=0, count=-1):
        return ""

    def close(self):
        pass
