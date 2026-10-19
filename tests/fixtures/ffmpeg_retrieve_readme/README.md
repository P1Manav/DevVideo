# ffmpeg-python: Python bindings for FFmpeg

Complex filter support for FFmpeg multimedia graphs.

- Convert video to numpy array
- Fast video decoding pipelines
- Filter graph construction

## API Overview
You can run stream.get_args() before stream.run() to retrieve the command line arguments that will be passed to ffmpeg.

## Contributing
To run tests locally, install dev dependencies and execute pytest:
```bash
pip install ffmpeg-python
pytest
```
