---
name: feedback-qa-subagent-before-commit
description: "After each coding subagent, run an independent read-only QA gate (PASS/FAIL) before committing — as a cheap inline script, not a heavyweight subagent"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fa81ee15-ba84-4599-81f3-33b8e8727219
---

The user wants a QA gate: after a coding subagent finishes and BEFORE committing, independently verify the change against acceptance criteria + regressions, PASS/FAIL, and only commit if all PASS (else fix first, re-QA). QA must not modify code or commit.

**Token optimization (user asked 2026-07-07, "QA-субагент потребляет очень много токенов, надо оптимизировать"):** do NOT spawn a separate QA *subagent* for this — they burned 45–75k tokens each on cold-start re-reading, repeated greps, and verbose reports. The checks are deterministic, so run them INLINE from the orchestrator via a reusable script. This still satisfies the gate (objective commands, run by me, not trusting the coding subagent's self-report) and is far cheaper. Running verification inline does NOT violate "all coding via subagents" ([[feedback-delegate-model-via-subagent]]) — verification is orchestration, not coding.

**How to apply (service-extraction refactors, Phase 2):** use the reusable script `scratchpad/qa_service_extraction.py` (args `--service-file --service-module --names a,b,c`). It runs: import ED_AP+EDAPGui, standalone import of the new service module (circular-import check), routing grep invariants (methods removed from ED_AP; no stale `self.<name>(` in ED_AP; no `self.ap.<name>(` intra-service misroute; no module-top `import ED_AP` in the service), and per-method behaviour parity vs `git show HEAD:ED_AP.py` (normalize `self.ap.`->`self.`, ignore blank lines + added deferred imports). Exit 0 = all PASS. Then a minimal GUI smoke: launch on the mock env (tools/setup_mock_env.ps1) and grep the output for `Traceback` only (don't capture the whole PaddleOCR log). Commit only on all-PASS. Pairs with [[feedback-commit-per-iteration]] and [[edap-cleanup-project]].
