import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import skimage.data as skdata

import face_id


class TestFaceId(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = ROOT / "tests" / "_tmp"
        cls.tmp_dir.mkdir(exist_ok=True)
        cls.image_path = str(cls.tmp_dir / "face.jpg")
        img_rgb = skdata.astronaut()  # bundled sample photo with a clear frontal face
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite(cls.image_path, img_bgr)

    def test_detects_a_face(self):
        record = face_id.process_image(self.image_path)
        x, y, w, h = record.bbox
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_encoding_is_deterministic(self):
        r1 = face_id.process_image(self.image_path)
        r2 = face_id.process_image(self.image_path)
        self.assertEqual(r1.fingerprint, r2.fingerprint)
        self.assertEqual(face_id.compare(r1.encoding, r2.encoding), 0.0)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            face_id.process_image(str(self.tmp_dir / "does_not_exist.jpg"))

    def test_crop_face_writes_a_smaller_image(self):
        record = face_id.process_image(self.image_path)
        crop_path = str(self.tmp_dir / "crop.jpg")
        face_id.crop_face(self.image_path, record.bbox, crop_path)
        self.assertTrue(Path(crop_path).exists())
        full = cv2.imread(self.image_path)
        crop = cv2.imread(crop_path)
        self.assertLess(crop.shape[0] * crop.shape[1], full.shape[0] * full.shape[1])

    def test_draw_bbox_writes_same_size_annotated_image(self):
        record = face_id.process_image(self.image_path)
        out_path = str(self.tmp_dir / "annotated.jpg")
        face_id.draw_bbox(self.image_path, record.bbox, out_path)
        self.assertTrue(Path(out_path).exists())
        original = cv2.imread(self.image_path)
        annotated = cv2.imread(out_path)
        self.assertEqual(original.shape, annotated.shape)
        # the box changes some pixels -- annotated image should differ from the original
        self.assertFalse((original == annotated).all())

    def test_multiple_faces_uses_largest(self):
        """Regression test: face_recognition.face_locations() does not sort
        by size, so process_image() used to just take whichever face dlib
        listed first (locations[0]) -- silently fingerprinting the wrong
        person on any photo with more than one face. It must pick the
        largest (closest-to-camera) face instead, matching the classical
        fallback's behavior."""
        fake_locations = [
            (10, 60, 60, 10),   # small face: 50x50 = 2500
            (0, 200, 200, 0),   # large face: 200x200 = 40000 -- must be picked
            (5, 90, 85, 5),     # medium face: 80x85 = 6800
        ]
        with mock.patch.object(face_id, "_HAS_FACE_RECOGNITION", True), \
             mock.patch.object(face_id, "face_recognition", create=True) as mock_fr:
            mock_fr.face_locations.return_value = fake_locations
            mock_fr.face_encodings.return_value = [np.zeros(128)]
            record = face_id.process_image(self.image_path)

        # bbox is (left, top, width, height); the large face's box is
        # (top=0, right=200, bottom=200, left=0) -> bbox (0, 0, 200, 200).
        self.assertEqual(record.bbox, (0, 0, 200, 200))
        called_locations = mock_fr.face_encodings.call_args.kwargs["known_face_locations"]
        self.assertEqual(called_locations, [(0, 200, 200, 0)])


if __name__ == "__main__":
    unittest.main()
