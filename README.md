<div align="center">

# Face Identification & Blockchain Verification

### Face detection + genuine reverse-image search + blockchain-anchored proof of discovery

Built for **HH Goa 2026 Shortlisting Task 3**.

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

## Overview

A pipeline that takes a face photo, finds a real matching social media post on the open web, and anchors that discovery on a blockchain as a tamper-evident, re-verifiable record.

```
face photo → detect + encode face → reverse image search → matching social post → hash + upload to blockchain → re-verify on-chain
```

---

## Pipeline Stages

**1. Face detection & encoding** (`src/face_id.py`) — detects the face in an input photo and produces a numeric encoding plus a SHA-256 fingerprint. Uses `face_recognition` (dlib, 128-d embedding) when available, and falls back to a zero-dependency OpenCV Haar-cascade + HOG encoder otherwise.

**2. Reverse image search** (`src/reverse_search.py`) — uploads the cropped face and runs a genuine reverse-image search (Google Lens via SerpApi, or Bing Visual Search), filtered down to real social media posts (Instagram, X/Twitter, Facebook, LinkedIn, TikTok, Reddit). Every social-domain candidate is face-verified against the original photo before being reported.

**3. Blockchain anchoring** (`src/simple_chain.py`, or `src/eth_chain.py` for a real testnet) — hashes the face fingerprint and discovered post into one record, mines it into a new block, then re-verifies it against the chain. `src/verify.py` re-runs just that verification later, independently.

Run all three stages together with `src/pipeline.py`.

---

## Tech Stack

| Category | Technologies |
|---|---|
| Face detection | `face_recognition` (dlib, 128-d embeddings), OpenCV Haar-cascade + HOG fallback |
| Reverse image search | SerpApi (Google Lens), Bing Visual Search |
| Blockchain (default) | Local simulated chain — SHA-256 hash-chained, proof-of-work mined |
| Blockchain (optional) | Polygon Amoy testnet via `web3.py` + Solidity (`ProofRegistry.sol`) |
| Testing | `unittest` — 32 tests |
| CI/CD | GitHub Actions |

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# add your SERPAPI_KEY (see below)
```

`requirements.txt` includes `face_recognition` (dlib-based — the recommended, accurate backend). If it fails to install (dlib needs a C++ compiler), that's fine: `face_id.py` automatically falls back to the OpenCV encoder with zero extra dependencies.

**Getting a SerpApi key** — sign up free at [serpapi.com](https://serpapi.com/) (100 free searches/month) and copy the key into `.env` as `SERPAPI_KEY`. Prefer Bing instead? Set `SEARCH_PROVIDER=bing` and `AZURE_BING_KEY`.

---

## Usage

**Full pipeline** (the one to record):
```bash
python src/pipeline.py sample_images/your_photo.jpg
```

**Individual stages:**
```bash
python src/face_id.py sample_images/your_photo.jpg --visualize out.jpg   # face detection only
python src/reverse_search.py sample_images/your_photo_face_crop.jpg      # reverse search only
python src/simple_chain.py demo                                          # tamper-evidence demo
python src/verify.py sample_images/your_photo.jpg                        # re-verify later
```

**Useful `pipeline.py` flags:**
```bash
--chain testnet       # use the real testnet backend instead of the local chain
--provider bing       # use Bing Visual Search instead of SerpApi
--mock                # rehearsal only, no real search — never use for a submission recording
--visualize out.jpg   # save an annotated photo with the face boxed
--out result.json     # save the full JSON result
```

The pipeline fails fast — a missing API key or config problem is reported immediately, before any processing runs.

---

## Testing

```bash
python -m unittest discover -s tests -v
```

Runs automatically on every push via GitHub Actions, including a full `dlib` install, so the `face_recognition` backend is continuously tested end to end.

---

## Project Structure

```text
src/
├── config.py            centralized, fail-fast .env/config loading
├── face_id.py            stage 1: face detection + encoding
├── reverse_search.py      stage 2: reverse image search + social filtering
├── simple_chain.py         stage 3 (default): local simulated blockchain
├── eth_chain.py             stage 3 (optional): real testnet via web3.py
├── pipeline.py               orchestrates all three stages
└── verify.py                  standalone re-verification
contracts/
└── ProofRegistry.sol       Solidity contract used by the testnet backend
tests/                       32 unit tests
sample_images/               put your own test photo here (not committed)
```

---

## Known Limitations

- **Face encoding accuracy** — the OpenCV fallback encoder is a classical HOG descriptor, not a deep-learning embedding; it won't reliably match faces across very different lighting, angle, or age gaps the way `face_recognition` would.
- **Reverse search needs a genuinely indexed photo** — a brand-new, never-posted photo will correctly return no social match; that's the search working, not a bug.
- **"Visually similar" is not automatically "same person"** — every social-domain candidate is face-verified against the original encoding before being reported, bounded by the same encoder-accuracy caveat above.
- **Local chain vs. testnet** — the default chain is tamper-evident and cryptographically real but not decentralized (a single local ledger file). The optional testnet path gives an actual public, decentralized ledger at the cost of needing a wallet and network access.
- **`eth_chain.py` was written but not network-tested** in the original dev sandbox (RPC/PyPI access was blocked there); it follows the standard `web3.py` pattern but should be tested before depending on it for a recording.
- **SerpApi's free tier is 100 searches/month** — switch to `SEARCH_PROVIDER=bing` (also free-tier) or a paid key past that.

---

## Ethics & Consent

This pipeline can identify where else a face appears online — a real identification capability, not a toy. Only run it on your own photo or one you have explicit permission to use. Built as a technical demonstration for a hackathon shortlisting task, not as a surveillance, stalking, or doxxing tool.

---

## License

MIT
