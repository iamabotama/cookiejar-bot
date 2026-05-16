"""patch_gcash_titles.py — Fix generic 'Gorbagana Cash | GCASH' titles."""
import json
from pathlib import Path

ACTIVE_FILE = Path(__file__).parent.parent / "knowledge" / "active.jsonl"

TITLE_PATCHES = {
    "4c45cef11d8670b5": "Gorbagana Cash (GCASH) — Community Hard Fork Overview",
    "4b7637ee905fb0dd": "Gorbagana Cash — For Builders",
    "2188239120d4b6b4": "Gorbagana Cash — Documentation Overview",
    "45a629b2299d649f": "Gorbagana Cash — For Degens",
    "b18c23ce8ba7f650": "Gorbagana Cash — RPC Endpoints",
    "91b9e846eaa034eb": "Gorbagana Cash — Bridge",
}

entries = [json.loads(l) for l in ACTIVE_FILE.read_text().splitlines() if l.strip()]
for e in entries:
    if e["id"] in TITLE_PATCHES:
        e["title"] = TITLE_PATCHES[e["id"]]
        print(f"  PATCHED: {e['title']}")
ACTIVE_FILE.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
print("Done.")
