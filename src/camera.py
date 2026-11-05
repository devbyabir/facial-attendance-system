"""Shared camera lifecycle for registration and attendance."""
from contextlib import contextmanager

import cv2


@contextmanager
def webcam(index: int, window: str):
    camera = cv2.VideoCapture(index)
    try:
        if not camera.isOpened():
            raise RuntimeError(f"Could not open camera {index}. Close other camera apps and retry.")
        yield camera
    finally:
        camera.release()
        cv2.destroyAllWindows()


def read_frame(camera):
    ok, frame = camera.read()
    if not ok or frame is None or not frame.size:
        raise RuntimeError("The camera stopped delivering frames.")
    return frame


def show_frame(window: str, frame) -> int:
    cv2.imshow(window, frame)
    key = cv2.waitKey(1) & 0xFF
    try:
        visible = cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE)
    except cv2.error:
        return 27
    return 27 if visible < 1 else key


def label(frame, message: str, x: int = 12, y: int = 28):
    cv2.putText(frame, message, (max(0, x), max(18, y)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (30, 235, 190), 2, cv2.LINE_AA)
