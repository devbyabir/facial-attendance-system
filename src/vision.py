"""Face detection and embedding with OpenCV or the optional dlib backend."""
from dataclasses import dataclass

import cv2
import numpy as np

from config import DLIB_TOLERANCE, MODELS, SFACE_MIN_SIMILARITY

YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"


@dataclass
class Face:
    box: tuple[int, int, int, int]
    landmarks: object


class Vision:
    def __init__(self, backend: str):
        self.backend = backend
        if backend == "dlib":
            try:
                import face_recognition
            except ImportError as error:
                raise RuntimeError("Install requirements-dlib.txt or choose OpenCV.") from error
            self.dlib = face_recognition
        elif backend == "opencv":
            if not all((MODELS / name).is_file() for name in (YUNET, SFACE)):
                raise RuntimeError("Download the OpenCV models with python download_models.py.")
            self.detector = cv2.FaceDetectorYN.create(str(MODELS / YUNET), "", (320, 320))
            self.recognizer = cv2.FaceRecognizerSF.create(str(MODELS / SFACE), "")
        else:
            raise ValueError("Choose opencv or dlib.")

    def detect(self, frame):
        if self.backend == "dlib":
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return [
                Face((left, top, right - left, bottom - top), (top, right, bottom, left))
                for top, right, bottom, left in self.dlib.face_locations(rgb)
            ]
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        return [] if faces is None else [
            Face(tuple(int(value) for value in row[:4]), row) for row in faces
        ]

    def encode(self, frame, face: Face):
        if self.backend == "dlib":
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            embeddings = self.dlib.face_encodings(rgb, [face.landmarks])
            return None if not embeddings else np.asarray(embeddings[0], dtype=np.float32)
        aligned = self.recognizer.alignCrop(frame, face.landmarks)
        vector = self.recognizer.feature(aligned).flatten()
        norm = np.linalg.norm(vector)
        return None if not norm else vector / norm


def best_match(vector, vectors, ids, backend: str) -> str | None:
    if vector is None or len(vectors) == 0:
        return None
    if backend == "dlib":
        distances = np.linalg.norm(vectors - vector, axis=1)
        best = int(distances.argmin())
        return str(ids[best]) if distances[best] < DLIB_TOLERANCE else None
    similarities = vectors @ vector
    best = int(similarities.argmax())
    return str(ids[best]) if similarities[best] >= SFACE_MIN_SIMILARITY else None
