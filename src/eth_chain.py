"""
eth_chain.py
============
OPTIONAL stage-3 backend: anchor the record on a real Ethereum-compatible
public testnet (default: Polygon Amoy) instead of the local simulated
chain in `simple_chain.py`.

Requires extra dependencies not needed by the default path:
    pip install web3 py-solc-x

And a .env with:
    CHAIN_MODE=testnet
    RPC_URL=https://rpc-amoy.polygon.technology   (or any Amoy/Sepolia RPC)
    PRIVATE_KEY=0x...                              (a TESTNET-ONLY wallet key)

Get free Amoy test POL from a faucet (e.g. https://faucet.polygon.technology/)
-- you need a small amount of test gas to send the registerRecord transaction.

IMPORTANT: this module could not be network-tested in the environment this
project was built in (outbound access to RPC endpoints and PyPI was
blocked there). The Solidity contract and web3.py calls below follow the
standard, well-documented web3.py deploy/call pattern, but you should run
`python src/eth_chain.py sample_images/test_face_crop.jpg` yourself on a
machine with normal internet access before you rely on it for your demo
recording. The default pipeline (simple_chain.py) does not have this
limitation.
"""
import json
import os
from pathlib import Path
from typing import Optional, Tuple

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "ProofRegistry.sol"
DEPLOYMENT_FILE = Path(__file__).resolve().parent.parent / ".deployment.json"


def _compile_contract() -> dict:
    from solcx import compile_source, install_solc, set_solc_version

    try:
        set_solc_version("0.8.19")
    except Exception:
        install_solc("0.8.19")
        set_solc_version("0.8.19")

    source = CONTRACT_PATH.read_text()
    compiled = compile_source(source, output_values=["abi", "bin"])
    _, contract_interface = compiled.popitem()
    return contract_interface


def _get_web3():
    from web3 import Web3

    rpc_url = os.environ.get("RPC_URL")
    if not rpc_url:
        raise RuntimeError("RPC_URL not set in .env (needed for CHAIN_MODE=testnet).")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise RuntimeError(f"Could not connect to RPC endpoint: {rpc_url}")
    return w3


def deploy_contract() -> str:
    """Deploy ProofRegistry.sol to the configured testnet (idempotent --
    reuses the address in .deployment.json if already deployed)."""
    if DEPLOYMENT_FILE.exists():
        info = json.loads(DEPLOYMENT_FILE.read_text())
        if info.get("rpc_url") == os.environ.get("RPC_URL"):
            return info["address"]

    from web3 import Web3

    w3 = _get_web3()
    private_key = os.environ["PRIVATE_KEY"]
    account = w3.eth.account.from_key(private_key)

    interface = _compile_contract()
    contract = w3.eth.contract(abi=interface["abi"], bytecode=interface["bin"])

    tx = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 2_000_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    DEPLOYMENT_FILE.write_text(
        json.dumps({"address": receipt.contractAddress, "abi": interface["abi"], "rpc_url": os.environ.get("RPC_URL")}, indent=2)
    )
    return receipt.contractAddress


def _get_contract():
    from web3 import Web3

    w3 = _get_web3()
    address = deploy_contract()
    info = json.loads(DEPLOYMENT_FILE.read_text())
    contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=info["abi"])
    return w3, contract


def register_record(data_hash_hex: str, metadata_uri: str) -> str:
    """Send registerRecord(dataHash, metadataURI) to the deployed contract.
    Returns the transaction hash."""
    from web3 import Web3

    w3, contract = _get_contract()
    private_key = os.environ["PRIVATE_KEY"]
    account = w3.eth.account.from_key(private_key)

    data_hash_bytes = Web3.to_bytes(hexstr=data_hash_hex)
    tx = contract.functions.registerRecord(data_hash_bytes, metadata_uri).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 200_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    return tx_hash.hex()


def verify_record(data_hash_hex: str) -> Tuple[bool, Optional[dict]]:
    """Re-verify a hash against the on-chain record."""
    from web3 import Web3

    w3, contract = _get_contract()
    data_hash_bytes = Web3.to_bytes(hexstr=data_hash_hex)
    found, metadata_uri, submitter, timestamp = contract.functions.verifyRecord(data_hash_bytes).call()
    if not found:
        return False, None
    return True, {"metadata_uri": metadata_uri, "submitter": submitter, "timestamp": timestamp}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    if len(sys.argv) != 2:
        print("Usage: python eth_chain.py <sha256_hex_to_anchor>")
        sys.exit(1)

    data_hash = sys.argv[1]
    if not data_hash.startswith("0x"):
        data_hash = "0x" + data_hash

    print("Deploying/reusing contract...")
    address = deploy_contract()
    print("Contract address:", address)

    print("Registering record on-chain...")
    tx = register_record(data_hash, "cli-test")
    print("Tx hash:", tx)

    print("Re-verifying...")
    ok, info = verify_record(data_hash)
    print("Verified:", ok, info)
