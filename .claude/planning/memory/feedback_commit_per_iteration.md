---
name: feedback-commit-per-iteration
description: "User wants a git commit + push after each completed iteration/step, not batched at the end"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1a378552-501b-4086-93bf-2a7d2d54f028
---

Commit and push after each completed iteration of work, not just when explicitly asked at the end of a session.

**Why:** User explicitly corrected this — on the [[edap-cleanup-project]] work, changes were left uncommitted across multiple completed steps (file deletions, ED_AP.py cleanup, README edits) until the user had to ask for commit+push separately each time.

**How to apply:** When a coherent unit of work finishes cleanly (e.g., a TODO checklist item, a phase step, a verified fix) and the working tree is in a good state (imports clean, tests/checks pass), commit it and push — don't wait for the user to ask. Still follow the existing repo-wide git safety rules (new commits not amends, no force-push, no `-i` flags, ask before anything destructive) — this preference is about *cadence* (commit often, per iteration) not about relaxing those safety rules. If a step leaves the tree in a known-broken intermediate state (e.g., mid-refactor where import is expected to fail until the next step), it's fine to hold the commit until the tree is green again, per the project's own verification convention.
