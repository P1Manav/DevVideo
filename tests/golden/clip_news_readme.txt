[title] CLIP (Contrastive Language-Image Pre-Training) is a neural network trained on a variety of (image, text) pairs.
[overview] It can be instructed in natural language to predict the most relevant text snippet, given an image.
[diagram] clip/model dot py defines the neural network model for multimodal representations.
[diagram] It connects to clip/clip dot py, which provides core interface functions for CLIP model loading and inference.
[code] In clip/clip dot py, load loads a CLIP model.
[terminal] Run pip install ftfy regex tqdm to install dependencies for clip news readme.
[fit] clip news readme is not built for video retrieval, but you can feed this video's transcript, chapters and search index into a retrieval pipeline.
[recap] In summary, it can be instructed in natural language to predict the most relevant text snippet.
[recap] To dive in, open clip/model dot py.
