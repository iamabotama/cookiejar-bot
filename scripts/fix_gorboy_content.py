"""
Fix gorboy knowledge base entries by replacing GitHub blob-viewer HTML
with actual raw markdown content fetched from raw.githubusercontent.com.
"""
import json
import requests
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cookiejar.knowledge_store import rebuild_topic_files
from cookiejar import config

# Map: blob URL fragment -> (raw URL, topic, better title)
GORBOY_FIXES = [
    {
        "blob_fragment": "gor-boy-list/README.md at main",
        "raw_url": "https://raw.githubusercontent.com/iamabotama/gor-boy-list/main/README.md",
        "source": "https://github.com/iamabotama/gor-boy-list/blob/main/README.md",
        "topic": "lore",
        "title": "GORBAGIO Gor-Boy NFT Viewer - README",
    },
    {
        "blob_fragment": "gor-boy-list/GORBOY_Tokenomics_Whitepaper.md at main",
        "raw_url": "https://raw.githubusercontent.com/iamabotama/gor-boy-list/main/GORBOY_Tokenomics_Whitepaper.md",
        "source": "https://github.com/iamabotama/gor-boy-list/blob/main/GORBOY_Tokenomics_Whitepaper.md",
        "topic": "token",
        "title": "GORBOY Token Whitepaper",
    },
    {
        "blob_fragment": "gor-boy-list/GORBOY_Tokenomics_Summary.md at main",
        "raw_url": "https://raw.githubusercontent.com/iamabotama/gor-boy-list/main/GORBOY_Tokenomics_Summary.md",
        "source": "https://github.com/iamabotama/gor-boy-list/blob/main/GORBOY_Tokenomics_Summary.md",
        "topic": "token",
        "title": "GORBOY Tokenomics Summary",
    },
    {
        "blob_fragment": "gor-boy-list/GORBOY_SDK_Specification_DRAFT.md at main",
        "raw_url": "https://raw.githubusercontent.com/iamabotama/gor-boy-list/main/GORBOY_SDK_Specification_DRAFT.md",
        "source": "https://github.com/iamabotama/gor-boy-list/blob/main/GORBOY_SDK_Specification_DRAFT.md",
        "topic": "dev",
        "title": "GORBOY SDK Specification (Draft)",
    },
    {
        "blob_fragment": "gor-boy-list/QUICKSTART.md at main",
        "raw_url": "https://raw.githubusercontent.com/iamabotama/gor-boy-list/main/QUICKSTART.md",
        "source": "https://github.com/iamabotama/gor-boy-list/blob/main/QUICKSTART.md",
        "topic": "faq",
        "title": "GORBOY Quick Start Guide",
    },
]

# Fetch raw content for each fix
print("Fetching raw content...")
for fix in GORBOY_FIXES:
    r = requests.get(fix["raw_url"], timeout=15)
    r.raise_for_status()
    # Truncate SDK spec — it's 132k chars, way too large for a KB entry
    content = r.text
    if len(content) > 8000:
        content = content[:8000] + "\n\n[... truncated for knowledge base ...]"
    fix["content"] = content
    print(f"  {fix['title']}: {len(fix['content'])} chars")

# Load active.jsonl
active_path = config.ACTIVE_CACHE
print(f"\nLoading {active_path}...")
with open(active_path, "r", encoding="utf-8") as f:
    entries = [json.loads(l) for l in f if l.strip()]

print(f"Total entries: {len(entries)}")

# Apply fixes
updated = 0
for entry in entries:
    title = entry.get("title", "")
    for fix in GORBOY_FIXES:
        if fix["blob_fragment"] in title:
            print(f"\nFixing: {title[:60]}...")
            entry["title"] = fix["title"]
            entry["content"] = fix["content"]
            entry["source"] = fix["source"]
            entry["topic"] = fix["topic"]
            updated += 1
            break

print(f"\nUpdated {updated} entries.")

# Write back active.jsonl
with open(active_path, "w", encoding="utf-8") as f:
    for entry in entries:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

print("Wrote active.jsonl.")

# Rebuild topic files
print("Rebuilding topic files...")
rebuild_topic_files()
print("Done.")
