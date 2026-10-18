# ffmpeg-python: Python bindings for FFmpeg

There are tons of Python FFmpeg wrappers out there but they seem to lack complex filter support. ffmpeg-python works well for simple as well as complex signal graphs.

## Features
- Convert video to numpy array
- Complex filter graphs
- Fast frame decoding

## Installation
```bash
pip install ffmpeg-python
```

## Quickstart
```bash
python -m ffmpeg.cli input.mp4 output.mp4
```
