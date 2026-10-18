[[Blog]](https://openai.com/research/clip) [[Paper]](https://arxiv.org/abs/2103.00020)

# CLIP

CLIP (Contrastive Language-Image Pre-Training) is a neural network trained on a variety of (image, text) pairs. It can be instructed in natural language to predict the most relevant text snippet, given an image, without being directly optimized for the task.

## Approach

CLIP jointly trains an image encoder and a text encoder to predict the correct pairings of a batch of (image, text) training examples. At test time, the learned feature representation is used for zero-shot classification.

## Install

First install PyTorch and torchvision:
```bash
conda install --yes -c pytorch pytorch=1.7.1 torchvision cudatoolkit=11.0
pip install ftfy regex tqdm
```

## Usage

```python
import clip
import torch

model, preprocess = clip.load("ViT-B/32")
text = clip.tokenize(["a diagram", "a dog", "a cat"])
```
