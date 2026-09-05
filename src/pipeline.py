"""
pipeline.py
===========
End-to-end orchestrator: face scan -> web/social search -> blockchain
upload & verification. This is the script to run (and record your screen
running) for the submission.

    python src/pipeline.py sample_images/your_photo.jpg
    python src/pipeline.py sample_images/your_photo.jpg --chain testnet
    python src/pipeline.py sample_images/your_photo.jpg --provider bing
    python src/pipeline.py sample_images/your_photo.jpg --mock       # rehearsal only, see below
    python src/pipeline.py sample_images/your_photo.jpg --visualize out.jpg

`--mock` skips the real web search and uses a clearly-labeled fake result
instead -- it exists purely so you can rehearse the full CLI flow (and
check stages 1 and 3 work) without spending a real search or needing
internet. It is loudly flagged in the output. NEVER use --mock for your
actual submission recording; the task requires a genuine search.

Each stage prints what it's doing and its result, so the CLI output itself
tells the story for the screen recording.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import face_id
import reverse_search
from simple_chain import SimpleChain


def _hash_record(record: dict) -> str:
    blob = json.dumps(record, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def run(
    image_path: str,
    chain_mode: str = "local",
    chain_file: str = "chain.json",
    provider: str = None,
    visualize: str = None,
) -> dict:
    settings = config.load_settings()
    provider = (provider or settings.search_provider).lower()

    if provider == "mock":
        print("*" * 70)
        print("  MOCK MODE -- stage 2 is NOT doing a real search.")
        print("  This is for rehearsing the CLI flow only.")
        print("  Do NOT use this run for your submission recording.")
        print("*" * 70)
        print()

    print("=" * 70)
    print("STAGE 1 / 3  --  Face detection & encoding")
    print("=" * 70)
    face_record = face_id.process_image(image_path)
    print(f"  Backend used   : {face_record.backend}")
    print(f"  Face bbox      : {face_record.bbox}")
    print(f"  Encoding length: {len(face_record.encoding)} numbers")
    print(f"  Fingerprint    : {face_record.fingerprint}")

    crop_path = str(Path(image_path).with_suffix("")) + "_face_crop.jpg"
    face_id.crop_face(image_path, tuple(face_record.bbox), crop_path)
    print(f"  Face crop saved: {crop_path}")

    if visualize:
        face_id.draw_bbox(image_path, tuple(face_record.bbox), visualize)
        print(f"  Annotated image: {visualize}")

    print()
    print("=" * 70)
    print("STAGE 2 / 3  --  Reverse image / social media search")
    print(f"    (provider: {provider})")
    print("=" * 70)
    match = reverse_search.find_social_match(
        crop_path, provider=provider, query_encoding=face_record.encoding
    )
    print(f"  Matching post  : {match.link}")
    print(f"  Title          : {match.title}")
    print(f"  Source platform: {match.source}")
    if match.mock:
        print("  ** MOCK RESULT -- not a real search finding **")
    elif match.verified:
        print(f"  Face verified  : YES (distance={match.face_distance:.4f}, threshold={reverse_search.DEFAULT_FACE_MATCH_THRESHOLD})")
        print("                   The candidate's face was cross-checked against your photo's")
        print("                   face encoding and is close enough to count as the same person.")
    else:
        dist_str = f"{match.face_distance:.4f}" if match.face_distance is not None else "n/a (no face found in candidate thumbnail)"
        print(f"  Face verified  : NO (distance={dist_str}, threshold={reverse_search.DEFAULT_FACE_MATCH_THRESHOLD})")
        print("                   This is the visually closest social-media result Lens returned,")
        print("                   but its face did NOT match yours closely enough to confirm it's")
        print("                   the same person. Reported honestly rather than as a false match.")

    record = {
        "face_fingerprint": face_record.fingerprint,
        "face_backend": face_record.backend,
        "social_post_url": match.link,
        "social_post_title": match.title,
        "social_post_source": match.source,
        "search_provider": provider,
        "mock": match.mock,
        "face_verified": match.verified,
        "face_distance": match.face_distance,
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    record_hash = _hash_record(record)

    print()
    print("=" * 70)
    print("STAGE 3 / 3  --  Blockchain upload & verification")
    print("=" * 70)

    if chain_mode == "local":
        chain = SimpleChain(chain_file=chain_file)
        block = chain.add_record(record)
        print(f"  Chain          : local simulated chain ({chain_file})")
        print(f"  Block #{block.index} mined (nonce={block.nonce})")
        print(f"  Block hash     : {block.hash}")
        print(f"  Previous hash  : {block.previous_hash}")

        print()
        print("  Re-verifying the record against the on-chain block...")
        ok, found_block, msg = chain.verify_record(record)
        print(f"  Verification   : {'PASSED' if ok else 'FAILED'} -- {msg}")

        chain_ok, chain_reason = chain.verify_chain()
        print(f"  Full chain integrity check: {'VALID' if chain_ok else 'BROKEN: ' + str(chain_reason)}")
        print()
        print(f"  Tip: re-verify this exact record any time later, without redoing stages 1-2, with:")
        print(f"       python src/verify.py {image_path} --chain-file {chain_file}")

        result = {
            "face": face_record.to_dict(),
            "social_match": match.to_dict(),
            "on_chain_record": record,
            "record_hash": record_hash,
            "block_index": block.index,
            "block_hash": block.hash,
            "verified": ok,
        }

    elif chain_mode == "testnet":
        import eth_chain

        print("  Chain          : public testnet (see .env RPC_URL)")
        address = eth_chain.deploy_contract()
        print(f"  Contract       : {address}")
        tx_hash = eth_chain.register_record(record_hash, match.link)
        print(f"  Tx hash        : {tx_hash}")

        ok, info = eth_chain.verify_record(record_hash)
        print(f"  Verification   : {'PASSED' if ok else 'FAILED'} -- {info}")

        result = {
            "face": face_record.to_dict(),
            "social_match": match.to_dict(),
            "on_chain_record": record,
            "record_hash": record_hash,
            "contract_address": address,
            "tx_hash": tx_hash,
            "verified": ok,
        }
    else:
        raise ValueError(f"Unknown chain mode: {chain_mode}")

    print()
    print("=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    return result


def main() -> None:
    settings = config.load_settings()

    parser = argparse.ArgumentParser(description="Face scan -> social search -> blockchain verification pipeline")
    parser.add_argument("image", help="Path to the input face photo")
    parser.add_argument("--chain", choices=["local", "testnet"], default=settings.chain_mode)
    parser.add_argument("--chain-file", default="chain.json")
    parser.add_argument("--provider", choices=["serpapi", "bing", "mock"], default=None, help="Reverse-search provider (default: SEARCH_PROVIDER in .env, or serpapi)")
    parser.add_argument("--mock", action="store_true", help="Shortcut for --provider mock (rehearsal only, not a real search)")
    parser.add_argument("--visualize", metavar="OUT_PATH", default=None, help="Also save a copy of the photo with the detected face boxed")
    parser.add_argument("--out", default=None, help="Optional path to save the full JSON result")
    args = parser.parse_args()

    provider = "mock" if args.mock else args.provider

    # Fail fast: check everything this run needs BEFORE doing any work,
    # instead of running face detection and then dying on a missing key.
    problems = config.check_search_provider_ready(provider or settings.search_provider) + config.check_chain_ready(args.chain)
    if problems:
        print("Cannot run -- fix the following first:\n")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    result = run(args.image, chain_mode=args.chain, chain_file=args.chain_file, provider=provider, visualize=args.visualize)

    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(f"\nFull result written to {args.out}")


if __name__ == "__main__":
    main()
