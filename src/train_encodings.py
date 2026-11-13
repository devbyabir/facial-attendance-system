"""Create a local embedding index from enrolled samples."""
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event

import cv2
import numpy as np

from config import DATASET, ENCODINGS
from src.db_manager import Database
from src.vision import Vision


def index_path(backend: str) -> Path:
    return ENCODINGS / f"{backend}.npz"


def train(db: Database, vision: Vision, stop: Event, progress) -> str:
    vectors, ids = [], []
    skipped = 0
    for user in db.get_users():
        key = user["student_id"]
        succeeded = failed = 0
        for path in sorted((DATASET / f"id_{key}").glob("img_*.jpg")):
            if stop.is_set():
                return "Training cancelled."
            try:
                frame = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
                faces = [] if frame is None else vision.detect(frame)
                vector = vision.encode(frame, faces[0]) if len(faces) == 1 else None
            except (OSError, cv2.error, RuntimeError):
                vector = None
            if vector is None or not np.isfinite(vector).all():
                failed += 1
                continue
            vectors.append(vector)
            ids.append(key)
            succeeded += 1
        skipped += failed
        progress(f"{key}: {succeeded} encoded, {failed} skipped.")
    if stop.is_set():
        return "Training cancelled."
    if not vectors:
        raise ValueError("No usable face samples. Register a person first.")
    ENCODINGS.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=ENCODINGS, suffix=".npz", delete=False) as temp:
        path = Path(temp.name)
    try:
        np.savez_compressed(path, vectors=np.stack(vectors), ids=np.asarray(ids))
        path.replace(index_path(vision.backend))
    finally:
        path.unlink(missing_ok=True)
    return f"Encodings ready: {len(vectors)} samples for {len(set(ids))} people, {skipped} skipped."


def load_index(backend: str):
    path = index_path(backend)
    if not path.is_file():
        raise ValueError(f"No {backend} encodings yet. Generate encodings in Settings first.")
    with np.load(path, allow_pickle=False) as index:
        vectors, ids = index["vectors"], index["ids"]
    if (vectors.ndim != 2 or vectors.shape[1] != 128 or ids.ndim != 1
            or len(vectors) != len(ids) or not len(ids) or not np.isfinite(vectors).all()):
        raise ValueError("The encoding index is invalid. Train the model again.")
    return vectors, ids
