"""Test: pycountry"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pycountry
    assert pycountry.countries.get(alpha_2="US").name == "United States"
    assert pycountry.currencies.get(alpha_3="EUR").name == "Euro"
    assert pycountry.languages.get(alpha_3="eng").name == "English"
    print("pycountry: PASS")
except Exception as e:
    print(f"pycountry: FAIL: {e}")
    sys.exit(1)
