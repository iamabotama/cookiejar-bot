"""
Patch missing topic fields on all active.jsonl entries that have topic=None or missing,
then rebuild all topic files.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cookiejar import knowledge_store

KB = REPO_ROOT / "knowledge" / "active.jsonl"

def classify_entry(e: dict) -> str:
    source = e.get("source", "")
    title = e.get("title", "")
    content = e.get("content", "")
    combined = f"{title} {content[:300]}".lower()

    if "GORBOY_Tokenomics" in title or "GORBOY_Tokenomics" in source:
        return "token"
    if "GORBOY_SDK" in title or "GORBOY_SDK" in source:
        return "dev"
    if "QUICKSTART" in title and "gor-boy" in source:
        return "faq"
    if "README" in title and "gor-boy" in source:
        return "lore"
    if "goyboy.com" in source or "gorboy" in combined:
        return "lore"

    # Fall back to keyword classifier
    return knowledge_store.classify_to_topic({"title": title, "content": content, "tags": []})

def main():
    entries = []
    with open(KB) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    patched = 0
    for e in entries:
        if not e.get("topic"):
            e["topic"] = classify_entry(e)
            patched += 1

    with open(KB, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    print(f"Patched {patched} entries with missing topics")

    knowledge_store.rebuild_topic_files()
    print("Topic files rebuilt")

    # Show gorboy entries
    print("\nGorboy entries now:")
    for e in entries:
        src = e.get("source", "")
        if "gorboy" in src.lower() or "gorboy" in e.get("title", "").lower() or "goyboy" in src.lower():
            print(f"  [{e['id'][:8]}] topic={e['topic']:<10} | {e.get('title','?')[:65]}")

if __name__ == "__main__":
    main()
