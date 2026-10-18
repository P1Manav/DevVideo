[[Blog]](https://openai.com/blog/clip/) [[Paper]](https://arxiv.org/abs/2103.00020) [[Model Card]](model-card.md)

CLIP (Contrastive Language-Image Pre-Training) is a neural network trained on a variety of (image, text) pairs. It can be instructed in natural language to predict the most relevant text snippet, given an image, without directly optimizing for the task.

## Features
- Zero-shot classification matching ResNet50 performance on ImageNet.
- Robust multimodal representation learning across diverse visual domains.

## Usage
```bash
pip install -r requirements.txt
python -m clip_tool.cli --image input.png --query "a dog playing frisbee"
```
