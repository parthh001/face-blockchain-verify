# Face Identification & Blockchain Verification

Built for **HH Goa 2026 Shortlisting Task 3**.

A pipeline that takes a face photo, finds a real matching social media post
on the open web, and anchors that discovery on a blockchain as a
tamper-evident, re-verifiable record.

```
face photo  -->  detect + encode face  -->  reverse image search  -->  matching social post  -->  hash + upload to blockchain  -->  re-verify on-chain
```

## What it does

1. **Face detection & encoding** (`src/face_id.py`) — detects the face in
   an input photo and turns it into a numeric encoding + a SHA-256
   fingerprint of that encoding. Uses `face_recognition` (dlib, 128-d
   embedding) if installed, and automatically falls back to a
   zero-dependency OpenCV Haar-cascade + HOG encoder if it isn't.
2. **Reverse image search** (`src/reverse_search.py`) — uploads the cropped
   face to a public image host, then runs a real reverse-image search
   against it (Google Lens via SerpApi by default, or Bing Visual Search),
   and filters the results down to actual social media posts (Instagram,
   X/Twitter, Facebook, LinkedIn, TikTok, Reddit, etc.). This is a genuine
   search — the result depends entirely on what the search engine finds for
   that specific photo.
3. **Blockchain anchoring** (`src/simple_chain.py`, or `src/eth_chain.py`
   for a real testnet) — hashes the face fingerprint + discovered post into
   one record, mines it into a new block, and then re-verifies that record
   against the on-chain block (recomputes the hash and checks the whole
   chain for tampering). `src/verify.py` lets you re-run just that
   verification later, independently, without redoing stages 1–2.

Run all three stages together with `src/pipeline.py`.

## Which blockchain

**Default: a local simulated blockchain** (`src/simple_chain.py`). It's a
real hash-chained, proof-of-work-mined, tamper-evident ledger — just run
entirely on your own machine instead of a public network. Every block
stores a SHA-256 hash of its contents plus the previous block's hash, and
`verify_chain()` walks the whole chain to detect any modification. This
was chosen as the default because the task brief explicitly allows "a
local/simulated chain," and it needs no wallet, gas, RPC endpoint, or API
key — it always works, which matters for a live demo recording.

**Optional: a real public testnet** (`src/eth_chain.py` +
`contracts/ProofRegistry.sol`), Polygon Amoy by default, using `web3.py`
to deploy a small Solidity contract (`registerRecord` / `verifyRecord`) and
send a real transaction. Switch to it with `CHAIN_MODE=testnet` in `.env`
(see below) plus `pip install web3 py-solc-x`.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and add your SERPAPI_KEY (see below)
```

`requirements.txt` includes `face_recognition` (dlib-based, 128-d face
embeddings — the recommended, accurate backend). If it fails to install
(dlib needs a C++ compiler and can be slow to build on some machines),
that's fine: `src/face_id.py` automatically falls back to a built-in
OpenCV Haar-cascade + HOG encoder with zero extra dependencies. Either way
the pipeline runs the same commands below.

### Getting a SerpApi key (required for stage 2, `SEARCH_PROVIDER=serpapi`)

Sign up free at [serpapi.com](https://serpapi.com/) — the free tier gives
100 searches/month, plenty for this project. Copy your key into `.env` as
`SERPAPI_KEY`.

Prefer Bing instead? Set `SEARCH_PROVIDER=bing` and `AZURE_BING_KEY` in
`.env` (create a free Azure "Bing Search v7" resource). Bing sends the
image bytes directly, skipping the public-URL upload step SerpApi needs.

## How to run

Detect + encode a face on its own (add `--visualize out.jpg` to save a copy
with the detected face boxed):
```bash
python src/face_id.py sample_images/your_photo.jpg --visualize out.jpg
```

Run the reverse image search on its own (needs an API key, or add `--mock`
to rehearse without one):
```bash
python src/reverse_search.py sample_images/your_photo_face_crop.jpg
```

Inspect or demo the local blockchain:
```bash
python src/simple_chain.py demo         # tamper-evidence demo
python src/simple_chain.py list         # pretty-print every block in chain.json
```

Re-verify a previously anchored record at any later time, without redoing
face detection or the web search:
```bash
python src/verify.py sample_images/your_photo.jpg
```

**Run the full end-to-end pipeline** (this is the one to record):
```bash
python src/pipeline.py sample_images/your_photo.jpg
```

Useful flags on `pipeline.py`:
```bash
--chain testnet          # use the real testnet backend instead of the local chain
--provider bing           # use Bing Visual Search instead of SerpApi
--mock                     # skip the real search, rehearsal only -- see below
--visualize out.jpg         # also save an annotated photo with the face boxed
--out result.json            # save the full JSON result
```

The pipeline **fails fast**: it checks your `.env` / provider setup before
doing any work, so a missing API key shows one clear message immediately
instead of a stack trace after face detection has already run.

### Rehearsal mode (`--mock`)

```bash
python src/pipeline.py sample_images/your_photo.jpg --mock
```
Runs the real stage 1 (face detection) and real stage 3 (blockchain), but
stage 2 returns a clearly-labeled fake result instead of doing a real
search — no API key or internet needed. Every mock result is tagged
(`mock: true`, title prefixed `[MOCK]`) so it can never be mistaken for a
genuine finding. Use this to rehearse the CLI flow and make sure the rest
of the pipeline works before you spend real search quota. **Never use
`--mock` for your actual submission recording** — the task requires a
genuine search step.

Run the automated tests (pure `unittest`, no extra install needed):
```bash
python -m unittest discover -s tests -v
```
Also runs automatically on every push via GitHub Actions
(`.github/workflows/tests.yml`) — including installing the full
`requirements.txt` (dlib included), which is the first place the
`face_recognition` backend actually gets exercised end to end (see
Known limitations).

## For the screen recording

Use your own photo (see the consent note below), and run:
```bash
python src/pipeline.py sample_images/your_photo.jpg
```
The CLI output narrates all three stages in order — face detection result,
the social post the search found, the block that got mined, and the
re-verification result — so recording that single run end to end satisfies
the "face scan → social post found → blockchain upload/verification"
requirement. Optionally follow it with `python src/verify.py <photo>` to
show the record can be independently re-verified later too.

## Repository layout

```
src/
  config.py               centralized, fail-fast .env/config loading
  face_id.py               stage 1: face detection + encoding (+ bbox visualization)
  reverse_search.py         stage 2: reverse image search (SerpApi/Bing/mock) + social filtering
  simple_chain.py             stage 3 (default): local simulated blockchain
  eth_chain.py                 stage 3 (optional): real testnet via web3.py
  pipeline.py                   orchestrates all three stages
  verify.py                      standalone re-verification of an already-anchored record
contracts/
  ProofRegistry.sol           Solidity contract used by the testnet backend
tests/                          32 unit tests, plain unittest, no pytest needed
.github/workflows/tests.yml       CI: runs the full test suite (incl. real dlib install) on every push
sample_images/                      put your own test photo here (not committed)
```

## Known limitations

- **Face encoding accuracy**: the fallback encoder (used when
  `face_recognition`/dlib isn't installed) is a classical HOG descriptor,
  not a deep-learning embedding. It's good enough to demonstrate the
  pipeline but is *not* a production-grade face recognition system — it
  won't reliably match a face across very different lighting, angle, or
  age gaps the way `face_recognition` or a model like FaceNet/ArcFace
  would. Install `face_recognition` for the stronger backend (CI installs
  it fresh on every push, so that path is now continuously tested even
  though the original dev sandbox couldn't install it).
- **Reverse search depends on a paid-tier API past the free quota**:
  SerpApi's free tier is 100 searches/month; past that, switch
  `SEARCH_PROVIDER` to `bing` (also has a free tier) or a paid key. Two
  providers are supported precisely so hitting one quota doesn't block you.
- **Reverse search needs a genuinely public, indexed photo to succeed**:
  reverse image search can only find a "matching social media post" if
  that photo (or a very similar one) is already public and indexed
  somewhere online. A brand new, never-before-posted photo will correctly
  return *no* social match — that's the search working correctly, not a
  bug. Use `--mock` to confirm the rest of the pipeline works while you
  find a good test photo.
- **A "visually similar" result is not automatically "the same person"**:
  Google Lens/Bing return whatever they consider visually similar (colors,
  composition, lighting), which real testing showed can confidently return
  a total stranger's profile. Every social-domain candidate is now
  face-verified against your photo's own encoding before being reported
  (see `face_verified` / `face_distance` in the output and on-chain
  record) — but this cross-check is still bounded by the same weaker
  classical-encoder accuracy noted above when `face_recognition`/dlib
  isn't installed, and by whether Lens even returns a thumbnail for a
  candidate to check in the first place.
- **Local chain vs. testnet**: the default `simple_chain.py` is tamper-evident
  and cryptographically real, but it isn't decentralized — it's a single
  local ledger file, not a network of independent nodes. The optional
  `eth_chain.py` path gives you an actual public, decentralized ledger, at
  the cost of needing a wallet, test funds, and network access.
- **`eth_chain.py` was written but not network-tested** in the sandbox this
  project was built in (outbound access to RPC endpoints/PyPI was blocked
  there). It follows the standard `web3.py` deploy/call pattern and should
  work as written, but test it yourself before depending on it for a
  recording — the default local-chain path has no such caveat and is fully
  tested (`tests/test_simple_chain.py`, `tests/test_verify.py`).
- **Image hosting for reverse search (SerpApi path)**: the face crop is
  uploaded to catbox.moe (a free, no-signup public host) to get a URL
  SerpApi can fetch. Anything uploaded there is publicly accessible
  indefinitely. The Bing provider avoids this — it sends image bytes
  directly.
- **Everything network-dependent is unit-tested against mocked responses**
  (32 tests, all passing) as the fast, repeatable safety net, but it has
  also now been run for real against real, public photos with a real
  SerpApi key — which is exactly how the face-verification bug above was
  found and fixed. Still run it yourself (`python src/pipeline.py <photo>`,
  no `--mock`) before trusting a specific result for your recording;
  reverse-image search quality varies by photo.

## Ethics & consent note

This pipeline can, by design, take a photo of a face and surface where
else that face appears online — that's a real identification capability,
not just a toy. Only run it on your own photo or a photo you have explicit
permission to use. Don't point it at someone else's face without their
consent. This was built as a technical demonstration for a hackathon
shortlisting task, not as a tool for surveillance, stalking, or doxxing,
and it shouldn't be used as one.
