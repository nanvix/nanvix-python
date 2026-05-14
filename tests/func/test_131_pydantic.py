"""Test: pydantic (v1 pure Python)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import pydantic

    assert pydantic.VERSION.startswith("1.")

    class User(pydantic.BaseModel):
        name: str
        age: int

    u = User(name="Nanvix", age=5)
    assert u.name == "Nanvix"
    assert u.age == 5

    # Validation
    try:
        User(name="test", age="not_a_number")
        assert False, "should have raised"
    except (pydantic.ValidationError, ValueError, TypeError):
        pass

    # Dict export
    d = u.dict()
    assert d["name"] == "Nanvix"

    print("pydantic: PASS")
except Exception as e:
    print(f"pydantic: FAIL: {e}")
    sys.exit(1)
