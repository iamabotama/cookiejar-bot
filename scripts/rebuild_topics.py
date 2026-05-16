"""
rebuild_topics.py — Full topic rebuild for CookieJar knowledge base.

This script:
1. Wipes all existing topic files
2. Rewrites active.jsonl entries with correct content (for the stub docs entries)
3. Adds new entries for docs.cookiechain.wtf pages not yet in the KB
4. Classifies every entry into the correct topic(s) and writes topic files
5. Updates knowledge/index.json

Run from repo root:
    python3 scripts/rebuild_topics.py
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
KB_DIR    = REPO_ROOT / "knowledge"
TOPICS_DIR = KB_DIR / "topics"
ACTIVE_FILE = KB_DIR / "active.jsonl"
INDEX_FILE  = KB_DIR / "index.json"

TOPICS = ["chain", "lore", "token", "community", "dev", "faq", "links", "socials", "general"]

# ---------------------------------------------------------------------------
# Real content for docs.cookiechain.wtf pages (replaces stub entries)
# ---------------------------------------------------------------------------

DOCS_CONTENT = {
    "https://cookiescan.io/docs#introduction": {
        "title": "Cookie Chain — Introduction",
        "content": (
            "Cookie Chain — Introduction\n\n"
            "Cookie Chain is a community-run Solana fork. It started as a Solana fork. "
            "The original group of community devs built a thriving chain and ecosystem. "
            "When the core team's vision stopped aligning with the community, the community "
            "forked the fork and kept shipping.\n\n"
            "Today, Cookie Chain is operated by an expanding multi-validator set with COOK as "
            "the native asset. Real validators. Real governance. Real shipping.\n\n"
            "What makes Cookie Chain different:\n"
            "- Solana compatible: SPL tokens, programs, and tooling work out of the box.\n"
            "- Community operated: no foundation gate, no single operator.\n"
            "- Multi-sig bridge: COOK moves between Solana and Cookie Chain through an m-of-n "
            "community multi-sig — no single key controls the vault.\n"
            "- Sub-second finality: ~1s block times with Solana-style consensus.\n"
            "- Minimal fees: fees paid in COOK, priced for builders and users, not extractors.\n"
            "- Dirt-cheap program deploys: deploying a program on Cookie Chain costs next to "
            "nothing compared to Solana mainnet."
        ),
        "topic": "chain",
    },
    "https://cookiescan.io/docs#getting-started": {
        "title": "Cookie Chain — Getting Started",
        "content": (
            "Cookie Chain — Getting Started\n\n"
            "Connect to Cookie Chain in minutes with the Solana CLI, Nightly wallet, and the "
            "community RPC.\n\n"
            "1. Point the Solana CLI at Cookie Chain:\n"
            "   solana config set --url https://rpc.cookiescan.io\n\n"
            "2. Check the connection:\n"
            "   solana cluster-version\n\n"
            "3. Create or import a wallet:\n"
            "   solana-keygen new --outfile ~/.config/solana/id.json\n\n"
            "Wallet support includes Nightly. Install from nightly.app and connect to Cookie "
            "Chain with the community RPC endpoint: https://rpc.cookiescan.io\n\n"
            "4. Get COOK: Bridge COOK from Solana through the community multi-sig bridge at "
            "bridge.cookiescan.io\n\n"
            "5. Explore:\n"
            "   - Block explorer: cookiescan.io\n"
            "   - Deployed programs: cookiescan.io/programs\n"
            "   - Validator set: cookiescan.io/validators"
        ),
        "topic": "faq",
    },
    "https://cookiescan.io/docs#wallets": {
        "title": "Cookie Chain — Wallets",
        "content": (
            "Cookie Chain — Wallets\n\n"
            "Cookie Chain supports standard Solana-compatible wallets, including browser "
            "wallets, mobile wallets, and hardware-backed flows.\n\n"
            "Recommended wallet: Nightly — fully supported on Cookie Chain. "
            "Install from nightly.app.\n\n"
            "Connect to Cookie Chain:\n"
            "- Open your wallet network settings and choose custom RPC or custom SVM network.\n"
            "- RPC: https://rpc.cookiescan.io\n"
            "- WebSocket: https://wss.cookiescan.io\n"
            "- Bridge: bridge.cookiescan.io\n\n"
            "Quick checklist:\n"
            "- Back up your seed phrase offline.\n"
            "- Verify URLs before signing transactions.\n"
            "- Use separate wallets for high-value storage and daily dApp use."
        ),
        "topic": "faq",
    },
    "https://cookiescan.io/docs#architecture": {
        "title": "Cookie Chain — Architecture & Consensus",
        "content": (
            "Cookie Chain — Architecture & Consensus\n\n"
            "Cookie Chain inherits SVM architecture with PoH, Tower BFT, Turbine, Gulf Stream, "
            "Sealevel, and pipelining.\n\n"
            "Proof of History (PoH): A verifiable delay function acts as a cryptographic clock "
            "and orders events before consensus runs.\n\n"
            "Tower BFT: A PoH-optimized PBFT variant lets validators vote on the PoH sequence, "
            "reducing messaging overhead and supporting sub-second finality.\n\n"
            "Turbine: block propagation via randomized shredding.\n"
            "Gulf Stream: mempool-less transaction forwarding directly to the upcoming leader.\n"
            "Sealevel: parallel program execution across CPU cores.\n"
            "Pipelining: staged transaction validation for steady throughput.\n\n"
            "Block time & finality:\n"
            "- Target block time: ~80-140 ms\n"
            "- Finality is sub-second under normal conditions.\n"
            "- Consensus is produced by an expanding set of independent validators."
        ),
        "topic": "chain",
    },
    "https://cookiescan.io/docs#validators": {
        "title": "Cookie Chain — Validators",
        "content": (
            "Cookie Chain — Validators\n\n"
            "Cookie Chain is operated by an expanding multi-validator set. "
            "Validator onboarding is open to qualified community members.\n\n"
            "Validators secure the chain through stake and produce blocks using Solana-style "
            "consensus (Tower BFT + PoH). No single validator or foundation controls the chain.\n\n"
            "View the current validator set at: cookiescan.io/validators\n\n"
            "Validator incentives are funded through pump.fun creator fees from the Solana-side "
            "token launch, routed back into the ecosystem."
        ),
        "topic": "chain",
    },
    "https://cookiescan.io/docs#bridge": {
        "title": "Cookie Chain — Community Multi-sig Bridge",
        "content": (
            "Cookie Chain — Community Multi-sig Bridge\n\n"
            "COOK moves between Solana and Cookie Chain through a community-operated multi-sig. "
            "It is a lock/unlock bridge — no single party can move bridge funds unilaterally.\n\n"
            "Flow: Solana to Cookie Chain:\n"
            "- Lock on Solana: deposit COOK into bridge vault on Solana mainnet.\n"
            "- Unlock on Cookie Chain: once the threshold is met, the multi-sig authorizes the "
            "corresponding asset to unlock on Cookie Chain.\n\n"
            "Bridge vault address: G3mm95M4ns7mk8oseWGJnirvgyMahMz3vZEUhdJn8oGX (Vault 0)\n"
            "Bridge frontend: bridge.cookiescan.io\n"
            "Multisig transparency dashboard: sig.cookiechain.wtf/community\n\n"
            "Token roles:\n"
            "- sCOOK: Solana-side COOK (created on pump.fun)\n"
            "- cCOOK: Cookie Chain-side COOK (the native COOK)\n"
            "- Locked COOK: acquired locked allocation representing 27% of the supply\n\n"
            "The plan: create pump.fun token on Solana (sCOOK), acquire the locked 27% COOK "
            "allocation, unlock bridge-out for locked holders, then operate the 1:1 sCOOK ↔ "
            "cCOOK relayer bridge under community multisig custody."
        ),
        "topic": "chain",
    },
    "https://cookiescan.io/docs#developer-guide": {
        "title": "Cookie Chain — Developer Guide",
        "content": (
            "Cookie Chain — Developer Guide\n\n"
            "Cookie Chain is SVM-compatible. Anchor, native Rust, and standard Solana client "
            "SDKs work with no changes beyond pointing at the Cookie Chain RPC.\n\n"
            "Endpoints:\n"
            "- HTTP RPC: https://rpc.cookiescan.io\n"
            "- WebSocket: https://wss.cookiescan.io\n\n"
            "JavaScript/TypeScript:\n"
            "  import { Connection } from '@solana/web3.js';\n"
            "  const connection = new Connection('https://rpc.cookiescan.io', 'confirmed');\n\n"
            "Anchor.toml:\n"
            "  [provider]\n"
            "  cluster = 'https://rpc.cookiescan.io'\n\n"
            "Deploy a program:\n"
            "  solana program deploy ./target/deploy/my_program.so\n\n"
            "Builder quick path:\n"
            "- Set CLI/SDK to https://rpc.cookiescan.io\n"
            "- Deploy programs with Solana CLI, validate on Cookiescan\n"
            "- Submit ecosystem programs at cookiescan.io/submit-project\n\n"
            "Developer tools: cookiescan.io/developer-tools\n"
            "API playground: api.cookiescan.io/playground"
        ),
        "topic": "dev",
    },
    "https://cookiescan.io/docs#faq": {
        "title": "Cookie Chain — FAQ & Governance",
        "content": (
            "Cookie Chain — FAQ & Governance\n\n"
            "Cookie Chain governance is off-chain-first and community-led. Major decisions — "
            "including bridge signer rotation, validator set policy, treasury spend, and "
            "protocol-level upgrades — are discussed openly and ratified by the multi-sig and "
            "validator operator set.\n\n"
            "Principles:\n"
            "- No single point of control: bridge vault, core infrastructure, and treasury all "
            "sit behind m-of-n signer sets.\n"
            "- Open participation: validator onboarding and program listings are open to "
            "qualified community members.\n"
            "- Progressive decentralization: operator and signer sets expand over time.\n\n"
            "Where decisions happen:\n"
            "- Community channels (Discord and X) for proposals, discussion, and RFCs.\n"
            "- Multi-sig signer ceremonies for on-chain ratification.\n"
            "- Validator operator coordination for upgrade timing.\n\n"
            "Common questions:\n"
            "Q: What wallet should I use? A: Nightly wallet (nightly.app) — fully supported.\n"
            "Q: What is the RPC endpoint? A: https://rpc.cookiescan.io\n"
            "Q: How do I get COOK? A: Bridge from Solana via bridge.cookiescan.io or swap on "
            "ecosystem DEXs.\n"
            "Q: Is Cookie Chain the same as Cookienet? A: Yes — cookienet and cookiechain are "
            "synonymous names for the same network."
        ),
        "topic": "faq",
    },
}

# ---------------------------------------------------------------------------
# New entries to add (not yet in active.jsonl)
# ---------------------------------------------------------------------------

NEW_ENTRIES = [
    {
        "title": "Cookie Chain — COOK Native Token",
        "source": "https://docs.cookiechain.wtf/cook",
        "tags": ["web", "token", "cook"],
        "topic": "token",
        "content": (
            "Cookie Chain — COOK (Native Token)\n\n"
            "COOK is the native asset of Cookie Chain. It pays network fees, secures the chain "
            "through validator stake, and serves as the primary unit of account across the "
            "ecosystem.\n\n"
            "Key facts:\n"
            "- Symbol: COOK\n"
            "- Decimals: 9 (SPL and lamports-style precision)\n"
            "- Fee currency: all network fees are paid in COOK\n"
            "- Bridge model: COOK is bridged 1:1 to its Solana counterpart through the "
            "community multi-sig\n\n"
            "How to get COOK:\n"
            "- Bridge from Solana via bridge.cookiescan.io\n"
            "- Swap for COOK on ecosystem DEXs\n"
            "- Receive COOK directly from any Cookie Chain wallet\n\n"
            "Only use bridges and RPC endpoints linked from official community channels. "
            "There is no centralized foundation — verify endpoints before signing."
        ),
    },
    {
        "title": "Cookie Jar — Community Treasury Vault",
        "source": "https://docs.cookiechain.wtf/cookie-jar",
        "tags": ["web", "community", "treasury"],
        "topic": "community",
        "content": (
            "Cookie Jar — Community Treasury Vault\n\n"
            "Cookie Jar is the name given to the second community multisig vault (Vault 1). "
            "It collects ecosystem-aligned donations and routes assets toward builders, "
            "developers, and contributors working on Cookie Chain.\n\n"
            "Cookie Jar Vault 1 address: 568tU9FMksJDxjkLBjWisSA4J4C5uPH87NCCkyREwrxe\n\n"
            "Who controls it: the community multisig — not a single operator, founder, or "
            "private wallet.\n\n"
            "What donations are for:\n"
            "- Builder and developer incentives\n"
            "- Grants for useful apps, tools, and infrastructure\n"
            "- Support for contributors shipping public goods\n"
            "- Funding experiments that grow the Cookie Chain ecosystem\n\n"
            "Leading Cookie Chain ecosystem projects can donate a portion of their revenue into "
            "Cookie Jar as voluntary ecosystem contributions."
        ),
    },
    {
        "title": "Cookie Chain — For Degens (Quick Start)",
        "source": "https://docs.cookiechain.wtf/for-degens",
        "tags": ["web", "faq", "degens"],
        "topic": "faq",
        "content": (
            "Cookie Chain — For Degens\n\n"
            "A fast, safer path for trading, bridging, exploring apps, and moving through the "
            "ecosystem.\n\n"
            "Degen quick path:\n"
            "1. Install Nightly wallet (nightly.app) and add the Cookie Chain RPC.\n"
            "2. Bridge COOK through bridge.cookiescan.io\n"
            "3. Track balances, transactions, blocks, and validators on cookiescan.io\n"
            "4. Explore live programs and ecosystem dApps from cookiescan.io/programs\n\n"
            "Before you ape:\n"
            "- Verify bridge, RPC, and app URLs before signing.\n"
            "- Use a hot wallet for daily dApp activity and a separate wallet for storage.\n"
            "- Keep enough COOK for fees before interacting with programs.\n"
            "- Check explorer activity and program pages before trusting a new app.\n\n"
            "Fast path: Wallets → COOK → Bridge → Ecosystem Programs"
        ),
    },
    {
        "title": "Gorbagana Cash — For Builders",
        "source": "https://www.gorbagana.cash/docs/builders",
        "tags": ["web", "dev", "gcash"],
        "topic": "dev",
        "content": (
            "Gorbagana Cash — For Builders\n\n"
            "How to migrate or deploy projects on GCASH depending on whether you are coming "
            "from Trashnet or Solana.\n\n"
            "Coming from Trashnet: replace your old RPC URL with the GCASH community RPC:\n"
            "  https://community-rpc.trashscan.io\n\n"
            "Coming from Solana:\n"
            "1. Bridge tokens from Solana to GCASH to pay for transactions.\n"
            "2. Point Solana CLI to GCASH:\n"
            "   solana config set --url https://community-rpc.trashscan.io\n"
            "3. Deploy programs:\n"
            "   solana program deploy ./target/deploy/your_program.so\n"
            "   anchor deploy --provider.cluster https://community-rpc.trashscan.io\n"
            "4. Update dApp RPCs to https://community-rpc.trashscan.io"
        ),
    },
    {
        "title": "Gorbagana Cash — For Degens",
        "source": "https://www.gorbagana.cash/docs/degens",
        "tags": ["web", "faq", "gcash"],
        "topic": "faq",
        "content": (
            "Gorbagana Cash — For Degens\n\n"
            "If you know Solana, you already understand the base experience. "
            "The apps and culture are what change.\n\n"
            "GCASH behaves like Solana at the network level. Wallet flows, transactions, and "
            "dApp interactions should feel familiar. What changes is the ecosystem, the apps, "
            "and the community culture around the chain.\n\n"
            "Bridge assets into GCASH, then visit the ecosystem page to find the dApps you "
            "want to use. Swap, explore, mint, build, or just watch the cookie jar fill up.\n\n"
            "Simple path: Bridge in. Pick a dApp. Use GCASH like a Solana-style network with "
            "a different ecosystem.\n\n"
            "Explorer: trashscan.io\n"
            "Bridge: bridge.trashscan.io"
        ),
    },
    {
        "title": "Gorbagana Cash — RPC Endpoints",
        "source": "https://www.gorbagana.cash/docs/rpc",
        "tags": ["web", "dev", "gcash", "rpc"],
        "topic": "dev",
        "content": (
            "Gorbagana Cash — RPC Endpoints\n\n"
            "Use the community RPC to connect apps, tools, scripts, and Solana-compatible "
            "workflows to GCASH.\n\n"
            "RPC endpoint: https://community-rpc.trashscan.io\n"
            "Native token: GCASH\n\n"
            "Use this RPC when configuring wallets, Solana CLI, dApps, indexers, or backend "
            "services for Gorbagana Cash."
        ),
    },
    {
        "title": "Gorbagana Cash — Bridge",
        "source": "https://www.gorbagana.cash/docs/bridge",
        "tags": ["web", "chain", "gcash", "bridge"],
        "topic": "chain",
        "content": (
            "Gorbagana Cash — Bridge\n\n"
            "Bridge from Solana into Gorbagana Cash before interacting with the ecosystem.\n\n"
            "The bridge is the entry path for users and builders coming from Solana. "
            "Move assets into GCASH, then use them for transactions, deployments, and dApps.\n\n"
            "Bridge UI: bridge.trashscan.io\n"
            "Explorer: trashscan.io"
        ),
    },
    {
        "title": "Cookiequad — Community Multisig on Cookie Chain",
        "source": "https://cookiequads.vercel.app/",
        "tags": ["web", "chain", "multisig"],
        "topic": "chain",
        "content": (
            "Cookiequad Multisig\n\n"
            "Cookiequad is a multisig management app on Cookie Chain. It lets teams create "
            "multisigs, manage members, set permissions, and handle proposals on-chain — "
            "with zero fees and full transparency.\n\n"
            "Core capabilities:\n"
            "- Create autonomous or controlled multisigs\n"
            "- View members, permissions, vault balances, spending limits, and proposals\n"
            "- Create vault transfer proposals and config proposals\n"
            "- Approve, reject, cancel, activate, and execute proposals\n"
            "- Use existing spending limits directly from the UI\n\n"
            "How it works:\n"
            "1. Create a multisig with members, permissions, threshold, and optional authorities.\n"
            "2. Fund a vault PDA and create proposals for transfers or configuration changes.\n"
            "3. Members approve or reject proposals based on their voting permission.\n"
            "4. Once approved and any time lock has passed, an executor can run it.\n\n"
            "App: cookiequads.vercel.app\n"
            "Community Wallet: view the Cookiequad treasury in read-only mode or connect a "
            "member wallet to approve and execute actions."
        ),
    },
    {
        "title": "Cookie Chain — Break Gorbagana (Stress Test)",
        "source": "https://cookiescan.io/break-gorbagana",
        "tags": ["web", "chain", "demo"],
        "topic": "chain",
        "content": (
            "Cookie Chain — Break Gorbagana Stress Test\n\n"
            "An interactive stress-test tool on cookiescan.io that lets users hammer the "
            "Cookie Chain network with rapid RPC requests to test its performance.\n\n"
            "Cookie Chain is a high-performance blockchain with 1-second block times, "
            "sub-second finality, and low fees. The stress test demonstrates the network's "
            "capacity for high-throughput transactions.\n\n"
            "URL: cookiescan.io/break-gorbagana"
        ),
    },
    {
        "title": "Cookie Chain — Official X (Twitter)",
        "source": "https://x.com/TheCookieChain",
        "tags": ["social", "twitter", "official"],
        "topic": "socials",
        "content": (
            "Cookie Chain — Official X/Twitter\n\n"
            "The official Cookie Chain X (Twitter) account.\n"
            "URL: https://x.com/TheCookieChain\n\n"
            "Follow for announcements, updates, and community news about $COOK and the "
            "Cookie Chain ecosystem."
        ),
    },
    {
        "title": "Cookie Chain — Official Telegram Group",
        "source": "https://t.me/+YulIZhqjDrw3NDcx",
        "tags": ["community", "telegram", "official"],
        "topic": "community",
        "content": (
            "Cookie Chain — Official Telegram Group\n\n"
            "The official COOKIENET Telegram group — the main hub for $COOK and the "
            "Cookie Chain community.\n"
            "URL: https://t.me/+YulIZhqjDrw3NDcx\n\n"
            "Join to discuss $COOK, Cookie Chain developments, and connect with the community."
        ),
    },
    {
        "title": "Cookie Chain — Official Links",
        "source": "cookiechain_links",
        "tags": ["links", "official"],
        "topic": "links",
        "content": (
            "Cookie Chain — Official Links\n\n"
            "Explorer & Docs:\n"
            "- CookieScan (block explorer): https://cookiescan.io\n"
            "- Documentation: https://docs.cookiechain.wtf\n"
            "- API Playground: https://api.cookiescan.io/playground\n\n"
            "DeFi & Ecosystem:\n"
            "- CandyShop (DEX aggregator): https://swap.cookiescan.io\n"
            "- Cookie Bridge (Solana ↔ Cookie Chain): https://bridge.cookiescan.io\n"
            "- Cookoven (dApp hub): https://cookoven.xyz\n"
            "- Cookiequad (multisig): https://cookiequads.vercel.app\n\n"
            "Community:\n"
            "- Official X/Twitter: https://x.com/TheCookieChain\n"
            "- Official Telegram: https://t.me/+YulIZhqjDrw3NDcx\n"
            "- Gorbagana Cash (sister chain): https://www.gorbagana.cash\n\n"
            "Multisig & Governance:\n"
            "- Community multisig dashboard: https://sig.cookiechain.wtf/community\n"
            "- Bridge vault (Vault 0): G3mm95M4ns7mk8oseWGJnirvgyMahMz3vZEUhdJn8oGX\n"
            "- Cookie Jar vault (Vault 1): 568tU9FMksJDxjkLBjWisSA4J4C5uPH87NCCkyREwrxe"
        ),
    },
    {
        "title": "Cookie Chain — RPC & Network Endpoints",
        "source": "cookiechain_rpc",
        "tags": ["dev", "rpc", "network"],
        "topic": "dev",
        "content": (
            "Cookie Chain — RPC & Network Endpoints\n\n"
            "Use these endpoints to connect wallets, CLI tools, dApps, and SDKs to Cookie Chain.\n\n"
            "HTTP RPC:  https://rpc.cookiescan.io\n"
            "WebSocket: https://wss.cookiescan.io\n\n"
            "Wallet setup (Nightly or any Solana-compatible wallet):\n"
            "- Network: Custom SVM\n"
            "- RPC: https://rpc.cookiescan.io\n"
            "- WSS: https://wss.cookiescan.io\n\n"
            "Solana CLI:\n"
            "  solana config set --url https://rpc.cookiescan.io\n\n"
            "JavaScript/TypeScript:\n"
            "  new Connection('https://rpc.cookiescan.io', 'confirmed')\n\n"
            "Anchor.toml:\n"
            "  cluster = 'https://rpc.cookiescan.io'"
        ),
    },
]

# ---------------------------------------------------------------------------
# Manual reclassification map: entry_id -> correct topic(s)
# ---------------------------------------------------------------------------

RECLASSIFY = {
    # Telegram invite link saved as raw /ingest message — move to community
    "1738e682f3b1bff7": "community",
    # "bang is dead on g" — dev/chain chat noise, keep in general
    "fcf4b299776a06fc": "general",
    # Bridge discussion chat — chain topic
    "bc2629b67240e535": "chain",
    # "Fork of Gorbagana" narrative — lore
    "5fae330875f6ad73": "lore",
    # "cookienet and cookiechain are synonymous" — faq
    "20368aa40d12b008": "faq",
    # Official Telegram group entry — community
    "bb4c353798e62e00": "community",
    # Gorbagana Cash docs already in active.jsonl — reclassify correctly
    "4b7637ee905fb0dd": "dev",    # builders
    "2188239120d4b6b4": "lore",   # gcash docs intro
    "45a629b2299d649f": "faq",    # degens
    "b18c23ce8ba7f650": "dev",    # rpc
    "91b9e846eaa034eb": "chain",  # bridge
    # Ecosystem sites
    "56fb9b3fa095c089": "links",  # CandyShop
    "7c85bf73ecb41c6d": "links",  # Cookoven
    "4c45cef11d8670b5": "lore",   # Gorbagana Cash main site
    "15f2829601dae3df": "links",  # Cookie Bridge
    "eb31dcca3cbbff29": "dev",    # Trading API
    "b7d7754d6518fadc": "chain",  # Cookiequad
    "991876074939a958": "chain",  # break-gorbagana
    # Docs entries — updated content + correct topic
    "b4a8c9b502ebf183": "chain",  # introduction
    "90a7d724f6b817fd": "faq",    # getting-started
    "9c267c04794564dc": "faq",    # wallets
    "77de4b61d7be49fc": "chain",  # architecture
    "eb14923b8c14f8c7": "chain",  # validators
    "7be174219f750cd7": "chain",  # bridge
    "a296e792d138d03e": "dev",    # developer-guide
    "0d12273c92767ef8": "faq",    # faq
    # Lore / origin story
    "d75519dd24ca56e3": "lore",   # cookie recipe
}


def make_id(content: str, source: str) -> str:
    return hashlib.sha256(f"{source}:{content[:100]}".encode()).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_active() -> list[dict]:
    if not ACTIVE_FILE.exists():
        return []
    entries = []
    for line in ACTIVE_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def save_active(entries: list[dict]) -> None:
    ACTIVE_FILE.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def main() -> None:
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Load existing active entries ─────────────────────────────────
    entries = load_active()
    entry_map = {e["id"]: e for e in entries}
    print(f"Loaded {len(entries)} active entries")

    # ── Step 2: Update content for stub docs entries ──────────────────────────
    updated = 0
    for entry in entries:
        source = entry.get("source", "")
        if source in DOCS_CONTENT:
            doc = DOCS_CONTENT[source]
            entry["title"]   = doc["title"]
            entry["content"] = doc["content"]
            updated += 1
    print(f"Updated content for {updated} stub docs entries")

    # ── Step 3: Add new entries (skip if source already exists) ───────────────
    existing_sources = {e.get("source") for e in entries}
    added = 0
    for new in NEW_ENTRIES:
        if new["source"] in existing_sources:
            print(f"  SKIP (already exists): {new['title']}")
            continue
        eid = make_id(new["content"], new["source"])
        entry = {
            "id":         eid,
            "title":      new["title"],
            "content":    new["content"],
            "source":     new["source"],
            "tags":       new["tags"],
            "priority":   "normal",
            "added_at":   now_iso(),
            "added_by":   0,
            "status":     "active",
        }
        entries.append(entry)
        entry_map[eid] = entry
        added += 1
        print(f"  ADDED: {new['title']}")
    print(f"Added {added} new entries")

    # ── Step 4: Save updated active.jsonl ─────────────────────────────────────
    save_active(entries)
    print(f"Saved active.jsonl ({len(entries)} entries)")

    # ── Step 5: Wipe and rebuild all topic files ───────────────────────────────
    for topic in TOPICS:
        (TOPICS_DIR / f"{topic}.jsonl").write_text("")
    print("Wiped all topic files")

    topic_counts = {t: 0 for t in TOPICS}
    unclassified = []

    for entry in entries:
        if entry.get("status") == "stale":
            continue

        eid = entry["id"]
        source = entry.get("source", "")

        # Determine topic: manual override first, then new entry map, then source-based
        topic = RECLASSIFY.get(eid)
        if not topic:
            # Check if it was a new entry with explicit topic
            for new in NEW_ENTRIES:
                if new["source"] == source:
                    topic = new["topic"]
                    break
        if not topic:
            # Fallback classification by source URL
            s = source.lower()
            c = entry.get("content", "").lower()
            t = entry.get("tags", [])
            if "t.me" in s or "telegram" in s:
                topic = "community"
            elif "x.com" in s or "twitter.com" in s:
                topic = "socials"
            elif "developer" in s or "rpc" in s or "builder" in s or "api" in s:
                topic = "dev"
            elif "faq" in s or "getting-started" in s or "wallets" in s:
                topic = "faq"
            elif "lore" in c or "origin" in c or "recipe" in c:
                topic = "lore"
            elif "cook" in s and ("token" in c or "symbol" in c):
                topic = "token"
            else:
                topic = "general"

        if topic not in TOPICS:
            topic = "general"

        with open(TOPICS_DIR / f"{topic}.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
        topic_counts[topic] += 1

    # ── Step 6: Write index.json ───────────────────────────────────────────────
    index = {
        "topics": {
            t: {
                "file": f"topics/{t}.jsonl",
                "count": topic_counts[t],
                "description": {
                    "chain":     "Architecture, consensus, validators, bridge, ecosystem dApps",
                    "lore":      "Origin story, history, culture, Gorbagana",
                    "token":     "$COOK tokenomics, staking, bridge mechanics",
                    "community": "Telegram groups, community vault, governance",
                    "dev":       "Developer guide, SDK, RPC, API, builder docs",
                    "faq":       "Getting started, wallets, how-to guides, degens guide",
                    "links":     "Official websites, explorer, bridge, swap, dApps",
                    "socials":   "Official X/Twitter, community Twitter handles",
                    "general":   "General knowledge, miscellaneous",
                }.get(t, ""),
            }
            for t in TOPICS
        },
        "total_active": len([e for e in entries if e.get("status") != "stale"]),
        "last_rebuilt": now_iso(),
    }
    INDEX_FILE.write_text(json.dumps(index, indent=2) + "\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n=== Topic Distribution ===")
    for t in TOPICS:
        count = topic_counts[t]
        if count > 0:
            print(f"  {t:12s}: {count} entries")
    print(f"\nTotal active entries: {index['total_active']}")
    print("Done.")


if __name__ == "__main__":
    main()
