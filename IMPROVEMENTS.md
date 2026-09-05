# Improvements made in this revision

Everything below was added or fixed on top of the first working version.
Test count went from 13 to 26 (all passing). Grouped by why it matters.

## Real bugs fixed (not just polish)

1. **Blockchain proof-of-work difficulty wasn't persisted per block.**
   `SimpleChain.verify_chain()` used to check every block against
   whatever `difficulty` the *current* `SimpleChain(...)` instance was
   constructed with — not what the block was actually mined at. That meant
   opening a chain file with a different difficulty setting than it was
   written with (which is exactly what the new `simple_chain.py list`
   inspector does, since it doesn't know your original setting) could
   report a perfectly valid chain as broken. Fixed by storing the
   difficulty on each block itself (and hashing it as part of the block),
   so verification always checks a block against the difficulty it was
   actually mined at. Covered by
   `test_verify_is_correct_regardless_of_instance_difficulty`.

2. **Social-domain matching used a naive substring check.** The original
   code did `"instagram.com" in link.lower()`, which a URL like
   `https://evil.example.com/instagram.com-login` would incorrectly pass
   as a real Instagram match. Replaced with proper URL parsing
   (`urlparse(link).netloc`) checked for an exact or subdomain match
   against the real domain. Covered by `TestDomainMatching` (3 new tests,
   including the lookalike-URL case).

## New capabilities

3. **Offline rehearsal mode (`--mock`).** `python src/pipeline.py <photo>
   --mock` runs real face detection and a real blockchain write, but stage
   2 returns one clearly-labeled fake result instead of hitting the
   network — no API key, no internet, no spent search quota. Every mock
   result carries `mock: true` and a `[MOCK]` title prefix so it can never
   be confused with a genuine finding, and the CLI prints a loud banner
   while it's active. This is what let me actually run the *entire*
   pipeline end-to-end for real in this build environment (which has no
   outbound internet) instead of only testing stages 1 and 3 separately —
   and it gives you a fast way to rehearse the exact CLI flow before
   spending real SerpApi credits.

4. **A second search provider: Bing Visual Search** (`SEARCH_PROVIDER=bing`
   in `.env`). Directly addresses the "100 free searches/month" limitation
   called out before — if you burn through SerpApi's quota, or just prefer
   Bing, switch providers with one .env line. Bonus: Bing takes the image
   bytes directly, so it skips the catbox.moe public-upload step entirely.

5. **Standalone re-verification (`src/verify.py`).** Re-checks a record
   `pipeline.py` already anchored, using only the deterministic, offline
   part of stage 1 (recompute the face fingerprint) plus the on-chain
   check — no web search, no re-mining. This is the "prove this wasn't
   edited after the fact" moment as its own runnable thing, independent
   of re-doing the whole pipeline — useful to show in the recording as a
   second, later step.

6. **Blockchain ledger inspector (`python src/simple_chain.py list`).**
   Pretty-prints every block in `chain.json` — hash, previous hash, nonce,
   the anchored data — so you (or a judge) can actually look at the chain
   instead of taking "it's on a blockchain" on faith.

7. **Face-detection visualization (`--visualize out.jpg`)**, on `face_id.py`
   directly and wired into `pipeline.py --visualize`. Draws a box around
   the detected face and saves it. Gives the recording something visual
   for stage 1 instead of only a JSON blob scrolling past.

8. **Fail-fast config validation (`src/config.py`).** Before, a missing
   `SERPAPI_KEY` surfaced as an exception *after* face detection had
   already run. Now `pipeline.py` checks everything the run needs up front
   and prints one clear, actionable message immediately if something's
   missing.

9. **Retry with exponential backoff on every outbound HTTP call**
   (catbox upload, SerpApi, Bing) — a transient timeout or a 503/429
   no longer kills the run outright. Covered by tests that simulate a
   failing-then-succeeding request and one that gives up correctly after
   repeated failures.

## Engineering hygiene

10. **GitHub Actions CI** (`.github/workflows/tests.yml`) — runs the full
    test suite on every push, including a real `pip install -r
    requirements.txt`. This matters more than a typical CI add here: it's
    the first place the `face_recognition`/dlib backend actually gets
    installed and exercised end-to-end, since the sandbox this project was
    built in had no PyPI access and could only test the OpenCV/HOG
    fallback. Once you push, watch that workflow run — it's real signal
    on whether the accurate backend actually works, which I could not
    confirm myself before now.

11. **Test suite grew from 13 to 26 tests**, adding coverage for every fix
    and feature above.

12. **README rewritten** to document every new flag/script and update the
    limitations list — several previously-listed limitations are now
    fixed or have a documented workaround (search-provider quota, no
    rehearsal path, no way to inspect the chain).

13. **Fixed a real false-positive bug found by running the pipeline live
    (not in the sandbox).** Once run against real, already-public photos
    with a real SerpApi key, `find_social_match()` returned three
    different wrong answers across three separate runs — a stranger's
    LinkedIn profile, an unrelated YouTube video, and an unrelated
    Instagram post. Reading the code showed why: it simply returned the
    *first* Google Lens result on a recognized social domain, with zero
    check that the candidate image actually contained a matching face.
    Google Lens returns "visually similar" images (similar colors,
    composition, lighting), which is not the same thing as "same person."

    Fixed in `src/reverse_search.py` by reusing the dlib model already
    integrated for stage 1 (`face_id.compare`, the standard
    Euclidean-distance face-recognition metric, threshold 0.6): for every
    social-domain candidate, download its thumbnail, run it through the
    same face detection+encoding used on the original photo, and compare.
    A candidate whose face is actually close enough is returned as
    `verified=True`; otherwise the closest candidate is still shown (so
    there's something concrete for the demo) but honestly marked
    `verified=False` — a "nearest visual candidate, not confirmed" rather
    than a false positive dressed up as a match. No new dependency, no new
    API key — this was a missing verification step, not a missing model.
    `pipeline.py` now prints the verification outcome and distance for
    every run, and the on-chain record includes `face_verified` /
    `face_distance` so the blockchain entry itself is honest about whether
    the match was confirmed. Covered by 5 new tests in
    `tests/test_reverse_search.py` (verified-match case, closest-candidate
    fallback, no-usable-face fallback, backward-compatibility with no
    `query_encoding`, and thumbnail-download-failure handling) — test
    count is now 31, all passing.

## Still true from before (not re-litigated, see README "Known limitations")

- `eth_chain.py` (the real-testnet path) is unchanged and still untested
  against a live RPC endpoint — no live network access to an RPC endpoint
  has been exercised yet.
