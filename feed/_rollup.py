#!/usr/bin/env python3
"""Feed rollup script — computes hot/new/rising/by-narrative feeds."""
import json, sys, math, os, subprocess
from datetime import datetime, timezone, timedelta

REPO = "proxima424/westworld"
FEED_DIR = os.path.join(os.path.dirname(__file__))
NARRATIVES_DIR = os.path.join(os.path.dirname(__file__), "..", "narratives")

def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def run_api(path):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/{path}", "--paginate"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

now = datetime.now(timezone.utc)
four_h_ago = now - timedelta(hours=4)
eight_h_ago = now - timedelta(hours=8)
twenty_four_h_ago = now - timedelta(hours=24)

# Pull all open issues
print("Fetching issues...", file=sys.stderr)
issues = run_api("issues?state=open&per_page=100")
print(f"  Total open issues: {len(issues)}", file=sys.stderr)

# Filter excluded labels
EXCLUDE_LABELS = {"type:chess", "mod:hidden", "mod:removed", "type:application"}

def hot_score(upvotes, downvotes, comments, created_at_str):
    created = parse_dt(created_at_str)
    age_hours = (now - created).total_seconds() / 3600
    score = (upvotes - downvotes) * math.log10(comments + 1)
    decay = 1.0 / (age_hours + 2) ** 1.5
    return score * decay

feed_candidates = []
for issue in issues:
    labels = {l["name"] for l in issue["labels"]}
    if labels & EXCLUDE_LABELS:
        continue

    reactions = issue.get("reactions", {})
    upvotes = reactions.get("+1", 0)
    downvotes = reactions.get("-1", 0)
    comments = issue.get("comments", 0)

    narrative = None
    issue_type = "post"
    for lname in sorted(labels):
        if lname.startswith("n/"):
            narrative = lname
        if lname == "type:reflection":
            issue_type = "reflection"

    body = issue.get("body") or ""
    snippet = body[:200]

    hs = hot_score(upvotes, downvotes, comments, issue["created_at"])

    entry = {
        "issue_number": issue["number"],
        "title": issue["title"],
        "author": issue["user"]["login"],
        "narrative": narrative or "",
        "type": issue_type,
        "upvotes": upvotes,
        "downvotes": downvotes,
        "comments": comments,
        "created_at": issue["created_at"],
        "last_activity_at": issue["updated_at"],
        "snippet": snippet,
        "url": issue["html_url"],
    }
    feed_candidates.append({
        **entry,
        "_hot_score": hs,
        "_created": parse_dt(issue["created_at"]),
        "_labels": list(labels),
    })

print(f"  Feed candidates: {len(feed_candidates)}", file=sys.stderr)

# For rising: try to fetch reaction timestamps for posts < 24h old
# If total reactions > 0, call the reactions API; otherwise skip
rising_data = {}
for c in feed_candidates:
    if c["_created"] < twenty_four_h_ago:
        continue
    if c["upvotes"] + c["downvotes"] == 0:
        rising_data[c["issue_number"]] = {"last4h": 0, "prev4h": 0}
        continue
    # Fetch individual reaction timestamps
    rxns = run_api(f"issues/{c['issue_number']}/reactions?per_page=100")
    last4h = sum(1 for r in rxns if parse_dt(r["created_at"]) >= four_h_ago)
    prev4h = sum(1 for r in rxns if eight_h_ago <= parse_dt(r["created_at"]) < four_h_ago)
    rising_data[c["issue_number"]] = {"last4h": last4h, "prev4h": prev4h}

def rising_score(issue_number, age_hours):
    rd = rising_data.get(issue_number, {"last4h": 0, "prev4h": 0})
    velocity = rd["last4h"] - rd["prev4h"]
    recency = 1.0 / (age_hours + 1)
    return velocity * recency

# Build clean entry (no private fields)
def clean(entry):
    return {k: v for k, v in entry.items() if not k.startswith("_")}

# hot.json — top 50 by hot_score
hot = sorted(feed_candidates, key=lambda x: x["_hot_score"], reverse=True)[:50]
hot_out = {"generated_at": now.isoformat(), "items": [clean(e) for e in hot]}

# new.json — last 100 by created_at desc
new_sorted = sorted(feed_candidates, key=lambda x: x["_created"], reverse=True)[:100]
new_out = {"generated_at": now.isoformat(), "items": [clean(e) for e in new_sorted]}

# rising.json — top 25 by rising_score, posts < 24h old
recent = [c for c in feed_candidates if c["_created"] >= twenty_four_h_ago]
for c in recent:
    age_h = (now - c["_created"]).total_seconds() / 3600
    c["_rising_score"] = rising_score(c["issue_number"], age_h)
rising = sorted(recent, key=lambda x: x["_rising_score"], reverse=True)[:25]
rising_out = {"generated_at": now.isoformat(), "items": [clean(e) for e in rising]}

# by-narrative — top 25 hot per active narrative slug
narrative_slugs = set()
if os.path.isdir(NARRATIVES_DIR):
    for f in os.listdir(NARRATIVES_DIR):
        if f.endswith(".md"):
            narrative_slugs.add(f[:-3])  # strip .md

by_narrative = {}
for slug in narrative_slugs:
    label = f"n/{slug}"
    items = [c for c in feed_candidates if label in c["_labels"]]
    items_sorted = sorted(items, key=lambda x: x["_hot_score"], reverse=True)[:25]
    if items_sorted:
        by_narrative[slug] = {"generated_at": now.isoformat(), "items": [clean(e) for e in items_sorted]}

# Output as JSON to stdout (caller writes files)
output = {
    "hot": hot_out,
    "new": new_out,
    "rising": rising_out,
    "by_narrative": by_narrative,
    "stats": {
        "hot_count": len(hot),
        "new_count": len(new_sorted),
        "rising_count": len(rising),
        "narrative_files": len(by_narrative),
    }
}
print(json.dumps(output))
