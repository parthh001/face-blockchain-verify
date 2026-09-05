"""
face_id.py
==========
Stage 1 of the pipeline: face detection + encoding.

Two backends, auto-selected at import time:

  1. `face_recognition` (dlib ResNet, 128-d embedding). Used automatically
     if it is installed (`pip install face_recognition`). This is the
     recommended backend -- it's the industry-standard approach and gives
     a real recognition-grade embedding.

  2. Built-in OpenCV Haar-cascade detector + HOG descriptor. Pure classical
     computer vision, zero extra dependencies, works fully offline with
     nothing beyond opencv-python. Used automatically as a fallback when
     `face_recognition`/dlib isn't installed (e.g. in network-restricted
     environments where dlib can't be compiled).

Either backend produces the same output shape:
  - a fixed-length numeric encoding (python list of floats)
  - a SHA-256 fingerprint of that encoding (this is what gets anchored to
    the blockchain in stage 3 -- we hash the encoding, not the raw photo,
    so the on-chain record never contains biometric data itself)
  - the pixel bounding box of the detected face
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

try:
    import face_recognition  # type: ignore
    _BACKEND = "face_recognition (dlib, 128-d embedding)"
    _HAS_FACE_RECOGNITION = True
except ImportError:
    _BACKEND = "opencv-haar + HOG (classical fallback, no dlib available)"
    _HAS_FACE_RECOGNITION = False

_HAAR_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


@dataclass
class FaceRecord:
    encoding: List[float]
    fingerprint: str                    # sha256 hex digest of the encoding
    bbox: Tuple[int, int, int, int]      # x, y, w, h in the source image
    backend: str
    source_image: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "encoding_length": len(self.encoding),
                "fingerprint": self.fingerprint,
                "bbox": list(self.bbox),
                "backend": self.backend,
                "source_image": self.source_image,
            },
            indent=2,
        )

    def to_dict(self) -> dict:
        return {
            "encoding": self.encoding,
            "fingerprint": self.fingerprint,
            "bbox": list(self.bbox),
            "backend": self.backend,
            "source_image": self.source_image,
        }


def _fingerprint(vector: np.ndarray) -> str:
    # Quantize before hashing so near-identical floats hash identically
    # (float repr can differ in the last bits between runs/platforms).
    quantized = np.round(vector.astype(np.float64), 6)
    return hashlib.sha256(quantized.tobytes()).hexdigest()


def _detect_face_bbox(gray: np.ndarray) -> Tuple[int, int, int, int]:
    cascade = cv2.CascadeClassifier(_HAAR_PATH)
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        raise ValueError("No face detected in the input image.")
    # If several faces are found, use the largest (closest to camera).
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = faces[0]
    return int(x), int(y), int(w), int(h)


def _encode_classical(image_bgr: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = bbox
    face = image_bgr[y : y + h, x : x + w]
    face = cv2.resize(face, (128, 128))
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    hog = cv2.HOGDescriptor((128, 128), (32, 32), (16, 16), (16, 16), 9)
    vec = hog.compute(gray).flatten()
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def process_image(image_path: str) -> FaceRecord:
    """Detect the (largest) face in `image_path` and return its encoding."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image_bgr = cv2.imread(str(path))
    if image_bgr is None:
        raise ValueError(f"Could not read image (unsupported format?): {image_path}")

    if _HAS_FACE_RECOGNITION:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb)
        if not locations:
            raise ValueError("No face detected in the input image.")
        top, right, bottom, left = locations[0]
        bbox = (left, top, right - left, bottom - top)
        encodings = face_recognition.face_encodings(rgb, known_face_locations=[locations[0]])
        vector = np.asarray(encodings[0])
    else:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        bbox = _detect_face_bbox(gray)
        vector = _encode_classical(image_bgr, bbox)

    return FaceRecord(
        encoding=[float(v) for v in vector],
        fingerprint=_fingerprint(vector),
        bbox=bbox,
        backend=_BACKEND,
        source_image=str(path),
    )


def crop_face(image_path: str, bbox: Tuple[int, int, int, int], out_path: str, margin: float = 0.4) -> str:
    """Crop the detected face (with a margin so context/hair is included)
    and save it. This crop is what gets uploaded for reverse image search
    in stage 2 -- we search with the face, not the whole original photo."""
    image_bgr = cv2.imread(image_path)
    h_img, w_img = image_bgr.shape[:2]
    x, y, w, h = bbox
    mx, my = int(w * margin), int(h * margin)
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(w_img, x + w + mx), min(h_img, y + h + my)
    crop = image_bgr[y0:y1, x0:x1]
    cv2.imwrite(out_path, crop)
    return out_path


def compare(encoding_a: List[float], encoding_b: List[float]) -> float:
    """Euclidean distance between two encodings (lower = more similar).
    Only meaningful when both encodings came from the same backend."""
    a, b = np.asarray(encoding_a), np.asarray(encoding_b)
    return float(np.linalg.norm(a - b))


def draw_bbox(image_path: str, bbox: Tuple[int, int, int, int], out_path: str) -> str:
    """Save a copy of the image with a rectangle drawn around the detected
    face, plus its fingerprint-ready label. Purely visual -- useful for the
    screen recording so the viewer can *see* stage 1 actually found the
    face, not just read a JSON blob."""
    image_bgr = cv2.imread(image_path)
    x, y, w, h = bbox
    annotated = image_bgr.copy()
    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 220, 0), 3)
    label = "face detected"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(annotated, (x, max(0, y - th - 10)), (x + tw + 10, y), (0, 220, 0), -1)
    cv2.putText(annotated, label, (x + 5, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.imwrite(out_path, annotated)
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 1: detect + encode a face")
    parser.add_argument("image", help="Path to the input photo")
    parser.add_argument("--visualize", metavar="OUT_PATH", help="Also save a copy with the detected face boxed")
    args = parser.parse_args()

    record = process_image(args.image)
    print(f"Backend: {record.backend}")
    print(record.to_json())

    if args.visualize:
        draw_bbox(args.image, tuple(record.bbox), args.visualize)
        print(f"\nAnnotated image saved to {args.visualize}")
