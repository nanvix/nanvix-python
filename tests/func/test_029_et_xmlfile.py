"""Test: et-xmlfile"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    from et_xmlfile import xmlfile
    import io

    # Test basic XML file generation
    out = io.BytesIO()
    with xmlfile(out) as xf:
        with xf.element("root"):
            with xf.element("child", attrib={"key": "value"}):
                xf.write("hello")

    result = out.getvalue()
    assert b"<root>" in result, f"missing <root> tag in: {result}"
    assert b"<child " in result, f"missing <child> tag in: {result}"
    assert b"hello" in result, f"missing text content in: {result}"

    print("et-xmlfile: PASS")
except Exception as e:
    print(f"et-xmlfile: FAIL: {e}")
    sys.exit(1)
