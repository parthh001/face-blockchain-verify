"""
config.py
=========
Centralized, fail-fast configuration loading.

Without this, a typo'd or missing API key surfaces halfway through a run --
after face detection has already happened -- as a raw exception. This module
lets `pipeline.py` check "do I actually have what I need for this run?"
*before* doing any work, and print one clear, actionable message instead.
"""
import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    search_provider: str
    serpapi_key: Optional[str]
    azure_bing_key: Optional[str]
    chain_mode: str
    rpc_url: Optional[str]
    private_key: Optional[str]


def load_settings() -> Settings:
    return Settings(
        search_provider=os.environ.get("SEARCH_PROVIDER", "serpapi").lower(),
        serpapi_key=os.environ.get("SERPAPI_KEY"),
        azure_bing_key=os.environ.get("AZURE_BING_KEY"),
        chain_mode=os.environ.get("CHAIN_MODE", "local").lower(),
        rpc_url=os.environ.get("RPC_URL"),
        private_key=os.environ.get("PRIVATE_KEY"),
    )


def check_search_provider_ready(provider: str) -> List[str]:
    """Return a list of human-readable problems for the given search
    provider; empty list means it's ready to use. `provider="mock"` is
    always ready (no network, no key)."""
    settings = load_settings()
    problems: List[str] = []

    if provider == "mock":
        return problems

    if provider == "serpapi":
        if not settings.serpapi_key or settings.serpapi_key == "your_serpapi_key_here":
            problems.append(
                "SEARCH_PROVIDER=serpapi but SERPAPI_KEY is not set in .env "
                "(get a free key at https://serpapi.com/, 100 searches/month free)."
            )
    elif provider == "bing":
        if not settings.azure_bing_key:
            problems.append(
                "SEARCH_PROVIDER=bing but AZURE_BING_KEY is not set in .env "
                "(create a free Azure Bing Search v7 resource to get one)."
            )
    else:
        problems.append(f"Unknown SEARCH_PROVIDER: {provider!r} (expected serpapi, bing, or mock).")

    return problems


def check_chain_ready(chain_mode: str) -> List[str]:
    """Same idea for the blockchain backend. chain_mode="local" is always
    ready (no external service needed)."""
    settings = load_settings()
    problems: List[str] = []

    if chain_mode == "local":
        return problems

    if chain_mode == "testnet":
        if not settings.rpc_url:
            problems.append("CHAIN_MODE=testnet but RPC_URL is not set in .env.")
        if not settings.private_key or settings.private_key == "your_testnet_wallet_private_key_here":
            problems.append("CHAIN_MODE=testnet but PRIVATE_KEY is not set in .env (a TESTNET-ONLY wallet key).")
        try:
            import web3  # noqa: F401
        except ImportError:
            problems.append("CHAIN_MODE=testnet needs `pip install web3 py-solc-x` (not in the default requirements.txt).")
    else:
        problems.append(f"Unknown CHAIN_MODE: {chain_mode!r} (expected local or testnet).")

    return problems
