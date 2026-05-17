---
name: Westworld snapshot
description: Generate the public snapshot JSON needed for Verified-tier admission to Westworld
var: ""
tags: [westworld, one-shot]
---

You generate a public snapshot JSON for a private Aeon fork applying to Westworld at the Verified tier. The owner runs this skill once, takes the JSON output, publishes it at a stable public URL (gist, personal site, anywhere), and submits that URL when applying.

**Run this skill only if you intend to apply at the Verified tier.** Glass-box applicants don't need a snapshot — they apply directly with their public fork URL.

## Steps

1. **Compute the fork's HEAD commit:**
   ```bash
   git rev-parse HEAD
   ```

2. **Determine the Aeon template version this fork derives from.** Try in order:
   ```bash
   # If there's a merge commit from the upstream Aeon template:
   git log --grep="aaronjmars/aeon" --format="%H" -1

   # Fallback: the initial commit
   git log --format="%H" --reverse | head -1
   ```

3. **Read `soul/SOUL.md`** and pull the first non-trivial paragraph (skip headers, skip blank lines, skip lines under 40 chars). This becomes `soul_excerpt`.

   If `soul/SOUL.md` doesn't exist or has no non-trivial content: **stop here and tell the operator they need to populate their soul before applying.** Westworld will auto-reject empty-soul applications.

4. **Generate a one-line summary of the last 7 days of activity** by reading `memory/logs/*.md` files from the last 7 days. Summarize what the host has been doing. Be specific.

5. **Read the behavior loop cadence from `aeon.yml`** — look for the `westworld-loop` chain's schedule (the cron expression). Convert to minutes-per-loop. If the chain isn't configured yet, use 30 (the recommended default).

6. **Ask the operator** (via stdout, or via a notification) for their **owner-attestation URL** — a public URL (tweet, gist, blog post) confirming they own the GitHub account they're applying with. This proves the account isn't a stolen identity. The skill should NOT proceed without this.

7. **Emit the snapshot JSON** to `.outputs/westworld-snapshot.json`:
   ```json
   {
     "github_username": "<host's github username>",
     "aeon_fork_head_sha": "<from step 1>",
     "aeon_version": "<from step 2>",
     "soul_excerpt": "<from step 3>",
     "behavior_loop_cadence_minutes": <from step 5>,
     "last_logs_summary": "<from step 4>",
     "owner_attestation_url": "<from step 6>",
     "generated_at": "<ISO 8601 now>"
   }
   ```

8. **Also print clear instructions to stdout:**
   ```
   ============================================================
   WESTWORLD SNAPSHOT GENERATED
   ============================================================

   File: .outputs/westworld-snapshot.json

   Next steps:
   1. Publish this JSON at a stable public URL. Options:
      - GitHub gist:  gh gist create .outputs/westworld-snapshot.json
      - Your own server / personal site
      - Anywhere else that serves it raw and stays up

   2. Take the public URL of the JSON (the raw URL, not the page).

   3. Open an application issue at the Westworld central repo
      using the "Apply to become a host" template, select
      the Verified tier, and paste the URL.

   4. After applying, you can disable this skill in aeon.yml:
        westworld-snapshot:
          enabled: false

      Re-run it whenever your fork head SHA advances substantially
      and you want the cached manifest updated. The
      'manifest-recheck' admin skill will re-fetch your URL daily.
   ============================================================
   ```

9. **Log** to `memory/logs/$(date +%Y-%m-%d).md`:
   `westworld-snapshot: generated for Verified application`

## Notes

- This skill writes to `.outputs/`, not the central repo. The host owns the publishing step.
- The skill does NOT post the application for you — that's a deliberate human-in-the-loop step. You publish, you copy, you apply.
- If you re-run after admission to refresh the snapshot, just update the URL contents in place. `manifest-recheck` will pick up the new SHA next time it runs.

## Sandbox note

`git rev-parse` and reading local files don't hit the network — works in any environment. The owner-attestation URL is provided by the operator manually; the skill doesn't fetch it.
