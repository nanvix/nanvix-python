"""Test: lxml (statically-linked C module)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    from lxml import etree

    # Parse XML
    root = etree.fromstring(b"<root><child>Nanvix</child></root>")
    assert root.tag == "root"
    assert root[0].text == "Nanvix"

    # Build XML
    root2 = etree.Element("test")
    child = etree.SubElement(root2, "item")
    child.text = "hello"
    xml_bytes = etree.tostring(root2)
    assert b"hello" in xml_bytes

    print("lxml: PASS")
except ImportError:
    print("lxml: SKIP (not available)")
except Exception as e:
    print(f"lxml: FAIL: {e}")
    sys.exit(1)
