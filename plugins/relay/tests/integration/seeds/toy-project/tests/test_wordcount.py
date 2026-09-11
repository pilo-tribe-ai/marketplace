import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from wordcount import word_count


def test_word_count_counts_words():
    assert word_count("one two three") == 3


def test_word_count_empty_is_zero():
    assert word_count("") == 0
