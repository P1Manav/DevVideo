# VideoRetriever SDK

A lightweight client library for neural video search and multimodal index queries.

## Overview

VideoRetriever provides Python bindings for indexing and searching video repositories.

## Installation

```bash
pip install videoretriever-sdk
```

## Usage

```python
from retriever import VideoIndex
index = VideoIndex.load("index.bin")
results = index.query("person walking in park")
```
