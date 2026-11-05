"""Download and verify the official OpenCV Zoo models."""
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from config import MODELS

REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
BASE_URL = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models"
FILES = {
    "face_detection_yunet/face_detection_yunet_2023mar.onnx":
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "face_recognition_sface/face_recognition_sface_2021dec.onnx":
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}


def download_models():
    MODELS.mkdir(parents=True, exist_ok=True)
    for source, expected in FILES.items():
        target = MODELS / Path(source).name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            print(f"Verified {target.name}")
            continue
        temp_path = None
        digest = hashlib.sha256()
        try:
            with NamedTemporaryFile(dir=MODELS, suffix=".part", delete=False) as temp:
                temp_path = Path(temp.name)
                with urlopen(f"{BASE_URL}/{source}", timeout=30) as response:
                    while chunk := response.read(1024 * 1024):
                        digest.update(chunk)
                        temp.write(chunk)
            if digest.hexdigest() != expected:
                raise ValueError(f"Checksum mismatch for {target.name}.")
            temp_path.replace(target)
            print(f"Downloaded {target.name}")
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        download_models()
    except (OSError, ValueError) as error:
        raise SystemExit(f"Model download failed: {error}") from error
