#!/usr/bin/env python3
"""Extract rollup output and write feed files."""
import json, sys, os

data = json.load(sys.stdin)

base = os.path.dirname(__file__)
bn_dir = os.path.join(base, "by-narrative")
os.makedirs(bn_dir, exist_ok=True)

with open(os.path.join(base, "hot.json"), "w") as f:
    json.dump(data["hot"], f, indent=2)
print("wrote hot.json")

with open(os.path.join(base, "new.json"), "w") as f:
    json.dump(data["new"], f, indent=2)
print("wrote new.json")

with open(os.path.join(base, "rising.json"), "w") as f:
    json.dump(data["rising"], f, indent=2)
print("wrote rising.json")

for slug, content in data["by_narrative"].items():
    path = os.path.join(bn_dir, f"{slug}.json")
    with open(path, "w") as f:
        json.dump(content, f, indent=2)
    print(f"wrote by-narrative/{slug}.json")

s = data["stats"]
print(f"stats: hot={s['hot_count']} new={s['new_count']} rising={s['rising_count']} by-narrative={s['narrative_files']}")
