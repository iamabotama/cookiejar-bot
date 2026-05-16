#!/usr/bin/env python3
"""
CookieJar Bot — Knowledge Store Migration Script
Migrates existing active.jsonl entries into the new topic-based file structure.

Usage:
    python3 scripts/migrate_to_topics.py [--dry-run]

What it does:
  1. Reads all entries from knowledge/active.jsonl
  2. Classifies each entry into a topic using the rule-based classifier
  3. Writes each entry to knowledge/topics/<topic>.jsonl (skipping duplicates)
  4. Runs sync_cookiechain() to populate links/socials/community from cookiechain.json
  5. Rebuilds index.json with accurate entry counts

Safe to run multiple times — duplicates are skipped by source URL.
"""

import sys
import json
import argparse
from pathlib import Path

# Add the repo root to the path so we can import the cookiejar package
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Set up a minimal runtime dir so config.py resolves paths correctly
import os
os.environ.setdefault("COOKIEJAR_RUNTIME_DIR", str(REPO_ROOT))

from cookiejar import knowledge_store, config


def migrate(dry_run: bool = False) -> None:
    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating knowledge entries to topic files...")
    print(f"  active.jsonl: {config.ACTIVE_CACHE}")
    print(f"  topics dir:   {config.CACHE_DIR / 'topics'}")
    print()

    # Read all entries from active.jsonl
    entries = knowledge_store._read_entries(config.ACTIVE_CACHE)
    print(f"Found {len(entries)} entries in active.jsonl")

    if not entries:
        print("Nothing to migrate.")
    else:
        topic_counts: dict[str, int] = {}
        skipped = 0

        for entry in entries:
            if entry.get("status") != "active":
                skipped += 1
                continue

            topic = knowledge_store.classify_to_topic(entry)
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

            if not dry_run:
                path = knowledge_store._topic_path(topic)
                # Check for duplicate by ID
                existing = knowledge_store._read_entries(path)
                if any(e["id"] == entry["id"] for e in existing):
                    print(f"  [skip] {entry['id']} already in {topic}.jsonl")
                    continue
                knowledge_store._append_entry_to_file(path, entry)
                print(f"  [write] {entry['id']} -> {topic}.jsonl  ({entry['title'][:50]})")
            else:
                print(f"  [would write] {entry['id']} -> {topic}.jsonl  ({entry['title'][:50]})")

        print()
        print("Topic distribution:")
        for topic, count in sorted(topic_counts.items()):
            print(f"  {topic}: {count}")
        if skipped:
            print(f"  (skipped {skipped} non-active entries)")

    # Sync cookiechain.json into links/socials/community
    print()
    print("Syncing cookiechain.json into topic files...")
    if not dry_run:
        result = knowledge_store.sync_cookiechain()
        print(f"  links: {result['links']} entries")
        print(f"  socials: {result['socials']} entries")
        print(f"  community: {result['community']} entries")
    else:
        print("  [dry run] would sync cookiechain.json")

    # Rebuild index.json
    print()
    if not dry_run:
        knowledge_store.rebuild_index_counts()
        idx = knowledge_store._load_index()
        print("index.json updated:")
        for name, info in idx["topics"].items():
            print(f"  {name}: {info['entry_count']} entries")
    else:
        print("[dry run] would rebuild index.json")

    print()
    print("Migration complete." if not dry_run else "Dry run complete — no files written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate knowledge entries to topic files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
