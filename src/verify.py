"""
verify.py
=========
Standalone re-verification: prove that a record `pipeline.py` anchored
earlier still matches the blockchain -- without re-running face detection
encoding-only is free/instant, no network) or the web search again.

This is exactly the "demonstrate re-verifying the data against the on-chain
record" requirement, runnable independently and at any later time -- the
thing you'd show someone who asks "how do I know this wasn't edited after
the fact?" without having to redo the whole pipeline in front of them.

Usage:
    python src/verify.py sample_images/your_photo.jpg
    python src/verify.py sample_images/your_photo.jpg --chain-file chain.json
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import face_id
from simple_chain import SimpleChain


def verify(image_path: str, chain_file: str = "chain.json") -> bool:
    print(f"Recomputing the face fingerprint from {image_path} (deterministic, no network calls)...")
    record = face_id.process_image(image_path)
    print(f"  Fingerprint: {record.fingerprint}")

    chain = SimpleChain(chain_file=chain_file)
    block = chain.find_record(record.fingerprint)
    if block is None:
        print(f"\nNo on-chain record found for this face in {chain_file}.")
        print("Run `python src/pipeline.py <image>` first to anchor a record.")
        return False

    chain_ok, chain_reason = chain.verify_chain()
    if not chain_ok:
        print(f"\nCHAIN INTEGRITY CHECK FAILED: {chain_reason}")
        print("The ledger itself has been tampered with -- do not trust any record in it.")
        return False

    recomputed_hash = block.compute_hash()
    match = recomputed_hash == block.hash

    print(f"\nFound block #{block.index}")
    print(f"  Discovered at      : {block.data.get('discovered_at', 'unknown')}")
    print(f"  Social post        : {block.data.get('social_post_url', 'n/a')}")
    print(f"  Stored block hash  : {block.hash}")
    print(f"  Recomputed hash    : {recomputed_hash}")
    print(f"  Result             : {'MATCH -- record is authentic and unmodified' if match else 'MISMATCH -- TAMPERED'}")
    return match


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-verify a face's on-chain record without re-running the whole pipeline")
    parser.add_argument("image", help="The same face photo used with pipeline.py")
    parser.add_argument("--chain-file", default="chain.json")
    args = parser.parse_args()

    ok = verify(args.image, chain_file=args.chain_file)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
