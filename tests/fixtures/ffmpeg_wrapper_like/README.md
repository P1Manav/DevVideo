# ffmpeg-python: Python bindings for FFmpeg

Python bindings for FFmpeg. There are tons of Python FFmpeg wrappers out there but they seem to lack complex filter support.

## Overview

ffmpeg-python allows you to assemble complex FFmpeg filter graphs and transcode audio or video streams using an expressive Pythonic API.

## Installation

```bash
pip install ffmpeg-python
```

## Quickstart

```python
import ffmpeg
stream = ffmpeg.input('input.mp4')
stream = ffmpeg.hflip(stream)
stream = ffmpeg.output(stream, 'output.mp4')
ffmpeg.run(stream)
```
