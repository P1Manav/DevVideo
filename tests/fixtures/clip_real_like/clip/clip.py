"""CLIP model loading and tokenization routines."""

import os
import torch

_MODELS = {"ViT-B/32": "https://openaipublic.azureedge.net/clip/models/vit-b-32.pt"}

def available_models():
    """Returns the names of available CLIP models."""
    return list(_MODELS.keys())

def load(name, device='cpu', jit=True, download_root=None):
    """Load a CLIP model.

    Parameters
    ----------
    name : str
        A model name listed by `clip.available_models()`
    device : Union[str, torch.device]
        The device to put the loaded model on
    """
    download_root = download_root or os.path.expanduser('~/.cache/clip')
    is_cuda = torch.cuda.is_available()
    target_device = 'cuda' if is_cuda and device == 'cuda' else 'cpu'
    return object(), lambda x: x
