import cv2
import numpy as np
from PIL import Image
from typing import List
import io


def extract_frames(video_path: str, n_frames: int = 20) -> List[np.ndarray]:
    """Extract evenly spaced frames from video in BGR."""
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total == 0:
        cap.release()
        return []

    indices = np.linspace(0, total - 1, min(n_frames, total), dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


def image_to_bgr(image_bytes: bytes) -> np.ndarray:
    """Convert uploaded image bytes to BGR numpy array."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def compute_lab_stats(frames: List[np.ndarray]) -> dict:
    """Compute mean and std in CIE Lab per channel across all frames."""
    all_pixels = []
    for frame in frames:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
        all_pixels.append(lab.reshape(-1, 3))

    pixels = np.concatenate(all_pixels, axis=0)
    return {
        "mean": pixels.mean(axis=0),   # [L, a, b]
        "std":  pixels.std(axis=0),
    }


def compute_histogram_stats(frames: List[np.ndarray]) -> dict:
    """Per-channel histogram analysis in BGR (0-255)."""
    stats = {}
    for ch_idx, ch_name in enumerate(["b", "g", "r"]):
        vals = np.concatenate([f[:, :, ch_idx].flatten() for f in frames])
        stats[ch_name] = {
            "mean": float(vals.mean()),
            "std":  float(vals.std()),
            "p5":   float(np.percentile(vals, 5)),
            "p95":  float(np.percentile(vals, 95)),
        }
    return stats
