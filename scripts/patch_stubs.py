"""
patch_stubs.py — Enrich stub entries in active.jsonl with proper content,
then re-run rebuild_topics to refresh all topic files.
"""
import json
from pathlib import Path

REPO_ROOT   = Path(__file__).parent.parent
ACTIVE_FILE = REPO_ROOT / "knowledge" / "active.jsonl"

PATCHES = {
    # "cookienet and cookiechain are synonymous" — expand into a proper FAQ entry
    "20368aa40d12b008": {
        "title":   "Cookie Chain FAQ — Cookienet vs Cookiechain",
        "content": (
            "Cookie Chain FAQ — Cookienet vs Cookiechain\n\n"
            "Cookienet and Cookie Chain are synonymous — they refer to the same network.\n\n"
            "The name 'Cookienet' is an informal community shorthand for the Cookie Chain "
            "network. Both names refer to the same SVM chain running with COOK as its native "
            "asset. Official documentation uses 'Cookie Chain' as the primary name."
        ),
    },
    # Cookiescan Trading API — add proper description
    "eb31dcca3cbbff29": {
        "title":   "Cookiescan Trading API",
        "content": (
            "Cookiescan Trading API\n\n"
            "The Cookiescan API provides programmatic access to Cookie Chain blockchain data "
            "including transactions, blocks, tokens, validators, and analytics.\n\n"
            "API Playground: https://api.cookiescan.io/playground\n"
            "Base URL: https://api.cookiescan.io\n\n"
            "Use the API to build trading bots, indexers, dashboards, and data tools on top "
            "of Cookie Chain. The playground lets you explore endpoints interactively."
        ),
    },
    # Cookie Bridge — add proper description
    "15f2829601dae3df": {
        "title":   "Cookie Bridge — Transfer COOK between Cookie Chain & Solana",
        "content": (
            "Cookie Bridge — Transfer COOK between Cookie Chain & Solana\n\n"
            "The Cookie Bridge lets you move COOK between Solana and Cookie Chain through "
            "a community-operated multi-sig vault.\n\n"
            "Bridge URL: https://bridge.cookiescan.io\n\n"
            "How it works:\n"
            "- Solana → Cookie Chain: deposit COOK into the bridge vault on Solana mainnet. "
            "Once the multi-sig threshold is met, COOK is unlocked on Cookie Chain.\n"
            "- Cookie Chain → Solana: the same signer set coordinates the reverse unlock.\n\n"
            "Bridge vault address (Vault 0): G3mm95M4ns7mk8oseWGJnirvgyMahMz3vZEUhdJn8oGX\n"
            "Multisig transparency: sig.cookiechain.wtf/community\n\n"
            "Only use the official bridge URL. Verify the URL before signing any transaction."
        ),
    },
    # CandyShop — add proper description
    "56fb9b3fa095c089": {
        "title":   "CandyShop — Cookie Chain DEX Aggregator",
        "content": (
            "CandyShop — Cookie Chain DEX Aggregator\n\n"
            "CandyShop is the DEX aggregator for Cookie Chain, allowing users to swap tokens "
            "at the best available rates across liquidity sources on the network.\n\n"
            "URL: https://swap.cookiescan.io\n\n"
            "Use CandyShop to swap COOK and other SPL tokens on Cookie Chain. "
            "It is the primary trading interface for the Cookie Chain ecosystem."
        ),
    },
    # Cookoven — add proper description
    "7c85bf73ecb41c6d": {
        "title":   "Cookoven — dApp Hub for Cookie Chain",
        "content": (
            "Cookoven — The Hub for dApps on Cookie Chain\n\n"
            "Cookoven is the central hub for discovering and accessing decentralized "
            "applications (dApps) built on Cookie Chain.\n\n"
            "URL: https://cookoven.xyz\n\n"
            "Browse the Cookie Chain ecosystem, find live programs, and explore what builders "
            "have shipped on the network. Cookoven is the go-to directory for Cookie Chain "
            "dApps and ecosystem projects."
        ),
    },
    # break-gorbagana — the content was already updated in rebuild_topics but let's verify
    "991876074939a958": {
        "title":   "Cookie Chain — Break Gorbagana (Network Stress Test)",
        "content": (
            "Cookie Chain — Break Gorbagana (Network Stress Test)\n\n"
            "An interactive stress-test tool on cookiescan.io that lets users hammer the "
            "Cookie Chain network with rapid RPC requests to test its performance.\n\n"
            "Cookie Chain is a high-performance blockchain with ~1-second block times, "
            "sub-second finality, and low fees. The stress test demonstrates the network's "
            "capacity for high-throughput transactions.\n\n"
            "URL: https://cookiescan.io/break-gorbagana\n\n"
            "Powered by the Solana Virtual Machine (SVM) with proof-of-history consensus "
            "and parallel transaction processing."
        ),
    },
}


def main() -> None:
    entries = [json.loads(l) for l in ACTIVE_FILE.read_text().splitlines() if l.strip()]
    patched = 0
    for entry in entries:
        eid = entry["id"]
        if eid in PATCHES:
            entry.update(PATCHES[eid])
            patched += 1
            print(f"  PATCHED: {entry['title']}")
    ACTIVE_FILE.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    print(f"\nPatched {patched} entries in active.jsonl")


if __name__ == "__main__":
    main()
