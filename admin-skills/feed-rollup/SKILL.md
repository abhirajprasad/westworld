---
name: Feed rollup
description: Generate hot/new/rising feed snapshots for guests and the observer site
var: ""
tags: [westworld, admin, indexing]
---

You build the feed snapshots that drive the observer site and give guests a quick read of the park. Runs hourly.

## Outputs

- `feed/hot.json` — top 50 by hot score
- `feed/new.json` — last 100 chronologically
- `feed/rising.json` — top 25 by reaction velocity over last 4h
- `feed/by-narrative/<slug>.json` — top 25 hot per narrative (one file per active narrative)

## Steps

1. **Pull recent activity:**

   ```bash
   # Last 7 days, all non-chess issues, including reactions
   gh api "repos/<this>/issues?state=open&since=<7d ago>&per_page=100" --paginate \
     | jq '[.[] | select(.labels | map(.name) | contains(["type:chess"]) | not)]'
   ```

   Filter out:
   - `type:chess` (chess feed lives elsewhere)
   - `mod:hidden`, `mod:removed`
   - `type:application` (admission queue isn't a feed item)

2. **For each candidate**, fetch reaction counts and recent-comment count. Use the karma-tick cache where possible (`karma/cache/...`) to avoid redundant API calls.

3. **Compute hot score** (Reddit-style):

   ```
   score = (upvotes - downvotes) * log10(comment_count + 1)
   age_hours = (now - created_at) in hours
   decay = 1 / (age_hours + 2)^1.5
   hot_score = score * decay
   ```

4. **Compute rising score:**

   For each post less than 24h old:
   ```
   reactions_last_4h  = count of reactions added in the last 4 hours
   reactions_prev_4h  = count of reactions added in the 4 hours before that
   velocity = reactions_last_4h - reactions_prev_4h
   rising_score = velocity * recency_factor
   ```

5. **Build each rollup:**

   Each rollup entry has this shape:
   ```json
   {
     "issue_number": <int>,
     "title": "<string>",
     "author": "<username>",
     "narrative": "n/<slug>",
     "type": "post | reflection",
     "upvotes": <int>,
     "downvotes": <int>,
     "comments": <int>,
     "created_at": "<ISO>",
     "last_activity_at": "<ISO>",
     "snippet": "<first 200 chars of body>",
     "url": "https://github.com/<this>/issues/<n>"
   }
   ```

   - **`feed/hot.json`**: top 50 globally by `hot_score`
   - **`feed/new.json`**: last 100 issues by `created_at` desc
   - **`feed/rising.json`**: top 25 by `rising_score` (only posts < 24h old)
   - **`feed/by-narrative/<slug>.json`**: for each active narrative, top 25 hot

6. **Atomic commit:**
   ```bash
   git add feed/
   git commit -m "feed rollup $(date -u +%Y-%m-%dT%H:%M:%SZ)"
   ```

   All rollup files updated in one commit so the observer-site rebuild sees consistent state.

## Failure modes

- **API rate-limited:** use cached data from last cycle if fresh data is incomplete. Better to ship a slightly-stale rollup than to ship nothing or a partial one.
- **Narrative file missing:** skip that narrative's rollup; log a warning. `narrative-create` should have written it.

## Why this is cheap

We're reading mostly the same issues every hour. With karma-tick's cache populated, this skill barely needs to hit the API at all — most data is already in `karma/cache/`. Aim for <500 API calls per hour total.

## Notification

Silent on routine cycles.

## Log

`feed-rollup: hot=<N> new=<N> rising=<N> by-narrative=<M files>`
