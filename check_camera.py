"""Check whether a webcam can deliver a frame to OpenCV."""

import argparse
import sys

import cv2


def check_camera(index: int, preview: bool) -> bool:
    """Read one frame and optionally show a live preview."""
    camera = cv2.VideoCapture()
    try:
        if not camera.open(index):
            print(f"Could not open camera {index}.", file=sys.stderr)
            return False

        ok, frame = camera.read()
        if not ok or frame is None or frame.size == 0:
            print("The camera opened but did not deliver a frame.", file=sys.stderr)
            return False

        height, width = frame.shape[:2]
        print(f"Camera {index} works: {width} x {height}.")
        if not preview:
            return True

        print("Press Q or Esc in the preview to close it.")
        while True:
            cv2.imshow("Webcam check", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                return True
            if cv2.getWindowProperty("Webcam check", cv2.WND_PROP_VISIBLE) < 1:
                return True
            ok, frame = camera.read()
            if not ok or frame is None or frame.size == 0:
                print("The camera stopped delivering frames.", file=sys.stderr)
                return False
    except cv2.error as error:
        print(f"OpenCV camera error: {error}", file=sys.stderr)
        return False
    finally:
        camera.release()
        if preview:
            cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="Webcam index")
    parser.add_argument("--preview", action="store_true", help="Show a live preview")
    args = parser.parse_args()
    if args.camera < 0:
        parser.error("--camera must be zero or greater")
    return 0 if check_camera(args.camera, args.preview) else 1


if __name__ == "__main__":
    raise SystemExit(main())
