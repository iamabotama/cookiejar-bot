#!/usr/bin/env python3
"""Rebuild topic files from active.jsonl and push all topic files to GitHub."""
import sys
import os
import json
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# Import via package
from cookiejar import knowledge_store, config

print("Rebuilding topic files from active.jsonl...")
knowledge_store.rebuild_topic_files()
print("Rebuild done.")

# Verify gorboy entries
found = []
topics_dir = config.CACHE_DIR / "topics"
for topic_file in topics_dir.glob("*.jsonl"):
    topic = topic_file.stem
    with open(topic_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            t = e.get('title', '').lower()
            c = e.get('content', '').lower()
            if 'gorboy' in t or 'gorboy' in c or 'goyboy' in t:
                found.append((topic, e['id'][:8], e.get('title', '?')[:60]))

print(f"\nGorboy entries now in topic files: {len(found)}")
for t, i, title in found:
    print(f"  [{t}] {i} — {title}")

# Show all topic counts
print("\nTopic file entry counts:")
for topic_file in sorted(topics_dir.glob("*.jsonl")):
    count = sum(1 for line in open(topic_file) if line.strip())
    print(f"  {topic_file.stem}: {count}")
