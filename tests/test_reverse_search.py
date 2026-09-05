import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import requests

import reverse_search as rs


FAKE_LENS_RESPONSE = {
    "visual_matches": [
        {"title": "Random blog post", "link": "https://someblog.example.com/post/1", "source": "someblog.example.com"},
        {"title": "Jane on Instagram", "link": "https://www.instagram.com/p/abc123/", "source": "instagram.com"},
        {"title": "Stock photo site", "link": "https://stock.example.com/img/9", "source": "stock.example.com"},
        # a domain designed to trip up a naive substring check
        {"title": "Phishing lookalike", "link": "https://evil.example.com/instagram.com-login", "source": "evil.example.com"},
    ]
}


class TestDomainMatching(unittest.TestCase):
    """Covers the netloc-based social-domain check (fixes a substring-match
    false positive the first version had)."""

    def test_real_social_links_match(self):
        self.assertTrue(rs._is_social_domain("https://www.instagram.com/p/abc123/"))
        self.assertTrue(rs._is_social_domain("https://m.facebook.com/someone"))
        self.assertTrue(rs._is_social_domain("https://x.com/someone"))
        self.assertTrue(rs._is_social_domain("https://www.linkedin.com/in/someone"))

    def test_lookalike_domain_does_not_match(self):
        # "instagram.com" appears as a substring of the path, not the host --
        # must NOT be treated as a social match.
        self.assertFalse(rs._is_social_domain("https://evil.example.com/instagram.com-login"))
        self.assertFalse(rs._is_social_domain("https://not-really-facebook.com/x"))

    def test_bare_domain_matches(self):
        self.assertTrue(rs._is_social_domain("https://instagram.com/p/abc"))


class TestReverseSearch(unittest.TestCase):
    def test_missing_api_key_raises_clear_error(self):
        # reverse_search.py now calls load_dotenv() at import time (fixes a
        # real bug: running `python src/reverse_search.py <img>` standalone
        # used to ignore .env entirely). That means a real .env with a real
        # SERPAPI_KEY -- exactly what exists in this project once you've set
        # one up -- would otherwise leak into this "no key configured" test
        # via os.environ. Explicitly blank it out so this test verifies the
        # no-key code path regardless of what's in the real environment.
        with mock.patch.dict(os.environ, {"SERPAPI_KEY": ""}, clear=False):
            with self.assertRaises(rs.ReverseSearchError):
                rs.reverse_image_search("https://example.com/x.jpg", api_key=None)

    def test_filters_to_social_matches_only_and_rejects_lookalikes(self):
        with mock.patch("reverse_search.requests.get") as mget:
            mget.return_value.raise_for_status = lambda: None
            mget.return_value.json = lambda: FAKE_LENS_RESPONSE
            mget.return_value.status_code = 200
            matches = rs.reverse_image_search("https://example.com/face.jpg", api_key="fake")

        social = [m for m in matches if m.is_social]
        self.assertEqual(len(social), 1)
        self.assertIn("instagram.com", social[0].link)

    def test_no_social_match_raises(self):
        no_social_response = {"visual_matches": [FAKE_LENS_RESPONSE["visual_matches"][0]]}
        with mock.patch("reverse_search.requests.post") as mpost, mock.patch("reverse_search.requests.get") as mget:
            mpost.return_value.raise_for_status = lambda: None
            mpost.return_value.text = "https://files.catbox.moe/x.jpg"
            mpost.return_value.status_code = 200
            mget.return_value.raise_for_status = lambda: None
            mget.return_value.json = lambda: no_social_response
            mget.return_value.status_code = 200
            with self.assertRaises(rs.ReverseSearchError):
                rs.find_social_match(str(ROOT / "sample_images" / ".gitkeep"), api_key="fake")

    def test_find_social_match_end_to_end_mocked(self):
        with mock.patch("reverse_search.requests.post") as mpost, mock.patch("reverse_search.requests.get") as mget:
            mpost.return_value.raise_for_status = lambda: None
            mpost.return_value.text = "https://files.catbox.moe/abc123.jpg"
            mpost.return_value.status_code = 200
            mget.return_value.raise_for_status = lambda: None
            mget.return_value.json = lambda: FAKE_LENS_RESPONSE
            mget.return_value.status_code = 200

            match = rs.find_social_match(str(ROOT / "sample_images" / ".gitkeep"), api_key="fake")
            self.assertTrue(match.is_social)
            self.assertIn("instagram.com", match.link)
            self.assertFalse(match.mock)

    def test_retries_on_transient_failure_then_succeeds(self):
        """A 503 followed by a 200 should succeed without raising, and
        should not sleep for long (patch time.sleep to keep tests fast)."""
        good_resp = mock.Mock(status_code=200)
        good_resp.raise_for_status = lambda: None
        good_resp.json = lambda: FAKE_LENS_RESPONSE
        bad_resp = mock.Mock(status_code=503)

        with mock.patch("reverse_search.requests.get", side_effect=[bad_resp, good_resp]), \
             mock.patch("reverse_search.time.sleep"):
            matches = rs.reverse_image_search("https://example.com/x.jpg", api_key="fake")
        self.assertTrue(any(m.is_social for m in matches))

    def test_gives_up_after_max_retries(self):
        always_bad = mock.Mock(status_code=503)
        with mock.patch("reverse_search.requests.get", return_value=always_bad), \
             mock.patch("reverse_search.time.sleep"):
            with self.assertRaises(rs.ReverseSearchError):
                rs.reverse_image_search("https://example.com/x.jpg", api_key="fake")


FAKE_LENS_RESPONSE_WITH_THUMBS = {
    "visual_matches": [
        {"title": "Random blog post", "link": "https://someblog.example.com/post/1", "source": "someblog.example.com"},
        {"title": "Someone on Instagram", "link": "https://www.instagram.com/p/abc123/", "source": "instagram.com", "thumbnail": "https://example.com/thumb1.jpg"},
        {"title": "Someone else on LinkedIn", "link": "https://www.linkedin.com/in/other/", "source": "linkedin.com", "thumbnail": "https://example.com/thumb2.jpg"},
    ]
}


class TestFaceVerification(unittest.TestCase):
    """Covers the face-verification cross-check added to find_social_match:
    a Lens/Bing "visually similar" hit is only ever reported as a confirmed
    match when its own face actually matches the query photo's face
    encoding. This is the fix for the false positives seen in real testing
    (an unrelated LinkedIn profile, an unrelated YouTube video, an
    unrelated Instagram post all being reported as "the match")."""

    def _mock_search_call(self, mpost, mget):
        mpost.return_value.raise_for_status = lambda: None
        mpost.return_value.text = "https://files.catbox.moe/abc123.jpg"
        mpost.return_value.status_code = 200
        mget.return_value.raise_for_status = lambda: None
        mget.return_value.json = lambda: FAKE_LENS_RESPONSE_WITH_THUMBS
        mget.return_value.status_code = 200

    def test_verifies_matching_candidate_and_returns_it(self):
        """A candidate whose face distance is within threshold is returned
        with verified=True -- this is the "real match found" case."""
        with mock.patch("reverse_search.requests.post") as mpost, \
             mock.patch("reverse_search.requests.get") as mget, \
             mock.patch("reverse_search._thumbnail_encoding", return_value=[0.1, 0.2, 0.3]), \
             mock.patch("reverse_search.face_id.compare", return_value=0.35):
            self._mock_search_call(mpost, mget)
            match = rs.find_social_match(
                str(ROOT / "sample_images" / ".gitkeep"),
                api_key="fake",
                query_encoding=[0.0, 0.0, 0.0],
            )
        self.assertTrue(match.verified)
        self.assertAlmostEqual(match.face_distance, 0.35)
        self.assertIn("instagram.com", match.link)

    def test_no_verified_candidate_returns_closest_as_unverified(self):
        """When no candidate's face is close enough, the closest one is
        still returned (something concrete to show) but honestly marked
        verified=False -- this is exactly the case that used to silently
        report a random visual lookalike as if it were a real match."""
        with mock.patch("reverse_search.requests.post") as mpost, \
             mock.patch("reverse_search.requests.get") as mget, \
             mock.patch("reverse_search._thumbnail_encoding", side_effect=[[0.1] * 5, [0.9] * 5]), \
             mock.patch("reverse_search.face_id.compare", side_effect=[0.8, 0.65]):
            self._mock_search_call(mpost, mget)
            match = rs.find_social_match(
                str(ROOT / "sample_images" / ".gitkeep"),
                api_key="fake",
                query_encoding=[0.0] * 5,
            )
        self.assertFalse(match.verified)
        self.assertAlmostEqual(match.face_distance, 0.65)
        self.assertIn("linkedin.com", match.link)

    def test_no_usable_face_falls_back_to_first_social_match_unverified(self):
        """If no candidate's thumbnail yields a usable face at all, fall
        back to the original (pre-verification) behavior rather than
        crashing or returning nothing."""
        with mock.patch("reverse_search.requests.post") as mpost, \
             mock.patch("reverse_search.requests.get") as mget, \
             mock.patch("reverse_search._thumbnail_encoding", return_value=None):
            self._mock_search_call(mpost, mget)
            match = rs.find_social_match(
                str(ROOT / "sample_images" / ".gitkeep"),
                api_key="fake",
                query_encoding=[0.0] * 5,
            )
        self.assertFalse(match.verified)
        self.assertIsNone(match.face_distance)
        self.assertIn("instagram.com", match.link)

    def test_no_query_encoding_keeps_old_behavior(self):
        """Omitting query_encoding must behave exactly like before this
        feature existed -- required for backward compatibility."""
        with mock.patch("reverse_search.requests.post") as mpost, \
             mock.patch("reverse_search.requests.get") as mget:
            self._mock_search_call(mpost, mget)
            match = rs.find_social_match(
                str(ROOT / "sample_images" / ".gitkeep"),
                api_key="fake",
            )
        self.assertFalse(match.verified)
        self.assertIsNone(match.face_distance)
        self.assertIn("instagram.com", match.link)

    def test_thumbnail_encoding_returns_none_on_download_failure(self):
        """Network/decoding failures while fetching a candidate's thumbnail
        must never raise -- just mean "can't verify this one"."""
        with mock.patch("reverse_search.requests.get", side_effect=requests.exceptions.ConnectionError("boom")), \
             mock.patch("reverse_search.time.sleep"):
            self.assertIsNone(rs._thumbnail_encoding("https://example.com/bad.jpg"))


class TestMockProvider(unittest.TestCase):
    """The offline rehearsal mode -- must never be mistaken for a real result."""

    def test_mock_search_needs_no_network(self):
        matches = rs.mock_search()
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].mock)
        self.assertIn("[MOCK]", matches[0].title)

    def test_find_social_match_mock_provider(self):
        match = rs.find_social_match(str(ROOT / "sample_images" / ".gitkeep"), provider="mock")
        self.assertTrue(match.mock)
        self.assertIn("[MOCK]", match.title)

    def test_unknown_provider_raises(self):
        with self.assertRaises(rs.ReverseSearchError):
            rs.find_social_match(str(ROOT / "sample_images" / ".gitkeep"), provider="not-a-real-provider")


if __name__ == "__main__":
    unittest.main()
