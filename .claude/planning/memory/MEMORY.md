# Memory index

- [edap-cleanup-project](edap-cleanup-project.md) — the cleanup/decompose/avionics project: plan, TODO, phases, model-delegation rules
- [dev-env-setup](dev-env-setup.md) — Python 3.11 venv + mock ED files to run GUI on this laptop (no game installed)
- [web-ui-direction](web-ui-direction.md) — replace tkinter GUI with headless server + web MCDU (tablet); keep EDMesg, don't polish EDAPGui
- [feedback-commit-per-iteration](feedback_commit_per_iteration.md) — commit+push after each finished iteration, don't wait to be asked
- [feedback-delegate-model-via-subagent](feedback-delegate-model-via-subagent.md) — for non-default-model work, spawn a model-specific subagent myself; don't make the user switch /model
- [feedback-qa-subagent-before-commit](feedback-qa-subagent-before-commit.md) — independent QA gate (PASS/FAIL) before each commit, run inline via tools/qa_service_extraction.py (cheap), not a subagent
