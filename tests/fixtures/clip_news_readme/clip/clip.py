"""Core interface functions for CLIP model loading and inference."""
import os
from .model import build_model

def load(
    name: str,
    device: str = "cpu",
    jit: bool = False,
    download_root: str = None,
):
    """
    Load a CLIP model.

    Parameters
    ----------
    name : str
        A model name listed by `clip.available_models()`, or the path to a model
        checkpoint containing the state_dict.
    device : Union[str, torch.device]
        The device to put the loaded model.
    jit : bool
        Whether to load the optimized JIT model or more flexible model.
    download_root: str
        Path to download the model files; by default, it uses "~/.cache/clip".

    Returns
    -------
    model : torch.nn.Module
        The CLIP model.
    preprocess : Callable[[PIL.Image], torch.Tensor]
        A torchvision transform that converts a PIL image into a tensor that the
        returned model can accept as its input.

    Raises
    ------
    RuntimeError
        If the model is not found in available models.
    """
    if not os.path.exists(name):
        model_path = os.path.expanduser(f"~/.cache/clip/{name}.pt")
    else:
        model_path = name

    state_dict = {"name": name, "path": model_path}
    model = build_model(state_dict)
    preprocess = lambda img: img

    if jit:
        return model, preprocess

    return model, preprocess
