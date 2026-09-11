<div align="center">

# Face Identification & Blockchain Verification

### Find where a face appears online, and prove it with a blockchain record

<p>

![Python](https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Face%20Detection-5C3EE8?logo=opencv&logoColor=white)
![dlib](https://img.shields.io/badge/dlib-face__recognition-black)
![SerpApi](https://img.shields.io/badge/SerpApi-Reverse%20Image%20Search-6C47FF)
![Solidity](https://img.shields.io/badge/Solidity-Smart%20Contract-363636?logo=solidity)
![web3.py](https://img.shields.io/badge/web3.py-Polygon%20Amoy-8247E5)
![Tests](https://img.shields.io/badge/tests-32%20passing-brightgreen)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)

</p>

</div>

---

## What this does

Give it a photo of a face. It finds the face, searches the web for a matching photo already posted somewhere (Instagram, X, Facebook, LinkedIn, TikTok, Reddit), and saves proof of that match on a blockchain — so the discovery can be checked again later and can't quietly be changed.

```
photo → find & encode the face → search the web for a match → matching post found → save proof on-chain → check it again anytime
```

---

## How it works

**1. Face detection** (`src/face_id.py`) — finds the face in your photo and turns it into a set of numbers (an "encoding") plus a fingerprint hash. Uses `face_recognition` (a well-tested face model) when it's installed, and falls back to a simpler built-in method if not.

**2. Reverse image search** (`src/reverse_search.py`) — uploads the face and searches for it online (via Google Lens or Bing), then checks every result against the original face before reporting it as a match.

**3. Blockchain proof** (`src/simple_chain.py`, or `src/eth_chain.py` for a real test network) — takes the fingerprint and the matched post, saves them together as a record, and can verify that record again later. `src/verify.py` does just that re-check on its own.

Run everything together with `src/pipeline.py`.

---

## Built with

| Part | What's used |
|---|---|
| Face detection | `face_recognition` (dlib), with an OpenCV fallback |
| Web search | SerpApi (Google Lens), Bing Visual Search |
| Blockchain (default) | A local, hash-chained ledger — real cryptography, runs on your machine |
| Blockchain (optional) | Polygon Amoy test network via `web3.py` + a Solidity contract |
| Tests | `unittest`, 32 tests |
| CI | GitHub Actions |

---

## Getting started

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# add your SERPAPI_KEY (see below)
```

`requirements.txt` includes `face_recognition`, which needs a C++ compiler to install (it uses dlib). If that install fails, don't worry — `face_id.py` automatically switches to a built-in OpenCV method instead.

**Getting a SerpApi key** — sign up free at [serpapi.com](https://serpapi.com/) (100 free searches a month) and put the key in `.env` as `SERPAPI_KEY`. Prefer Bing? Set `SEARCH_PROVIDER=bing` and `AZURE_BING_KEY` instead.

---

## Using it

**Run the whole pipeline:**
```bash
python src/pipeline.py sample_images/your_photo.jpg
```

**Or run one step at a time:**
```bash
python src/face_id.py sample_images/your_photo.jpg --visualize out.jpg   # just detect the face
python src/reverse_search.py sample_images/your_photo_face_crop.jpg      # just search
python src/simple_chain.py demo                                          # see the blockchain part work
python src/verify.py sample_images/your_photo.jpg                        # check a record again later
```

**Useful flags on `pipeline.py`:**
```bash
--chain testnet       # use the real test network instead of the local one
--provider bing       # search with Bing instead of SerpApi
--mock                # practice run, no real search
--visualize out.jpg   # save a photo with the face marked
--out result.json     # save the full result as JSON
```

If a key or setting is missing, it tells you right away instead of failing partway through.

---

## Running the tests

```bash
python -m unittest discover -s tests -v
```

These run automatically on every push, including a full install of `dlib`, so the real face-matching path gets tested every time — not just the fallback.

---

## Project layout

```text
src/
├── config.py            loads settings from .env, fails fast if something's missing
├── face_id.py            step 1: find and encode the face
├── reverse_search.py      step 2: search the web, filter to real matches
├── simple_chain.py         step 3 (default): local blockchain
├── eth_chain.py             step 3 (optional): real test network
├── pipeline.py               runs all three steps
└── verify.py                  checks a saved record again
contracts/
└── ProofRegistry.sol       the smart contract used by the test network option
tests/                       32 tests
sample_images/               put a test photo here (not tracked by git)
```

---

## What this doesn't do well yet

- **The fallback face encoder is weaker.** When `face_recognition` isn't installed, the backup method (plain OpenCV) won't match faces as reliably across different lighting, angles, or age gaps.
- **A photo that's never been posted online won't find a match — and that's correct**, not a bug.
- **Looking similar isn't the same as being the same person.** Every match found online gets checked against the original face before being reported, but that check has the same accuracy limits as above.
- **The default blockchain is local, not public.** It's cryptographically real (tamper-evident, hash-chained) but lives on one machine. The optional test-network mode gives you an actual public, shared ledger, at the cost of needing a wallet and network access.
- **`eth_chain.py` hasn't been tested against a live network yet** — it follows the standard `web3.py` pattern, but test it yourself before relying on it.
- **SerpApi's free tier is 100 searches a month** — switch to `SEARCH_PROVIDER=bing` or a paid key once you hit that.

---

## Please use this responsibly

This can find where else a face shows up online — that's a real capability, not a toy. Only run it on your own photo, or one you have permission to use. It's a technical demo, not a tool for stalking, surveillance, or doxxing anyone.

---

## License

MIT
