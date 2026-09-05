"""
simple_chain.py
================
Stage 3 (default backend) of the pipeline: a local, simulated blockchain
used to anchor the discovered social media post in a tamper-evident record.

This is a genuine blockchain data structure -- not a database pretending to
be one:
  - every block stores a SHA-256 hash of its own contents
  - every block stores the previous block's hash, chaining them together
  - a lightweight proof-of-work (find a nonce so the block hash starts with
    N zero hex digits) is required to append a block, same idea as real
    chains, just with a tiny difficulty so it runs instantly
  - changing ANY byte of ANY past block's data breaks that block's hash AND
    every hash after it -- `verify_chain()` walks the whole chain and will
    catch this (see `tamper_demo()` at the bottom for a live demonstration)

The task brief explicitly allows "a local/simulated chain" as one of the
valid blockchain choices -- this is that option, and it's the default
because it needs zero external services, wallets, gas, or API keys, so the
pipeline always works, including for the screen recording.

For a *real* public testnet instead (Polygon Amoy via web3.py + a Solidity
contract), see `src/eth_chain.py` and `contracts/ProofRegistry.sol`.

The ledger is persisted to a JSON file (default: chain.json) so state
survives between runs, the same way a real node persists to disk.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DIFFICULTY = 4  # number of leading hex zeros required in a block hash
DEFAULT_CHAIN_FILE = "chain.json"


@dataclass
class Block:
    index: int
    timestamp: float
    data: Dict[str, Any]
    previous_hash: str
    nonce: int = 0
    hash: str = ""
    difficulty: int = 0  # leading-zero-hex-digits requirement THIS block was mined at

    def compute_hash(self) -> str:
        payload = {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
        }
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Block":
        return Block(**d)


class SimpleChain:
    def __init__(self, chain_file: str = DEFAULT_CHAIN_FILE, difficulty: int = DEFAULT_DIFFICULTY):
        self.chain_file = Path(chain_file)
        self.difficulty = difficulty
        self.blocks: List[Block] = []
        if self.chain_file.exists():
            self._load()
        else:
            self._create_genesis_block()
            self._save()

    # -- chain construction -------------------------------------------------

    def _create_genesis_block(self) -> None:
        # difficulty=0 -- the genesis block carries no data worth mining,
        # it just anchors index 0 so every real block has a previous_hash.
        genesis = Block(index=0, timestamp=time.time(), data={"genesis": True}, previous_hash="0" * 64, difficulty=0)
        genesis.hash = genesis.compute_hash()
        self.blocks = [genesis]

    def _mine(self, block: Block) -> Block:
        # The difficulty used to mine THIS block is stored on the block
        # itself (and hashed as part of it) so verification later always
        # checks each block against the difficulty it was actually mined
        # at -- even if this chain object was constructed with a different
        # `difficulty` setting than the file was originally written with.
        block.difficulty = self.difficulty
        prefix = "0" * self.difficulty
        while True:
            candidate = block.compute_hash()
            if candidate.startswith(prefix):
                block.hash = candidate
                return block
            block.nonce += 1

    def add_record(self, data: Dict[str, Any]) -> Block:
        """Append a new block anchoring `data` (e.g. the face fingerprint +
        discovered social post) to the chain. Returns the mined block."""
        previous = self.blocks[-1]
        block = Block(
            index=previous.index + 1,
            timestamp=time.time(),
            data=data,
            previous_hash=previous.hash,
        )
        block = self._mine(block)
        self.blocks.append(block)
        self._save()
        return block

    # -- verification ---------------------------------------------------

    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        """Walk the whole chain and confirm every hash link and every
        proof-of-work is valid. Returns (is_valid, reason_if_not).

        Each block is checked against the difficulty *recorded on that
        block* (set when it was mined), not against self.difficulty --
        otherwise re-opening a chain file with a SimpleChain instance
        configured at a different difficulty than it was written with
        would wrongly report a healthy chain as broken."""
        for i, block in enumerate(self.blocks):
            recomputed = block.compute_hash()
            if recomputed != block.hash:
                return False, f"Block {i} hash mismatch -- its data was modified after mining."
            if i > 0:
                if block.previous_hash != self.blocks[i - 1].hash:
                    return False, f"Block {i} does not correctly reference block {i - 1}'s hash -- chain is broken."
                prefix = "0" * block.difficulty
                if not block.hash.startswith(prefix):
                    return False, f"Block {i} does not satisfy its recorded proof-of-work difficulty."
        return True, None

    def find_record(self, fingerprint: str) -> Optional[Block]:
        """Return the MOST RECENT block anchoring this fingerprint.

        A face can legitimately be re-scanned and re-anchored more than
        once (e.g. re-running the pipeline on the same photo after a
        search-provider fix, or a genuine re-verification later). Walking
        from the newest block backwards -- instead of returning the first
        match found from the genesis block forward -- makes verify_record()
        check the *current* anchor for that face, not accidentally an old,
        stale one. Confirmed as a real bug: re-running this pipeline on the
        same photo multiple times (exactly what happened while debugging
        the reverse-search fix) left several blocks sharing one
        face_fingerprint, and the old first-match behavior made
        verify_record() compare against the wrong (earliest) block and
        report a false "tampered or wrong input" failure on a perfectly
        good, freshly-mined block."""
        for block in reversed(self.blocks):
            if block.data.get("face_fingerprint") == fingerprint:
                return block
        return None

    def verify_record(self, data: Dict[str, Any]) -> Tuple[bool, Optional[Block], str]:
        """Re-verify a piece of data against the on-chain record: find the
        block that claims to hold this fingerprint, recompute its hash from
        the data provided right now, and compare. This is the "re-verifying
        the data against the on-chain record" step the task asks for."""
        ok, reason = self.verify_chain()
        if not ok:
            return False, None, f"Chain integrity check failed: {reason}"

        fingerprint = data.get("face_fingerprint")
        block = self.find_record(fingerprint)
        if block is None:
            return False, None, "No on-chain record found for this fingerprint."

        if block.data != data:
            return False, block, "Record found on-chain, but the supplied data does not match what was anchored (tampered or wrong input)."

        return True, block, "Record verified: matches the on-chain block exactly, and the chain is intact."

    # -- persistence ---------------------------------------------------

    def _save(self) -> None:
        payload = [b.to_dict() for b in self.blocks]
        self.chain_file.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        payload = json.loads(self.chain_file.read_text())
        self.blocks = [Block.from_dict(b) for b in payload]


def tamper_demo(chain_file: str = "chain_tamper_demo.json") -> None:
    """Live demonstration of tamper-evidence: add a record, verify it's
    clean, then secretly edit a block's data on disk and show verify_chain()
    catching it. Useful to run once for the screen recording."""
    Path(chain_file).unlink(missing_ok=True)
    chain = SimpleChain(chain_file=chain_file)
    chain.add_record({"face_fingerprint": "abc123", "social_post_url": "https://instagram.com/p/xyz"})

    ok, reason = chain.verify_chain()
    print(f"Before tampering -> valid: {ok}")

    # simulate an attacker editing the ledger file directly
    raw = json.loads(Path(chain_file).read_text())
    raw[-1]["data"]["social_post_url"] = "https://instagram.com/p/FAKE"
    Path(chain_file).write_text(json.dumps(raw, indent=2))

    tampered_chain = SimpleChain(chain_file=chain_file)
    ok, reason = tampered_chain.verify_chain()
    print(f"After tampering  -> valid: {ok} ({reason})")


def print_chain(chain_file: str = DEFAULT_CHAIN_FILE) -> None:
    """Pretty-print every block in the ledger -- a quick way to look at the
    whole chain (e.g. for the screen recording, or just to sanity-check
    what's been anchored so far)."""
    path = Path(chain_file)
    if not path.exists():
        print(f"No chain file at {chain_file} yet -- run the pipeline first.")
        return

    chain = SimpleChain(chain_file=chain_file)
    ok, reason = chain.verify_chain()
    print(f"Chain: {chain_file}  ({len(chain.blocks)} blocks)  integrity: {'VALID' if ok else 'BROKEN: ' + str(reason)}")
    print("-" * 70)
    for block in chain.blocks:
        print(f"Block #{block.index}")
        print(f"  hash          : {block.hash}")
        print(f"  previous_hash : {block.previous_hash}")
        print(f"  nonce         : {block.nonce}")
        print(f"  data          : {json.dumps(block.data, indent=4)}")
        print("-" * 70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Local simulated blockchain -- inspect or demo it")
    sub = parser.add_subparsers(dest="command")

    demo_p = sub.add_parser("demo", help="Run the tamper-evidence demo (default if no command given)")
    demo_p.add_argument("--chain-file", default="chain_tamper_demo.json")

    list_p = sub.add_parser("list", help="Pretty-print every block in a chain file")
    list_p.add_argument("--chain-file", default=DEFAULT_CHAIN_FILE)

    args = parser.parse_args()

    if args.command == "list":
        print_chain(args.chain_file)
    else:
        tamper_demo(getattr(args, "chain_file", "chain_tamper_demo.json"))
