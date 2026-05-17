"""
Delete all gorboy/gor-boy-list entries from active.jsonl so the user
can re-crawl them cleanly using the fixed crawler.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cookiejar.knowledge_store import rebuild_topic_files
from cookiejar import config

active_path = config.ACTIVE_CACHE

with open(active_path, "r", encoding="utf-8") as f:
    entries = [json.loads(l) for l in f if l.strip()]

print(f"Total entries before: {len(entries)}")

# Identify gorboy entries by source or title containing gor-boy-list or goyboy
def is_gorboy(e):
    for field in ("title", "source", "content"):
        val = e.get(field, "").lower()
        if "gor-boy-list" in val or "gorboy" in val or "goyboy" in val:
            return True
    return False

kept = [e for e in entries if not is_gorboy(e)]
removed = [e for e in entries if is_gorboy(e)]

print(f"Removing {len(removed)} gorboy entries:")
for e in removed:
    print(f"  - {e.get('title','?')[:80]}")

print(f"Keeping {len(kept)} entries.")

with open(active_path, "w", encoding="utf-8") as f:
    for e in kept:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print("Wrote active.jsonl.")
print("Rebuilding topic files...")
rebuild_topic_files()
print("Done. Ready for re-crawl.")
