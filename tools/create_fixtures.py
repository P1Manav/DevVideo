"""
Create/update fixtures for Phase 1.
"""
import pathlib

def create_fixtures():
    # 1. ffmpeg_wrapper_real
    base_ff = pathlib.Path("tests/fixtures/ffmpeg_wrapper_real")
    (base_ff / "ffmpeg" / "tests").mkdir(parents=True, exist_ok=True)
    (base_ff / "examples").mkdir(parents=True, exist_ok=True)
    (base_ff / "doc" / "_static").mkdir(parents=True, exist_ok=True)

    (base_ff / "README.md").write_text(
        "# ffmpeg-python: Python bindings for FFmpeg\n\n"
        "There are tons of Python FFmpeg wrappers out there but they seem to lack complex filter support. "
        "ffmpeg-python works well for simple as well as complex signal graphs.\n\n"
        "## Features\n"
        "- Convert video to numpy array\n"
        "- Complex filter graphs\n"
        "- Fast frame decoding\n\n"
        "## Installation\n"
        "```bash\n"
        "pip install ffmpeg-python\n"
        "```\n\n"
        "## Quickstart\n"
        "```bash\n"
        "python -m ffmpeg.cli input.mp4 output.mp4\n"
        "```\n",
        encoding="utf-8"
    )

    (base_ff / "ffmpeg" / "__init__.py").write_text(
        "from ._run import run\n"
        "from ._filters import filter\n"
        "from .nodes import Node\n\n"
        "__all__ = ['run', 'filter', 'Node']\n",
        encoding="utf-8"
    )

    (base_ff / "ffmpeg" / "_run.py").write_text(
        '"""Execution runner for FFmpeg node graphs."""\n\n'
        "def run(stream_spec, cmd='ffmpeg', overwrite_output=False):\n"
        '    """Invoke ffmpeg for the supplied node graph."""\n'
        "    args = ['ffmpeg', '-i', 'input.mp4', 'output.mp4']\n"
        "    return args\n",
        encoding="utf-8"
    )

    (base_ff / "ffmpeg" / "_filters.py").write_text(
        '"""Filter nodes and operations for ffmpeg-python."""\n\n'
        "def filter(stream_spec, filter_name, *args, **kwargs):\n"
        '    """Apply a filter to the supplied stream."""\n'
        "    return {'filter': filter_name, 'args': args}\n",
        encoding="utf-8"
    )

    (base_ff / "ffmpeg" / "nodes.py").write_text(
        '"""Node hierarchy for filter graph representation."""\n\n'
        "class Node:\n"
        '    """Base graph node."""\n'
        "    def __init__(self, name):\n"
        "        self.name = name\n",
        encoding="utf-8"
    )

    (base_ff / "ffmpeg" / "_utils.py").write_text(
        '"""Internal utilities."""\n\n'
        "def escape_chars(text):\n"
        '    """Escape special characters."""\n'
        '    return text.replace(":", "\\\\:")\n',
        encoding="utf-8"
    )

    (base_ff / "examples" / "get_video_thumbnail.py").write_text(
        '"""Example script to extract a thumbnail."""\n'
        "import ffmpeg\n\n"
        "def generate_thumbnail(in_filename, out_filename, time):\n"
        '    """Generate a video thumbnail."""\n'
        "    ffmpeg.run(in_filename)\n",
        encoding="utf-8"
    )

    (base_ff / "ffmpeg" / "tests" / "test_ffmpeg.py").write_text(
        "def test_dummy():\n    assert True\n",
        encoding="utf-8"
    )

    # Vendored docs JS (larger in bytes than python source)
    js_blob = "/* jQuery v3.6.0 | (c) OpenJS Foundation | jquery.org/license */\n" + ("var jQuery = function() { return new jQuery.fn.init(); };\n" * 600)
    (base_ff / "doc" / "jquery.js").write_text(js_blob, encoding="utf-8")
    (base_ff / "doc" / "underscore.js").write_text("/* Underscore.js 1.13.1 */\n" + ("var _ = function(obj) { return new _(obj); };\n" * 400), encoding="utf-8")
    (base_ff / "doc" / "_static" / "doctools.min.js").write_text("/* Sphinx doctools */\n" + ("var Documentation = {};\n" * 500), encoding="utf-8")

    # 2. clip_real_like (extend per spec)
    # library with load()/available_models() where available_models calls list(_MODELS.keys()),
    # load calls os.path.expanduser, torch.cuda.is_available;
    # README link row + prose + conda install + pip install ftfy regex tqdm, and usage snippet starting with import clip.
    base_clip = pathlib.Path("tests/fixtures/clip_real_like")
    (base_clip / "clip").mkdir(parents=True, exist_ok=True)
    (base_clip / "tests").mkdir(parents=True, exist_ok=True)

    (base_clip / "README.md").write_text(
        "# CLIP: Contrastive Language-Image Pre-Training\n\n"
        "[[Blog]](https://openai.com/blog/clip/) [[Paper]](https://arxiv.org/abs/2103.00020) [[Model Card]](model-card.md)\n\n"
        "CLIP (Contrastive Language-Image Pre-Training) is a neural network trained on a variety of (image, text) pairs. "
        "It can be instructed in natural language to predict the most relevant text snippet, given an image, without directly optimizing for the task.\n\n"
        "## Approach\n"
        "CLIP models visual concepts using natural language supervision.\n\n"
        "## Installation\n\n"
        "```bash\n"
        "conda install --yes -c pytorch pytorch=1.7.1 torchvision cudatoolkit=11.0\n"
        "pip install ftfy regex tqdm\n"
        "```\n\n"
        "## Usage\n\n"
        "```python\n"
        "import clip\n"
        "import torch\n\n"
        'device = "cuda" if torch.cuda.is_available() else "cpu"\n'
        'model, preprocess = clip.load("ViT-B/32", device=device)\n'
        "```\n",
        encoding="utf-8"
    )

    (base_clip / "clip" / "__init__.py").write_text(
        "from .clip import load, available_models\n\n"
        "__all__ = ['load', 'available_models']\n",
        encoding="utf-8"
    )

    (base_clip / "clip" / "clip.py").write_text(
        '"""CLIP model loading and tokenization routines."""\n\n'
        "import os\n"
        "import torch\n\n"
        '_MODELS = {"ViT-B/32": "https://openaipublic.azureedge.net/clip/models/vit-b-32.pt"}\n\n'
        "def available_models():\n"
        '    """Returns the names of available CLIP models."""\n'
        "    return list(_MODELS.keys())\n\n"
        "def load(name, device='cpu', jit=True, download_root=None):\n"
        '    """Load a CLIP model.\n\n'
        "    Parameters\n"
        "    ----------\n"
        "    name : str\n"
        "        A model name listed by `clip.available_models()`\n"
        "    device : Union[str, torch.device]\n"
        "        The device to put the loaded model on\n"
        '    """\n'
        "    download_root = download_root or os.path.expanduser('~/.cache/clip')\n"
        "    is_cuda = torch.cuda.is_available()\n"
        "    target_device = 'cuda' if is_cuda and device == 'cuda' else 'cpu'\n"
        "    return object(), lambda x: x\n",
        encoding="utf-8"
    )

    # 3. readme_only
    # README with a title and ONE sentence ("My first repository on GitHub!" style), no code at all (Hello-World shape).
    base_ro = pathlib.Path("tests/fixtures/readme_only")
    base_ro.mkdir(parents=True, exist_ok=True)
    (base_ro / "README.md").write_text(
        "# Hello-World\n\n"
        "My first repository on GitHub!\n",
        encoding="utf-8"
    )

    # 4. no_prose_readme
    # README with only headings, badges and a table.
    base_np = pathlib.Path("tests/fixtures/no_prose_readme")
    base_np.mkdir(parents=True, exist_ok=True)
    (base_np / "README.md").write_text(
        "# Project Status\n\n"
        "[![Build](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://example.com)\n"
        "[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://example.com)\n\n"
        "## Components\n\n"
        "| Name | Version | Status |\n"
        "| :--- | :--- | :--- |\n"
        "| Core | 1.0.0 | Active |\n"
        "| Tool | 0.2.1 | Beta |\n",
        encoding="utf-8"
    )

    print("Successfully created all Phase 1 fixtures.")

if __name__ == "__main__":
    create_fixtures()
