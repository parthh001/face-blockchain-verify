import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2
import skimage.data as skdata

import face_id
import verify as verify_module
from simple_chain import SimpleChain


class TestVerify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = ROOT / "tests" / "_tmp"
        cls.tmp_dir.mkdir(exist_ok=True)
        cls.image_path = str(cls.tmp_dir / "verify_face.jpg")
        img_bgr = cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2BGR)
        cv2.imwrite(cls.image_path, img_bgr)

    def setUp(self):
        self.chain_file = str(self.tmp_dir / "verify_chain.json")
        Path(self.chain_file).unlink(missing_ok=True)

    def test_verify_fails_gracefully_with_no_chain_record(self):
        ok = verify_module.verify(self.image_path, chain_file=self.chain_file)
        self.assertFalse(ok)

    def test_verify_succeeds_after_anchoring(self):
        record = face_id.process_image(self.image_path)
        chain = SimpleChain(chain_file=self.chain_file, difficulty=2)
        chain.add_record(
            {
                "face_fingerprint": record.fingerprint,
                "social_post_url": "https://www.instagram.com/p/verify-test/",
                "discovered_at": "2026-01-01T00:00:00Z",
            }
        )

        ok = verify_module.verify(self.image_path, chain_file=self.chain_file)
        self.assertTrue(ok)

    def test_verify_detects_tampering(self):
        import json

        record = face_id.process_image(self.image_path)
        chain = SimpleChain(chain_file=self.chain_file, difficulty=2)
        chain.add_record({"face_fingerprint": record.fingerprint, "social_post_url": "https://www.instagram.com/p/original/"})

        raw = json.loads(Path(self.chain_file).read_text())
        raw[-1]["data"]["social_post_url"] = "https://www.instagram.com/p/tampered/"
        Path(self.chain_file).write_text(json.dumps(raw, indent=2))

        ok = verify_module.verify(self.image_path, chain_file=self.chain_file)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
