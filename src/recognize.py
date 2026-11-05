"""Run camera recognition and record confirmed daily attendance."""
from datetime import datetime
from threading import Event

import cv2

from config import CONFIRM_FRAMES, DLIB_FRAME_SCALE, OPENCV_FRAME_SCALE, PROCESS_EVERY
from src.attendance import Confirmation
from src.camera import label, read_frame, show_frame, webcam
from src.db_manager import Database
from src.train_encodings import load_index
from src.vision import Vision, best_match


def recognize(db: Database, vision: Vision, camera_index: int,
              stop: Event, progress) -> str:
    vectors, ids = load_index(vision.backend)
    names = {row["student_id"]: row["name"] for row in db.get_users()}
    confirmation = Confirmation(CONFIRM_FRAMES)
    frame_number, marked = 0, 0
    status, box = "Looking for a face", None
    outcomes = {}
    current_day = None
    scale = DLIB_FRAME_SCALE if vision.backend == "dlib" else OPENCV_FRAME_SCALE
    window = "Attendance | Q to stop"
    with webcam(camera_index, window) as camera:
        while not stop.is_set():
            frame = read_frame(camera)
            if frame_number % PROCESS_EVERY == 0:
                sample = frame if scale == 1 else cv2.resize(frame, None, fx=scale, fy=scale)
                faces = vision.detect(sample)
                key, box = None, None
                if len(faces) == 1:
                    face = faces[0]
                    box = tuple(round(value / scale) for value in face.box)
                    key = best_match(vision.encode(sample, face), vectors, ids, vision.backend)
                if key not in names:
                    key = None
                now = datetime.now()
                if current_day != now.date():
                    current_day = now.date()
                    confirmation.observe(None)
                    outcomes.clear()
                entry = (key, current_day)
                if confirmation.observe(key) and entry not in outcomes:
                    saved = db.mark_attendance(key, when=now)
                    outcomes[entry] = "Marked" if saved else "Already marked"
                    marked += int(saved)
                    progress(f"{key}: {outcomes[entry]}")
                if key:
                    status = f"{names[key]} ({key}) | {outcomes.get(entry, 'Confirming...')}"
                elif len(faces) > 1:
                    status = "One person at a time"
                else:
                    status = "Unknown" if faces else "Looking for a face"
            frame_number += 1
            if box is not None:
                x, y, width, height = box
                cv2.rectangle(frame, (x, y), (x + width, y + height), (30, 235, 190), 2)
            label(frame, status)
            if show_frame(window, frame) in (ord("q"), ord("Q"), 27):
                break
    return f"Attendance stopped. {marked} new daily records."
