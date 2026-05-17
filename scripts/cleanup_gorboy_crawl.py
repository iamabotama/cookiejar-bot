"""
One-off cleanup: remove the 25 junk entries from the GitHub crawl of the
Gorboy whitepaper repo, keeping only entries with real document content.
Real entries: .md files from the gor-boy-list repo that contain actual content.
Junk: sign-in pages, profile pages, other repos, JSON data files, images, etc.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
KB_PATH = REPO_ROOT / "knowledge" / "active.jsonl"

# Patterns that identify REAL gorboy document entries to keep
KEEP_PATTERNS = [
    "GORBOY_Tokenomics_Whitepaper.md",
    "GORBOY_Tokenomics_Summary.md",
    "GORBOY_SDK_Specification_DRAFT.md",
    "QUICKSTART.md",
    "README.md",
]

# Patterns that identify JUNK entries to remove
JUNK_PATTERNS = [
    "github.com/login",
    "github.com/iamabotama?tab=",
    "github.com/iamabotama/aGORaphobia",
    "github.com/iamabotama/cg_flair_bot",
    "github.com/iamabotama/MMEmailCollateral",
    "github.com/iamabotama/Lazarus-Countermeasures",
    "github.com/iamabotama/gorbot",
    "github.com/iamabotama/gor-boy-list/branches",
    "github.com/iamabotama/gor-boy-list/tags",
    "github.com/iamabotama/gor-boy-list/commits",
    "github.com/iamabotama/gor-boy-list/stargazers",
    "github.com/iamabotama/gor-boy-list/blob/main/bridge-cache.json",
    "github.com/iamabotama/gor-boy-list/blob/main/data.json",
    "github.com/iamabotama/gor-boy-list/blob/main/escrow-cache.json",
    "github.com/iamabotama/gor-boy-list/blob/main/gitignore",
    "github.com/iamabotama/gor-boy-list/blob/main/gorboy_logo",
    "github.com/iamabotama/gor-boy-list/blob/main/index.html",
    "iamabotama (iamabotama) · GitHub",
    "GitHub - iamabotama/gor-boy-list",
    "Sign in to GitHub",
    "Stargazers · iamabotama",
    "Branches · iamabotama",
    "Releases · iamabotama",
    "Commits · iamabotama",
    "History for GORBOY",
    "iamabotama (iamabotama) / Repositories",
    "iamabotama (iamabotama) / Projects",
    "iamabotama (iamabotama) / Packages",
    "iamabotama (iamabotama) / Starred",
]

def is_junk(entry: dict) -> bool:
    source = entry.get("source", "")
    title = entry.get("title", "")
    for pattern in JUNK_PATTERNS:
        if pattern in source or pattern in title:
            return True
    return False

def main():
    entries = []
    with open(KB_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    kept = []
    removed = []
    for e in entries:
        if is_junk(e):
            removed.append(e)
        else:
            kept.append(e)

    print(f"Total entries: {len(entries)}")
    print(f"Keeping: {len(kept)}")
    print(f"Removing: {len(removed)}")
    print("\nRemoving:")
    for e in removed:
        print(f"  [{e.get('id','?')[:8]}] {e.get('title','?')[:70]}")

    if "--dry-run" in sys.argv:
        print("\nDry run — no changes written.")
        return

    # Write kept entries back
    with open(KB_PATH, "w") as f:
        for e in kept:
            f.write(json.dumps(e) + "\n")

    print(f"\nDone. {len(removed)} entries removed from active.jsonl.")

if __name__ == "__main__":
    main()
