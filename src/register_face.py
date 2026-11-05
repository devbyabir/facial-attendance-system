"""Collect single-face enrollment samples from a webcam."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import cv2

from config import CAPTURE_COUNT, DATASET
from src.camera import label, read_frame, show_frame, webcam
from src.db_manager import Database, student_key
from src.vision import Vision


def register(db: Database, vision: Vision, camera_index: int, stop: Event,
             student_id: str, name: str, department: str) -> bool:
    key = student_key(student_id)
    if not name.strip() or not department.strip():
        raise ValueError("Name and department are required.")
    if any(user["student_id"] == key for user in db.get_users()):
        raise ValueError(f"Student ID {key} is already registered.")

    DATASET.mkdir(parents=True, exist_ok=True)
    destination = DATASET / f"id_{key}"
    if destination.exists():
        raise ValueError(f"A sample folder already exists for {key}.")

    window = "Enrollment | Space to capture | Q to cancel"
    with TemporaryDirectory(dir=DATASET, prefix=".enroll-") as folder:
        staging = Path(folder) / "samples"
        staging.mkdir()
        captured = 0
        with webcam(camera_index, window) as camera:
            while captured < CAPTURE_COUNT:
                if stop.is_set():
                    return False
                frame = read_frame(camera)
                faces = vision.detect(frame)
                preview = frame.copy()
                if len(faces) == 1:
                    x, y, width, height = faces[0].box
                    cv2.rectangle(preview, (x, y), (x + width, y + height), (30, 235, 190), 2)
                    guidance = "Vary your pose slightly, then press Space."
                else:
                    guidance = "Exactly one face must be visible."
                label(preview, f"{captured}/{CAPTURE_COUNT}   {guidance}")
                pressed = show_frame(window, preview)
                if pressed in (ord("q"), ord("Q"), 27):
                    return False
                if pressed == 32 and len(faces) == 1:
                    ok, image = cv2.imencode(".jpg", frame)
                    if not ok:
                        raise RuntimeError("Could not encode the capture.")
                    captured += 1
                    (staging / f"img_{captured:03}.jpg").write_bytes(image.tobytes())
        if stop.is_set():
            return False
        staging.rename(destination)
        try:
            db.add_user(key, name, department)
        except Exception:
            destination.rename(staging)
            raise
    return True
