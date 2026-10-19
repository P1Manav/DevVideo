[title] ffmpeg-python: Python bindings for FFmpeg. Complex filter support for FFmpeg multimedia graphs.
[overview] - Convert video to numpy array.
[overview] You can run stream.get args before stream.run to retrieve the command line arguments that will be passed to ffmpeg.
[diagram] ffmpeg/ utils dot py provides utility functions for shell argument conversion.
[diagram] It connects to ffmpeg/nodes dot py, which defines stream representation nodes forming filter graphs.
[code] In ffmpeg/ run dot py, run invokes ffmpeg for the supplied node graph.
[code] It takes stream spec and invokes convert kwargs to cmd line args and run.
[code] It returns the processed output.
[fit] ffmpeg retrieve readme covers one step of a video retrieval pipeline: decode.
[recap] In summary, - Convert video to numpy array.
[recap] To dive in, open ffmpeg/ utils dot py.
