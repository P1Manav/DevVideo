# CLIP
[![PyPI](https://img.shields.io/pypi/v/clip.svg)](https://pypi.org/project/clip/)

## News
* **[July 2022]** OpenCLIP: includes larger and independently trained CLIP models up to ViT-G/14.
* **[January 2022]** Hugging Face implementation of CLIP: for easier integration with the HF ecosystem.

## Approach
CLIP (Contrastive Language-Image Pre-Training) is a neural network trained on a variety of (image, text) pairs.
It can be instructed in natural language to predict the most relevant text snippet, given an image.

## Usage
```bash
pip install ftfy regex tqdm
```

```python
import clip
model, preprocess = clip.load("ViT-B/32")
```
