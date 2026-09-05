import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from simple_chain import SimpleChain


class TestSimpleChain(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = ROOT / "tests" / "_tmp"
        self.tmp_dir.mkdir(exist_ok=True)
        self.chain_file = self.tmp_dir / "chain_test.json"
        self.chain_file.unlink(missing_ok=True)
        self.chain = SimpleChain(chain_file=str(self.chain_file), difficulty=2)  # low difficulty for fast tests

    def test_genesis_block_created(self):
        self.assertEqual(len(self.chain.blocks), 1)
        self.assertTrue(self.chain.blocks[0].data.get("genesis"))

    def test_add_and_verify_record(self):
        data = {"face_fingerprint": "abc123", "social_post_url": "https://instagram.com/p/x"}
        block = self.chain.add_record(data)
        self.assertEqual(block.index, 1)

        ok, reason = self.chain.verify_chain()
        self.assertTrue(ok, reason)

        found = self.chain.find_record("abc123")
        self.assertIsNotNone(found)
        self.assertEqual(found.data, data)

        verified, block_found, msg = self.chain.verify_record(data)
        self.assertTrue(verified, msg)

    def test_tampering_is_detected(self):
        data = {"face_fingerprint": "def456", "social_post_url": "https://instagram.com/p/y"}
        self.chain.add_record(data)

        # simulate an attacker directly editing the ledger file on disk
        raw = json.loads(self.chain_file.read_text())
        raw[-1]["data"]["social_post_url"] = "https://instagram.com/p/FAKE"
        self.chain_file.write_text(json.dumps(raw, indent=2))

        tampered = SimpleChain(chain_file=str(self.chain_file), difficulty=2)
        ok, reason = tampered.verify_chain()
        self.assertFalse(ok)
        self.assertIn("hash mismatch", reason)

    def test_verify_record_uses_most_recent_block_for_a_reanchored_face(self):
        """Real bug found on 2026-09-05: re-running the pipeline on the same
        photo (e.g. after fixing the search step) anchors a NEW block that
        shares the same face_fingerprint as an older block from an earlier
        run. verify_record() must check the record against the most recent
        anchor for that face, not the first one it happens to find scanning
        from the genesis block forward -- otherwise a perfectly correct,
        freshly-mined block gets reported as a false "tampered or wrong
        input" mismatch against stale old data."""
        old_data = {"face_fingerprint": "same-face-abc", "social_post_url": "https://example.com/wrong-old-match"}
        self.chain.add_record(old_data)

        new_data = {"face_fingerprint": "same-face-abc", "social_post_url": "https://example.com/correct-new-match"}
        new_block = self.chain.add_record(new_data)

        found = self.chain.find_record("same-face-abc")
        self.assertIs(found, new_block)

        ok, block, msg = self.chain.verify_record(new_data)
        self.assertTrue(ok, msg)
        self.assertEqual(block.index, new_block.index)

    def test_verify_record_rejects_mismatched_data(self):
        data = {"face_fingerprint": "ghi789", "social_post_url": "https://instagram.com/p/z"}
        self.chain.add_record(data)

        wrong_data = dict(data)
        wrong_data["social_post_url"] = "https://instagram.com/p/NOT-THE-SAME"
        verified, block_found, msg = self.chain.verify_record(wrong_data)
        self.assertFalse(verified)

    def test_persistence_across_instances(self):
        data = {"face_fingerprint": "jkl000", "social_post_url": "https://instagram.com/p/persist"}
        self.chain.add_record(data)

        reloaded = SimpleChain(chain_file=str(self.chain_file), difficulty=2)
        self.assertEqual(len(reloaded.blocks), len(self.chain.blocks))
        self.assertIsNotNone(reloaded.find_record("jkl000"))

    def test_verify_is_correct_regardless_of_instance_difficulty(self):
        """Regression test: a chain mined at one difficulty must still
        verify as valid when re-opened with a SimpleChain constructed at a
        *different* difficulty setting (e.g. the CLI's `list` command uses
        the default difficulty, but the file might have been mined at a
        lower one, like this test does). Each block's own recorded
        difficulty is what verification checks, not the instance's."""
        data = {"face_fingerprint": "mno111", "social_post_url": "https://instagram.com/p/diff-mismatch"}
        self.chain.add_record(data)  # mined at difficulty=2

        reopened_at_higher_difficulty = SimpleChain(chain_file=str(self.chain_file), difficulty=6)
        ok, reason = reopened_at_higher_difficulty.verify_chain()
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
