"""Local application paths and camera settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "database" / "attendance.db"
DATASET = ROOT / "dataset"
ENCODINGS = ROOT / "encodings"
REPORTS = ROOT / "reports"
MODELS = ROOT / "models"

CAMERA_INDEX = 0
CAPTURE_COUNT = 24
OPENCV_FRAME_SCALE = 1.0
DLIB_FRAME_SCALE = 0.25
PROCESS_EVERY = 2
CONFIRM_FRAMES = 3
SFACE_MIN_SIMILARITY = 0.45
DLIB_TOLERANCE = 0.5
