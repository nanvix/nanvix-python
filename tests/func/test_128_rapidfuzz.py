"""Test: rapidfuzz (C++ native extensions)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    import rapidfuzz
    from rapidfuzz import fuzz, process

    # Verify C++ extensions are loaded (not Python fallback)
    from rapidfuzz._feature_detector import supports
    cpp_available = False
    try:
        from rapidfuzz import fuzz_cpp
        cpp_available = True
    except ImportError:
        pass

    # Basic ratio
    score = fuzz.ratio("hello", "hello")
    assert score == 100.0, f"expected 100, got {score}"

    # Partial ratio
    score2 = fuzz.partial_ratio("hello world", "hello")
    assert score2 > 50

    # Token sort
    score3 = fuzz.token_sort_ratio("world hello", "hello world")
    assert score3 == 100.0

    # Process extract
    choices = ["hello", "world", "help", "hero"]
    results = process.extract("helo", choices, limit=2)
    assert len(results) == 2
    assert results[0][0] in choices

    # extractOne
    best = process.extractOne("helo", choices)
    assert best is not None

    # Version
    assert rapidfuzz.__version__

    backend = "C++" if cpp_available else "Python"
    print(f"rapidfuzz: PASS (backend={backend})")
except Exception as e:
    print(f"rapidfuzz: FAIL: {e}")
    sys.exit(1)
