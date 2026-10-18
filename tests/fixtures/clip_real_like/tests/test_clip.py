"""Tests for clip package."""
from clip.clip import available_models, load, tokenize


def test_models():
    assert len(available_models()) >= 1
