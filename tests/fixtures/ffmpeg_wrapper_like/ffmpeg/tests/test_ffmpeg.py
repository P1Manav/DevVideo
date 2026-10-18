"""Tests for ffmpeg wrapper."""
import ffmpeg


def test_input():
    node = ffmpeg.input("dummy.mp4")
    assert node.filename == "dummy.mp4"
