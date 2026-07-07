---
name: feedback-qa-subagent-before-commit
description: "After each coding subagent, run a read-only QA subagent to verify acceptance criteria + regressions and report PASS/FAIL before committing"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fa81ee15-ba84-4599-81f3-33b8e8727219
---

The user wants a QA gate in the workflow. After a coding subagent finishes and BEFORE I commit, run a separate read-only QA subagent that verifies the change against acceptance criteria and checks for regressions, marks PASS/FAIL per criterion, and writes a test report. The QA agent must NOT modify code, NOT commit, NOT plan. Only commit if everything is PASS; if any FAIL, fix first (another coding subagent or inline), then re-QA.

**Why:** a quality gate to catch regressions before they enter git history — the user asked for this explicitly, modeled on a QA-agent role that reads the task's "desired result", runs build/tests, checks acceptance criteria, and produces a PASS/FAIL report.

**How to apply (this Python repo):** acceptance criteria come from the plan/TODO ([[edap-cleanup-project]] → fss-glowing-island). QA checks typically: `.\venv\Scripts\python.exe -c "import EDAPGui"` (exit 0), JSON validity of any edited locales, targeted greps (removed tokens gone / guard tokens still present), a mock-env GUI launch (tools/setup_mock_env.ps1), and that KEPT features (ELW/AW advisor, honk, EDNavigationPanel, core) are untouched. Use a subagent profile that cannot edit source (e.g. instruct general-purpose explicitly, or use a read-only agent); have it write test_report.md to the session scratchpad (NOT the repo, so it isn't committed) and return the PASS/FAIL summary. Relay the summary to the user. Pairs with [[feedback-commit-per-iteration]] (commit per iteration) and [[feedback-delegate-model-via-subagent]].
