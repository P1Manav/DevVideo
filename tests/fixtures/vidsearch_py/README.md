<p align="center">
  <img src="https://raw.githubusercontent.com/example/vidsearch/main/logo.png" alt="VidSearch Logo" width="200"/>
  <h1>VidSearch</h1>
</p>

[![CI](https://github.com/example/vidsearch/actions/workflows/ci.yml/badge.svg)](https://github.com/example/vidsearch/actions)
[![PyPI](https://img.shields.io/pypi/v/vidsearch.svg)](https://pypi.org/project/vidsearch/)

VidSearch is a lightweight multimodal video understanding and retrieval engine. It extracts key frames from video clips using ffmpeg, computes dense vector embeddings, builds a fast Faiss vector index, and searches video segments using natural language queries.

## Quickstart

Install the dependencies:

```bash
pip install -r requirements.txt
```

Index a video directory and search for clips:

```bash
python -m vidsearch.cli --query "sunset over ocean" --index index.faiss --fps 1.0
```

## Architecture

1. **Frame Extraction**: `vidsearch.frames` samples video keyframes with ffmpeg.
2. **Embedding**: `vidsearch.embed` generates normalized vector embeddings.
3. **Indexing**: `vidsearch.index` writes vectors into a Faiss cosine index.
4. **Search**: `vidsearch.search` queries the Faiss index for top matching video timestamps.
