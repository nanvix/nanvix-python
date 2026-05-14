"""Test: wordcloud (C++ native extension linked)"""
import sys
sys.stdout.reconfigure(line_buffering=True)
try:
    # Verify the package imports correctly
    import wordcloud
    from wordcloud import STOPWORDS

    # Verify the C extension is linked in the interpreter
    import _wc_query_integral_image
    assert hasattr(_wc_query_integral_image, 'query_integral_image')

    # Verify version
    assert wordcloud.__version__

    # Verify stopwords data file loaded
    assert "the" in STOPWORDS
    assert "a" in STOPWORDS
    assert len(STOPWORDS) > 50

    # Verify WordCloud class is importable
    from wordcloud import WordCloud
    assert callable(WordCloud)

    print("wordcloud: PASS")
except Exception as e:
    print(f"wordcloud: FAIL: {e}")
    sys.exit(1)
