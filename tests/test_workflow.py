"""Regression checks that do not require a webcam or enrolled faces."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event
from unittest.mock import patch

import cv2
import numpy as np
from openpyxl import load_workbook

from src.attendance import Confirmation
from src.db_manager import Database
from src.recognize import recognize
from src.reports import export_report, report_data
from src.register_face import register
from src.train_encodings import load_index, train
from src.vision import Face, best_match


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = Database(self.root / "attendance.db")

    def test_daily_unique_and_filters(self):
        self.db.add_user("S01", "Alex", "Computing")
        with self.assertRaises(ValueError):
            self.db.add_user("s01", "Duplicate", "Computing")
        with self.assertRaises(ValueError):
            self.db.mark_attendance("S99")
        self.assertTrue(self.db.mark_attendance("S01", datetime(2025, 3, 1, 9)))
        self.assertFalse(self.db.mark_attendance("S01", datetime(2025, 3, 1, 15)))
        self.assertTrue(self.db.mark_attendance("S01", datetime(2025, 3, 2, 9)))
        row, = self.db.get_attendance(date="2025-03-01", student_id="s01")
        self.assertEqual((row["time"], row["status"]), ("09:00:00", "Present"))

    def test_report_exports(self):
        self.db.add_user("S01", "=1+1", "Computing")
        self.db.add_user("S02", "Mina", "Computing")
        self.db.mark_attendance("S01", datetime(2025, 3, 1, 9))
        records, summary = report_data(self.db, "2025-03-01", "2025-03-02")
        self.assertEqual(summary.set_index("student_id")["attendance_percent"].to_dict(),
                         {"S01": 50.0, "S02": 0.0})
        export_report(self.root / "report.csv", records, summary)
        export_report(self.root / "report.xlsx", records, summary)
        self.assertIn("'=1+1", (self.root / "report.csv").read_text(encoding="utf-8-sig"))
        workbook = load_workbook(self.root / "report.xlsx")
        try:
            self.assertEqual(workbook.sheetnames, ["Attendance", "Summary"])
            self.assertEqual(workbook["Attendance"]["B2"].data_type, "s")
        finally:
            workbook.close()

    def test_match_and_confirmation(self):
        vectors = np.eye(2, 128, dtype=np.float32)
        ids = ["S01", "S02"]
        self.assertEqual(best_match(vectors[0], vectors, ids, "opencv"), "S01")
        self.assertIsNone(best_match(-vectors[0], vectors, ids, "opencv"))
        self.assertEqual(best_match(vectors[1], vectors, ids, "dlib"), "S02")
        self.assertIsNone(best_match(-vectors[0], vectors, ids, "dlib"))
        confirmation = Confirmation(3)
        result = [confirmation.observe(key) for key in
                  ("S01", "S01", None, "S01", "S01", "S01", "S01")]
        self.assertEqual(result, [False, False, False, False, False, True, False])

    def test_registration_skips_multiple_faces_and_training_saves_index(self):
        face = Face((10, 10, 20, 20), None)
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        dataset = self.root / "dataset"
        with (
            patch("src.register_face.DATASET", dataset),
            patch("src.register_face.CAPTURE_COUNT", 1),
            patch("src.register_face.webcam"),
            patch("src.register_face.read_frame", return_value=frame),
            patch("src.register_face.show_frame", return_value=32) as preview,
            patch("src.register_face.Vision") as detector,
        ):
            vision = detector.return_value
            vision.detect.side_effect = [[face, face], [face]]
            self.assertTrue(register(self.db, vision, 0, Event(), "S01", "Alex", "Computing"))
            self.assertEqual(preview.call_count, 2)
        self.assertEqual(len(list(dataset.rglob("*.jpg"))), 1)
        with (
            patch("src.train_encodings.DATASET", dataset),
            patch("src.train_encodings.ENCODINGS", self.root / "encodings"),
        ):
            with self.assertRaisesRegex(ValueError, "No usable"):
                vision.detect.side_effect = None
                vision.detect.return_value = []
                vision.backend = "opencv"
                train(self.db, vision, Event(), lambda _: None)
            vision.detect.return_value = [face]
            vision.encode.return_value = np.eye(1, 128, dtype=np.float32)[0]
            train(self.db, vision, Event(), lambda _: None)
            vectors, ids = load_index("opencv")
            self.assertEqual(vectors.shape, (1, 128))
            self.assertEqual(ids.tolist(), ["S01"])

    def test_recognition_rejects_unknown_and_marks_confirmed_face_once(self):
        self.db.add_user("S01", "Alex", "Computing")
        face = Face((10, 10, 20, 20), None)
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        vector = np.eye(1, 128, dtype=np.float32)[0]
        messages = []
        with (
            patch("src.recognize.webcam"),
            patch("src.recognize.read_frame", return_value=frame),
            patch("src.recognize.show_frame") as preview,
            patch("src.recognize.load_index", return_value=(vector[None, :], ["S01"])),
            patch("src.recognize.Vision") as detector,
        ):
            vision = detector.return_value
            vision.backend = "opencv"
            vision.detect.return_value = [face]
            for embedding in (-vector, vector, vector):
                vision.encode.return_value = embedding
                preview.side_effect = [0] * 6 + [ord("q")]
                recognize(self.db, vision, 0, Event(), messages.append)
                if embedding is not vector:
                    self.assertEqual(self.db.get_attendance(), [])
        self.assertEqual(messages, ["S01: Marked today", "S01: Already marked"])
        self.assertEqual(len(self.db.get_attendance()), 1)

    def test_missing_index_explains_recovery(self):
        with patch("src.train_encodings.ENCODINGS", self.root):
            with self.assertRaisesRegex(ValueError, "Generate encodings"):
                load_index("opencv")

    def test_unavailable_camera(self):
        from src.camera import webcam
        with patch.object(cv2, "VideoCapture") as factory, patch.object(cv2, "destroyAllWindows"):
            device = factory.return_value
            device.isOpened.return_value = False
            with self.assertRaisesRegex(RuntimeError, "Could not open camera"):
                with webcam(99, "Unavailable camera"):
                    self.fail("Camera should not have opened.")
            device.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
