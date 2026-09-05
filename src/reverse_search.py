"""
reverse_search.py
==================
Stage 2 of the pipeline: take the cropped face image from stage 1 and run a
*real* reverse-image search against the web to find a matching social media
post. This is a genuine network search step -- nothing here is hardcoded or
pre-picked; the results depend entirely on what the search engine returns
for the given image.

Two real providers, selected with SEARCH_PROVIDER in .env (default: serpapi),
plus a mock provider for rehearsal:

  "serpapi" (default) -- upload the face crop to catbox.moe (free, no key)
      to get a public URL, then call SerpApi's Google Lens engine
      (https://serpapi.com/search.json?engine=google_lens) with that URL.
      Needs SERPAPI_KEY (free tier: 100 searches/month).

  "bing" -- call Azure's Bing Visual Search API directly with the image
      bytes (no public-URL upload step needed). Needs AZURE_BING_KEY.
      Use this if you run out of SerpApi quota, or just prefer it.

  "mock" -- returns a clearly-labeled fake result with no network calls at
      all. For rehearsing the pipeline/CLI/demo flow only -- NEVER use this
      for your actual submission recording, the task requires a genuine
      search. Every mock result is tagged so it's impossible to mistake for
      a real one (title is prefixed "[MOCK]" and `mock=True` on the result).

All outbound requests retry with exponential backoff on transient failures
(timeouts, connection errors, 429/5xx) before giving up.

Face verification (why this file also imports face_id)
--------------------------------------------------------
An image-similarity engine like Google Lens returns whatever it considers
*visually* similar -- similar colors, composition, lighting -- which is not
the same thing as "the same person's face". In testing, a generic outdoor
portrait returned an unrelated stranger's LinkedIn profile, then an
unrelated travel video, then an unrelated Instagram post -- three different
real searches, three visually-plausible but wrong answers, with nothing on
our side to say so.

So when the caller (pipeline.py) has the query face's own encoding on hand,
`find_social_match` now cross-checks it: for each social-domain candidate
Lens returns, it downloads the candidate's thumbnail, runs it through the
*same* face_id detection+encoding used on the original photo, and compares
the two encodings with the standard face-recognition distance metric. Only
a candidate whose face is actually close enough (distance <= threshold) is
reported as `verified=True`. If no candidate passes, the closest one is
still returned (so the demo/recording has something concrete to show) but
clearly marked `verified=False` -- an honest "nearest visual candidate,
not confirmed to be the same person" rather than a false positive dressed
up as a match.

This costs no extra API key or paid service -- it reuses the dlib model
already integrated for stage 1. The 0.6 distance threshold is the standard
value documented by the face_recognition/dlib project for "same person";
it's most meaningful for the dlib backend. If face_id falls back to the
classical OpenCV/HOG encoder (no dlib installed), verification still runs
but is a weaker signal -- said plainly in the code, not hidden.
"""
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent))
import face_id

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
CATBOX_ENDPOINT = "https://catbox.moe/user/api.php"
BING_VISUAL_SEARCH_ENDPOINT = "https://api.bing.microsoft.com/v7.0/images/visualsearch"

SOCIAL_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "tiktok.com",
    "reddit.com",
    "pinterest.com",
    "youtube.com",
    "threads.net",
    "github.com",
]

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Standard threshold documented by the face_recognition/dlib project: two
# encodings closer than this (Euclidean distance) are considered the same
# person. Most meaningful for the dlib backend -- see module docstring.
DEFAULT_FACE_MATCH_THRESHOLD = 0.6


class ReverseSearchError(RuntimeError):
    pass


@dataclass
class SearchMatch:
    title: str
    link: str
    source: str
    thumbnail: Optional[str] = None
    is_social: bool = False
    mock: bool = False
    # Face-verification outcome (only meaningful when the caller supplied a
    # query_encoding to find_social_match -- otherwise left at these
    # defaults, matching the pre-verification behavior).
    verified: bool = False
    face_distance: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "link": self.link,
            "source": self.source,
            "thumbnail": self.thumbnail,
            "is_social": self.is_social,
            "mock": self.mock,
            "verified": self.verified,
            "face_distance": self.face_distance,
        }


def _is_social_domain(link: str) -> bool:
    """Domain check done properly with urlparse, not a substring search.
    A naive `"instagram.com" in link` would wrongly flag something like
    https://evil.example/instagram.com-phishing as social. This checks the
    actual host, so it only matches the real domain or a real subdomain of
    it (e.g. www.instagram.com, m.facebook.com)."""
    try:
        from urllib.parse import urlparse
        netloc = urlparse(link).netloc.lower()
    except Exception:
        return False
    netloc = netloc.split("@")[-1]  # drop userinfo if present
    netloc = netloc.split(":")[0]  # drop port if present
    return any(netloc == d or netloc.endswith("." + d) for d in SOCIAL_DOMAINS)


def _domain_from_link(link: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(link).netloc or link
    except Exception:
        return link


def _with_retries(request_fn: Callable[[], requests.Response], *, retries: int = 3, base_delay: float = 1.0) -> requests.Response:
    """Call `request_fn` (a zero-arg callable that performs one HTTP call),
    retrying with exponential backoff on network errors or a retryable
    status code. Raises the last error if every attempt fails."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = request_fn()
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            resp = None

        if resp is not None:
            if resp.status_code not in RETRYABLE_STATUS_CODES:
                return resp
            last_exc = ReverseSearchError(f"HTTP {resp.status_code} from {resp.url}")

        if attempt < retries:
            time.sleep(base_delay * (2 ** (attempt - 1)))

    assert last_exc is not None
    raise last_exc


def upload_public(image_path: str, timeout: int = 30) -> str:
    """Upload an image to catbox.moe and return its public URL.
    No API key required. Files are hosted publicly and indefinitely by
    catbox -- only ever upload an image you have the right to share
    (e.g. your own face), see README ethics/consent note."""

    def _do_upload() -> requests.Response:
        with open(image_path, "rb") as f:
            return requests.post(
                CATBOX_ENDPOINT,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=timeout,
            )

    resp = _with_retries(_do_upload)
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise ReverseSearchError(f"catbox.moe upload failed: {url}")
    return url


def reverse_image_search(image_url: str, api_key: Optional[str] = None, timeout: int = 30) -> List[SearchMatch]:
    """Run a real Google Lens reverse-image search via SerpApi and return
    every visual match it finds. Raises ReverseSearchError if no API key is
    configured or the request fails -- this function never returns a
    fabricated/hardcoded result."""
    api_key = api_key or os.environ.get("SERPAPI_KEY")
    if not api_key or api_key == "your_serpapi_key_here":
        raise ReverseSearchError(
            "SERPAPI_KEY is not set. Get a free key at https://serpapi.com/ "
            "and put it in your .env file before running a real search."
        )

    params = {"engine": "google_lens", "url": image_url, "api_key": api_key}
    resp = _with_retries(lambda: requests.get(SERPAPI_ENDPOINT, params=params, timeout=timeout))
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ReverseSearchError(f"SerpApi error: {data['error']}")

    raw_matches = data.get("visual_matches", []) or data.get("image_results", [])
    matches: List[SearchMatch] = []
    for item in raw_matches:
        link = item.get("link", "")
        source = item.get("source", "") or _domain_from_link(link)
        matches.append(
            SearchMatch(
                title=item.get("title", ""),
                link=link,
                source=source,
                thumbnail=item.get("thumbnail"),
                is_social=_is_social_domain(link),
            )
        )
    return matches


def bing_visual_search(image_path: str, api_key: Optional[str] = None, timeout: int = 30) -> List[SearchMatch]:
    """Alternative provider: Azure's Bing Visual Search API. Sends the image
    bytes directly -- no public-URL upload step needed. Requires
    AZURE_BING_KEY (Azure Cognitive Services -> Bing Search v7)."""
    api_key = api_key or os.environ.get("AZURE_BING_KEY")
    if not api_key:
        raise ReverseSearchError(
            "AZURE_BING_KEY is not set. Create a free Azure Bing Search resource and "
            "put the key in your .env file, or use SEARCH_PROVIDER=serpapi instead."
        )

    def _do_search() -> requests.Response:
        with open(image_path, "rb") as f:
            return requests.post(
                BING_VISUAL_SEARCH_ENDPOINT,
                headers={"Ocp-Apim-Subscription-Key": api_key},
                files={"image": f},
                timeout=timeout,
            )

    resp = _with_retries(_do_search)
    resp.raise_for_status()
    data = resp.json()

    matches: List[SearchMatch] = []
    for tag in data.get("tags", []):
        for action in tag.get("actions", []):
            if action.get("actionType") not in ("PagesIncluding", "VisualSearch"):
                continue
            for item in action.get("data", {}).get("value", []):
                link = item.get("hostPageUrl", "") or item.get("contentUrl", "")
                matches.append(
                    SearchMatch(
                        title=item.get("name", ""),
                        link=link,
                        source=_domain_from_link(link),
                        thumbnail=item.get("thumbnailUrl"),
                        is_social=_is_social_domain(link),
                    )
                )
    return matches


def mock_search() -> List[SearchMatch]:
    """No network calls. Returns one clearly-labeled fake match so you can
    rehearse the CLI flow (and the rest of the pipeline) without spending a
    real search or needing internet. Never use this for your submission --
    every result it returns is tagged mock=True and titled "[MOCK] ..." so
    it can't accidentally pass as a genuine finding."""
    return [
        SearchMatch(
            title="[MOCK] Example profile post (rehearsal only, not a real search result)",
            link="https://www.instagram.com/p/mock_example_not_real/",
            source="instagram.com",
            thumbnail=None,
            is_social=True,
            mock=True,
        )
    ]


def _download_bytes(url: str, timeout: int = 15) -> bytes:
    resp = _with_retries(lambda: requests.get(url, timeout=timeout), retries=2)
    resp.raise_for_status()
    return resp.content


def _thumbnail_encoding(thumbnail_url: str) -> Optional[List[float]]:
    """Download a candidate's thumbnail and run it through the same
    face_id detection+encoding used on the query photo. Returns None (never
    raises) if the thumbnail can't be fetched, isn't a valid image, or has
    no detectable face -- any of those just mean "can't verify this
    particular candidate", not a pipeline failure."""
    tmp_path = None
    try:
        image_bytes = _download_bytes(thumbnail_url)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        record = face_id.process_image(tmp_path)
        return record.encoding
    except Exception:
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def find_social_match(
    image_path: str,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    query_encoding: Optional[List[float]] = None,
    verify_threshold: float = DEFAULT_FACE_MATCH_THRESHOLD,
) -> SearchMatch:
    """Full stage-2 entry point used by the pipeline: get matches from the
    configured provider (SEARCH_PROVIDER in .env, default "serpapi") and
    return a matching social media post. Raises ReverseSearchError if no
    social-domain result is found at all -- the task requires a genuine
    search, so we don't fall back to a fake one (except in explicit "mock"
    provider mode, which is clearly labeled as such).

    If `query_encoding` is provided (the face encoding from stage 1),
    every social candidate is face-verified against it (see module
    docstring) before being returned:
      - the first candidate whose face distance is <= verify_threshold is
        returned with verified=True and face_distance set.
      - if none pass, the single closest candidate is still returned (so
        there's something concrete for the demo/record) but with
        verified=False -- an honest "nearest candidate, not confirmed" --
        rather than silently reporting a random visual lookalike as if it
        were a real match.

    If `query_encoding` is omitted, behavior is unchanged from before this
    verification feature existed: the first social-domain result is
    returned as-is (verified=False, face_distance=None)."""
    provider = (provider or os.environ.get("SEARCH_PROVIDER", "serpapi")).lower()

    if provider == "mock":
        matches = mock_search()
    elif provider == "bing":
        matches = bing_visual_search(image_path, api_key=api_key)
    elif provider == "serpapi":
        public_url = upload_public(image_path)
        matches = reverse_image_search(public_url, api_key=api_key)
    else:
        raise ReverseSearchError(f"Unknown SEARCH_PROVIDER: {provider!r} (expected serpapi, bing, or mock)")

    social_matches = [m for m in matches if m.is_social]

    if not social_matches:
        raise ReverseSearchError(
            f"Reverse search ran successfully ({len(matches)} results, provider={provider}) but none "
            "were on a recognized social media domain. Try a more distinctive "
            "photo, or widen SOCIAL_DOMAINS in reverse_search.py."
        )

    if query_encoding is None:
        return social_matches[0]

    best_match: Optional[SearchMatch] = None
    best_distance: Optional[float] = None

    for candidate in social_matches:
        if not candidate.thumbnail:
            continue
        candidate_encoding = _thumbnail_encoding(candidate.thumbnail)
        if candidate_encoding is None:
            continue  # no usable face in this candidate's thumbnail -- skip it

        distance = face_id.compare(query_encoding, candidate_encoding)
        if best_distance is None or distance < best_distance:
            best_match, best_distance = candidate, distance

        if distance <= verify_threshold:
            candidate.verified = True
            candidate.face_distance = distance
            return candidate

    # No candidate's face was close enough to count as verified. Report the
    # closest one honestly, rather than either silently lying (returning it
    # unmarked) or refusing to show anything at all.
    if best_match is not None:
        best_match.verified = False
        best_match.face_distance = best_distance
        return best_match

    # No candidate had a thumbnail we could even extract a face from --
    # fall back to the original (pre-verification) behavior.
    social_matches[0].verified = False
    return social_matches[0]


if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Usage: python reverse_search.py <face_crop_image_path> [--mock]")
        sys.exit(1)

    provider = "mock" if "--mock" in sys.argv else None
    match = find_social_match(sys.argv[1], provider=provider)
    print(json.dumps(match.to_dict(), indent=2))
